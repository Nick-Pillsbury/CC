import asyncio
import os
import subprocess

from fastapi import FastAPI, HTTPException

app = FastAPI()

CAMERA_DEVICE = os.getenv("CAMERA_DEVICE", "/dev/video0")
VIDEO_SIZE = os.getenv("VIDEO_SIZE", "1920x1080")
FRAMERATE = os.getenv("FRAMERATE", "30")
BITRATE = os.getenv("BITRATE", "3M")
BUFSIZE = os.getenv("BUFSIZE", "1500k")
RTSP_URL = f"rtsp://127.0.0.1:{os.getenv('RTSP_PORT', '8554')}/stream"

proc = None


def running():
    return proc is not None and proc.poll() is None


@app.post("/stream/start")
async def start_stream():
    global proc
    if running():
        return {"status": "already running"}

    proc = subprocess.Popen([
        "ffmpeg", "-loglevel", "error",
        "-fflags", "nobuffer", "-flags", "low_delay",
        "-use_wallclock_as_timestamps", "1",
        "-f", "v4l2", "-input_format", "mjpeg",
        "-video_size", VIDEO_SIZE, "-framerate", FRAMERATE,
        "-i", CAMERA_DEVICE,
        "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
        "-profile:v", "main", "-pix_fmt", "yuv420p",
        "-g", FRAMERATE, "-bf", "0",
        "-x264-params", "repeat-headers=1",
        "-b:v", BITRATE, "-maxrate", BITRATE, "-bufsize", BUFSIZE,
        "-f", "rtsp", "-rtsp_transport", "tcp", RTSP_URL,
    ])

    await asyncio.sleep(1)  # catch immediate failures (camera busy, bad format)
    if not running():
        raise HTTPException(500, "ffmpeg failed to start")
    return {"status": "started"}


@app.post("/stream/stop")
async def stop_stream():
    global proc
    if not running():
        return {"status": "not running"}
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    proc = None
    return {"status": "stopped"}


@app.get("/status")
async def status():
    return {"stream": "running" if running() else "stopped"}