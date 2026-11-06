"""Manages the FFmpeg process that captures the camera and publishes to MediaMTX."""
import asyncio
import logging
import subprocess
from config import Settings

log = logging.getLogger(__name__)


class StreamStartError(RuntimeError):
    """FFmpeg exited right after launch (camera busy, bad format, etc.)."""


class StreamService:
    def __init__(
        self,
        settings: Settings,
        startup_check_seconds: float = 1.0,
        stop_timeout_seconds: float = 5.0,
    ):
        self.settings = settings
        self._startup_check_seconds = startup_check_seconds
        self._stop_timeout_seconds = stop_timeout_seconds
        self._proc: subprocess.Popen | None = None
        self._lock = asyncio.Lock()  # stops overlapping start/stop calls racing

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def build_command(self) -> list[str]:
        s = self.settings
        fps = str(s.framerate)
        return [
            "ffmpeg", "-loglevel", "error",
            "-fflags", "nobuffer", "-flags", "low_delay",
            "-use_wallclock_as_timestamps", "1",
            "-f", "v4l2", "-input_format", "mjpeg",
            "-video_size", s.video_size, "-framerate", fps,
            "-i", s.camera_device,
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-profile:v", "main", "-pix_fmt", "yuv420p",
            "-g", fps, "-bf", "0",
            "-x264-params", "repeat-headers=1",
            "-b:v", s.bitrate, "-maxrate", s.bitrate, "-bufsize", s.bufsize,
            "-f", "rtsp", "-rtsp_transport", "tcp", s.rtsp_url,
        ]

    async def start(self) -> bool:
        """Start streaming. Returns False if it was already running."""
        async with self._lock:
            if self.is_running:
                return False

            log.info("Starting stream from %s to %s", self.settings.camera_device, self.settings.rtsp_url)
            self._proc = subprocess.Popen(self.build_command())

            # Catch immediate failures (camera busy, bad format).
            await asyncio.sleep(self._startup_check_seconds)
            if not self.is_running:
                code = self._proc.returncode
                self._proc = None
                log.error("ffmpeg exited during startup with code %s", code)
                raise StreamStartError(f"ffmpeg exited with code {code}")
            return True

    async def stop(self) -> bool:
        """Stop streaming. Returns False if it was not running."""
        async with self._lock:
            if not self.is_running:
                self._proc = None
                return False

            log.info("Stopping stream")
            # Waiting on the process blocks, so keep it off the event loop.
            await asyncio.to_thread(self._terminate, self._proc, self._stop_timeout_seconds)
            self._proc = None
            return True

    @staticmethod
    def _terminate(proc: subprocess.Popen, timeout: float) -> None:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            log.warning("ffmpeg did not exit after %ss, killing it", timeout)
            proc.kill()
            proc.wait()
