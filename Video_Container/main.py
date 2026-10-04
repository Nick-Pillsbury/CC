import os
import signal
import socket
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from fastapi import FastAPI

app = FastAPI()

# ---------------------------------------------------------------------------
# Config (override with environment variables, e.g. in docker-compose)
# ---------------------------------------------------------------------------
CAMERA_DEVICE = os.getenv("CAMERA_DEVICE", "/dev/video0")
# mjpeg / yuyv422 -> software x264 encode on the Pi.
# h264 -> camera already outputs H.264, so FFmpeg just copies it (lowest latency + CPU).
CAMERA_INPUT_FORMAT = os.getenv("CAMERA_INPUT_FORMAT", "mjpeg")
VIDEO_SIZE = os.getenv("VIDEO_SIZE", "1280x720")
FRAMERATE = os.getenv("FRAMERATE", "30")
BITRATE = os.getenv("BITRATE", "2M")      # cap so weak cellular signal doesn't stall the stream
BUFSIZE = os.getenv("BUFSIZE", "1M")
RTSP_PORT = int(os.getenv("RTSP_PORT", "8554"))
RTSP_URL = f"rtsp://127.0.0.1:{RTSP_PORT}/stream"  # local ingest; MediaMTX serves WebRTC to the Frontend
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", "/recordings")  # /recordings in docker is linked to /mnt/usb on host

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
lock = threading.Lock()
ffmpeg_process = None
recording_process = None
recording_file = None
last_error = None
stream_logs = deque(maxlen=20)
recording_logs = deque(maxlen=20)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _set_error(message, logs=None):
    global last_error
    last_error = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "message": message,
        "details": list(logs)[-5:] if logs else [],
    }


def _port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _storage_ok():
    try:
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        return os.access(RECORDINGS_DIR, os.W_OK)
    except OSError:
        return False


def _spawn(cmd, log_buffer):
    """Start ffmpeg and keep its recent stderr lines for error reporting."""
    log_buffer.clear()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def reader():
        for line in proc.stderr:
            log_buffer.append(line.decode(errors="replace").rstrip())

    threading.Thread(target=reader, daemon=True).start()
    return proc


def _refresh():
    """Detect processes that died on their own (crash, camera unplugged, etc.). Call with lock held."""
    global ffmpeg_process, recording_process, recording_file

    if ffmpeg_process is not None and ffmpeg_process.poll() is not None:
        _set_error(f"stream process exited unexpectedly (code {ffmpeg_process.returncode})", stream_logs)
        ffmpeg_process = None

    if recording_process is not None and recording_process.poll() is not None:
        _set_error(f"recording process exited unexpectedly (code {recording_process.returncode})", recording_logs)
        recording_process = None
        recording_file = None


def _stream_cmd():
    cmd = [
        "ffmpeg",
        "-loglevel", "warning",
        "-fflags", "nobuffer",
        "-flags", "low_delay",
        "-f", "v4l2",
        "-input_format", CAMERA_INPUT_FORMAT,
        "-video_size", VIDEO_SIZE,
        "-framerate", FRAMERATE,
        "-i", CAMERA_DEVICE,
        "-an",
    ]


    cmd += [
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-profile:v", "baseline",   # browser WebRTC compatible
        "-g", FRAMERATE,            # keyframe about every second
        "-b:v", BITRATE,
        "-maxrate", BITRATE,
        "-bufsize", BUFSIZE,
    ]

    cmd += ["-f", "rtsp", "-rtsp_transport", "tcp", RTSP_URL]
    return cmd


# ---------------------------------------------------------------------------
# Stream Start
# Start an ffmpeg process to:
#   - capture video from the camera
#   - encode it with H.264 (or copy it if the camera already outputs H.264)
#   - publish it over RTSP to MediaMTX on localhost:8554 (MediaMTX serves it as WebRTC)
# ---------------------------------------------------------------------------
@app.post("/stream/start")
def start_stream():
    global ffmpeg_process

    with lock:
        _refresh()

        if ffmpeg_process is not None:
            return {"status": "stream already running"}

        if not os.path.exists(CAMERA_DEVICE):
            msg = f"camera not found at {CAMERA_DEVICE}"
            _set_error(msg)
            return {"status": "error", "message": msg}

        if not _port_open("127.0.0.1", RTSP_PORT):
            msg = f"MediaMTX not reachable on port {RTSP_PORT}"
            _set_error(msg)
            return {"status": "error", "message": msg}

        try:
            ffmpeg_process = _spawn(_stream_cmd(), stream_logs)
        except Exception as e:
            ffmpeg_process = None
            _set_error(f"failed to start stream: {e}")
            return {"status": "error", "message": str(e)}

        # Catch immediate failures (camera busy, unsupported format, etc.)
        time.sleep(1)
        if ffmpeg_process.poll() is not None:
            _refresh()
            return {"status": "error", "message": "stream failed to start", "details": last_error["details"]}

        return {"status": "stream started"}


