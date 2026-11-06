"""Offline tests: no camera, ffmpeg, or MediaMTX needed. FFmpeg is replaced with a fake process.

Run: pytest tests/test_offline.py
"""
import subprocess
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
import stream
from app.config import Settings
from app.main import create_app
from app.stream import StreamService


class FakeProcess:
    def __init__(self, cmd, exits_immediately=False, ignores_terminate=False):
        self.cmd = cmd
        self.returncode = 1 if exits_immediately else None
        self.ignores_terminate = ignores_terminate
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        if not self.ignores_terminate:
            self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired(self.cmd, timeout)
        return self.returncode


class Launched(list):
    """Every fake process created so far. Set `options` to change how the next one behaves."""

    def __init__(self):
        super().__init__()
        self.options = {}


@pytest.fixture
def launched(monkeypatch):
    procs = Launched()

    def fake_popen(cmd):
        proc = FakeProcess(cmd, **procs.options)
        procs.append(proc)
        return proc

    monkeypatch.setattr(stream.subprocess, "Popen", fake_popen)
    return procs


@pytest.fixture
def client():
    service = StreamService(Settings(), startup_check_seconds=0, stop_timeout_seconds=0)
    return TestClient(create_app(service))


def test_status_starts_stopped(client):
    assert client.get("/status").json() == {"stream": "stopped"}


def test_start_and_stop_cycle(client, launched):
    assert client.post("/stream/start").json() == {"status": "started"}
    assert client.get("/status").json() == {"stream": "running"}
    assert client.post("/stream/start").json() == {"status": "already running"}
    assert len(launched) == 1

    assert client.post("/stream/stop").json() == {"status": "stopped"}
    assert client.get("/status").json() == {"stream": "stopped"}
    assert client.post("/stream/stop").json() == {"status": "not running"}


def test_start_failure_returns_500(client, launched):
    launched.options["exits_immediately"] = True
    response = client.post("/stream/start")
    assert response.status_code == 500
    assert response.json() == {"detail": "ffmpeg failed to start"}
    assert client.get("/status").json() == {"stream": "stopped"}


def test_stop_kills_ffmpeg_if_it_ignores_terminate(client, launched):
    launched.options["ignores_terminate"] = True
    client.post("/stream/start")
    assert client.post("/stream/stop").json() == {"status": "stopped"}
    assert launched[0].killed


def test_crashed_ffmpeg_shows_as_stopped(client, launched):
    client.post("/stream/start")
    launched[0].returncode = 1  # e.g. camera unplugged
    assert client.get("/status").json() == {"stream": "stopped"}


def test_ffmpeg_command_uses_settings():
    settings = Settings(camera_device="/dev/video2", video_size="1280x720", framerate=25,
                        bitrate="2M", bufsize="1M", rtsp_port=9000)
    cmd = StreamService(settings).build_command()

    def arg(flag):
        return cmd[cmd.index(flag) + 1]

    assert cmd[0] == "ffmpeg"
    assert arg("-i") == "/dev/video2"
    assert arg("-video_size") == "1280x720"
    assert arg("-framerate") == "25"
    assert arg("-g") == "25"
    assert arg("-b:v") == "2M"
    assert arg("-bufsize") == "1M"
    assert cmd[-1] == "rtsp://127.0.0.1:9000/stream"


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("VIDEO_SIZE", "1280x720")
    monkeypatch.setenv("FRAMERATE", "60")
    monkeypatch.setenv("RTSP_PORT", "9000")
    settings = Settings.from_env()
    assert settings.video_size == "1280x720"
    assert settings.framerate == 60
    assert settings.rtsp_url == "rtsp://127.0.0.1:9000/stream"
    assert settings.camera_device == "/dev/video0"  # default kept


def test_settings_reject_bad_values(monkeypatch):
    monkeypatch.setenv("VIDEO_SIZE", "big")
    with pytest.raises(ValidationError):
        Settings.from_env()
