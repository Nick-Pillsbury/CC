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
# Config (override via environment variables, e.g. in docker-compose)
# ---------------------------------------------------------------------------
CAMERA_DEVICE = os.getenv("CAMERA_DEVICE", "/dev/video0")
VIDEO_SIZE = os.getenv("VIDEO_SIZE", "1920x1080")
FRAMERATE = os.getenv("FRAMERATE", "30")
BITRATE = os.getenv("BITRATE", "3M")     # lower (e.g. 1.5M) for weak cellular
BUFSIZE = os.getenv("BUFSIZE", "1500k")  # ~0.5s of video keeps latency low
RTSP_PORT = int(os.getenv("RTSP_PORT", "8554"))
RTSP_URL = f"rtsp://127.0.0.1:{RTSP_PORT}/stream"
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", "/recordings")

lock = threading.Lock()
last_error = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def set_error(message, details=None):
    global last_error
    last_error = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "message": message,
        "details": list(details)[-5:] if details else [],
    }


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def storage_ok():
    try:
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        return os.access(RECORDINGS_DIR, os.W_OK)
    except OSError:
        return False


class Job:
    """One ffmpeg process plus its recent stderr output."""

    def __init__(self, name):
        self.name = name
        self.proc = None
        self.file = None
        self.logs = deque(maxlen=20)

    def running(self):
        """True if running. Records an error if it died on its own."""
        if self.proc is None:
            return False
        if self.proc.poll() is None:
            return True
        set_error(f"{self.name} exited unexpectedly (code {self.proc.returncode})", self.logs)
        self.proc = self.file = None
        return False

    def start(self, cmd, file=None):
        self.logs.clear()
        self.file = file
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        threading.Thread(target=self._read_logs, args=(self.proc,), daemon=True).start()

    def _read_logs(self, proc):
        for line in proc.stderr:
            self.logs.append(line.decode(errors="replace").rstrip())

    def stop(self, sig=signal.SIGTERM, timeout=5):
        try:
            self.proc.send_signal(sig)
            self.proc.wait(timeout=timeout)
        except Exception:
            self.proc.kill()
        finally:
            self.proc = self.file = None


stream = Job("stream")
recording = Job("recording")


# ---------------------------------------------------------------------------
# ffmpeg commands
# ---------------------------------------------------------------------------
def stream_cmd():
    return [
        "ffmpeg", "-loglevel", "warning",
        # input: camera MJPEG
        "-fflags", "nobuffer", "-flags", "low_delay",
        "-use_wallclock_as_timestamps", "1",
        "-f", "v4l2", "-input_format", "mjpeg",
        "-video_size", VIDEO_SIZE, "-framerate", FRAMERATE,
        "-i", CAMERA_DEVICE,
        "-an",
        # output: low-latency H.264, WebRTC-compatible
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-profile:v", "baseline", "-pix_fmt", "yuv420p",
        "-g", FRAMERATE, "-bf", "0",
        "-x264-params", "repeat-headers=1",
        "-b:v", BITRATE, "-maxrate", BITRATE, "-bufsize", BUFSIZE,
        "-f", "rtsp", "-rtsp_transport", "tcp", RTSP_URL,
    ]


def recording_cmd(filename):
    # Fragmented MP4 stays playable if power is lost mid-recording.
    return [
        "ffmpeg", "-loglevel", "warning",
        "-rtsp_transport", "tcp", "-i", RTSP_URL,
        "-c:v", "copy", "-an",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        filename,
    ]


# ---------------------------------------------------------------------------
# Stream
# ---------------------------------------------------------------------------
@app.post("/stream/start")
def start_stream():
    with lock:
        if stream.running():
            return {"status": "stream already running"}
        if not os.path.exists(CAMERA_DEVICE):
            msg = f"camera not found at {CAMERA_DEVICE}"
            set_error(msg)
            return {"status": "error", "message": msg}
        if not port_open(RTSP_PORT):
            msg = f"MediaMTX not reachable on port {RTSP_PORT}"
            set_error(msg)
            return {"status": "error", "message": msg}

        try:
            stream.start(stream_cmd())
        except Exception as e:
            set_error(f"failed to start stream: {e}")
            return {"status": "error", "message": str(e)}

        time.sleep(1)  # catch immediate failures (camera busy, bad format)
        if not stream.running():
            return {"status": "error", "message": "stream failed to start",
                    "details": last_error["details"]}
        return {"status": "stream started"}


@app.post("/stream/stop")
def stop_stream():
    with lock:
        if not stream.running():
            return {"status": "stream not running"}
        if recording.running():
            return {"status": "stop recording before stopping stream"}
        stream.stop()
        return {"status": "stream stopped"}


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------
@app.post("/recording/start")
def start_recording():
    with lock:
        if recording.running():
            return {"status": "recording already running"}
        if not stream.running():
            return {"status": "stream not running"}
        if not storage_ok():
            msg = f"recording storage not writable at {RECORDINGS_DIR}"
            set_error(msg)
            return {"status": "error", "message": msg}

        filename = os.path.join(
            RECORDINGS_DIR, f"recording_{datetime.now():%Y%m%d_%H%M%S}.mp4"
        )
        try:
            recording.start(recording_cmd(filename), file=filename)
        except Exception as e:
            set_error(f"failed to start recording: {e}")
            return {"status": "error", "message": str(e)}
        return {"status": "recording started", "file": filename}


@app.post("/recording/stop")
def stop_recording():
    with lock:
        if not recording.running():
            return {"status": "recording not running"}
        saved = recording.file
        recording.stop(sig=signal.SIGINT, timeout=10)  # SIGINT = clean file close
        return {"status": "recording stopped", "file": saved}


# ---------------------------------------------------------------------------
# Status / Health
# ---------------------------------------------------------------------------
@app.get("/status")
def status():
    with lock:
        return {
            "stream": "running" if stream.running() else "stopped",
            "recording": "running" if recording.running() else "stopped",
            "recording_file": recording.file,
        }


@app.get("/health")
def health():
    with lock:
        camera = os.path.exists(CAMERA_DEVICE)
        mediamtx = port_open(RTSP_PORT)
        storage = storage_ok()
        return {
            "ok": camera and mediamtx and storage,
            "camera_detected": camera,
            "mediamtx_reachable": mediamtx,
            "storage_writable": storage,
            "stream": "running" if stream.running() else "stopped",
            "recording": "running" if recording.running() else "stopped",
            "last_error": last_error,
        }