# ---------------------------------------------------------------------------
# Stream Stop
# End the ffmpeg process that is streaming to the RTSP server.
# If recording is active, do not stop the stream until recording is stopped first.
#   Ending the stream while recording will error out the recording process.
# ---------------------------------------------------------------------------
@app.post("/stream/stop")
def stop_stream():
    global ffmpeg_process

    with lock:
        _refresh()

        if ffmpeg_process is None:
            return {"status": "stream not running"}
        if recording_process is not None:
            return {"status": "stop recording before stopping stream"}

        try:
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=5)
        except Exception:
            ffmpeg_process.kill()
        finally:
            ffmpeg_process = None

        return {"status": "stream stopped"}


# ---------------------------------------------------------------------------
# Recording Start
# Start an ffmpeg process to:
#   - read the RTSP stream on localhost:8554 (no re-encode)
#   - save it to a uniquely named file in /recordings
# Fragmented MP4 is used so the file stays playable if the Pi loses power mid-recording.
# ---------------------------------------------------------------------------
@app.post("/recording/start")
def start_recording():
    global recording_process, recording_file

    with lock:
        _refresh()

        if recording_process is not None:
            return {"status": "recording already running"}

        if ffmpeg_process is None:
            return {"status": "stream not running"}

        if not _storage_ok():
            msg = f"recording storage not writable at {RECORDINGS_DIR}"
            _set_error(msg)
            return {"status": "error", "message": msg}

        filename = os.path.join(
            RECORDINGS_DIR,
            f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
        )

        cmd = [
            "ffmpeg",
            "-loglevel", "warning",
            "-rtsp_transport", "tcp",
            "-i", RTSP_URL,
            "-c:v", "copy",
            "-movflags", "frag_keyframe+empty_moov",
            filename,
        ]

        try:
            recording_process = _spawn(cmd, recording_logs)
            recording_file = filename
        except Exception as e:
            recording_process = None
            recording_file = None
            _set_error(f"failed to start recording: {e}")
            return {"status": "error", "message": str(e)}

        return {"status": "recording started", "file": filename}


# ---------------------------------------------------------------------------
# Recording Stop
# End the ffmpeg process that is recording the RTSP stream.
# SIGINT lets ffmpeg finish and close the file cleanly.
# ---------------------------------------------------------------------------
@app.post("/recording/stop")
def stop_recording():
    global recording_process, recording_file

    with lock:
        _refresh()

        if recording_process is None:
            return {"status": "recording not running"}

        saved = recording_file
        try:
            recording_process.send_signal(signal.SIGINT)
            recording_process.wait(timeout=10)
        except Exception:
            recording_process.kill()
        finally:
            recording_process = None
            recording_file = None

        return {"status": "recording stopped", "file": saved}


# ---------------------------------------------------------------------------
# Status
# Return the state of the stream and recording processes.
# ---------------------------------------------------------------------------
@app.get("/status")
def status():
    with lock:
        _refresh()
        return {
            "stream": "running" if ffmpeg_process else "stopped",
            "recording": "running" if recording_process else "stopped",
            "recording_file": recording_file,
        }


# ---------------------------------------------------------------------------
# Health
# Container health for the Master API: dependencies, process state, and last error.
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    with lock:
        _refresh()

        camera_ok = os.path.exists(CAMERA_DEVICE)
        mediamtx_ok = _port_open("127.0.0.1", RTSP_PORT)
        storage_ok = _storage_ok()

        return {
            "ok": camera_ok and mediamtx_ok and storage_ok,
            "camera_detected": camera_ok,
            "mediamtx_reachable": mediamtx_ok,
            "storage_writable": storage_ok,
            "stream": "running" if ffmpeg_process else "stopped",
            "recording": "running" if recording_process else "stopped",
            "last_error": last_error,
        }