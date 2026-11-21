"""Deployment tests: run against the live containers on the car.

These start the real camera stream, then put it back the way it was.
Skipped unless VIDEO_API_URL is set.

Run:
    VIDEO_API_URL=http://10.0.0.51:8001 MEDIAMTX_URL=http://10.0.0.51:8889 pytest tests/test_deployment.py
"""
import os
import httpx
import pytest

API_URL = os.getenv("VIDEO_API_URL")
MEDIAMTX_URL = os.getenv("MEDIAMTX_URL")

pytestmark = pytest.mark.skipif(not API_URL, reason="VIDEO_API_URL not set")


@pytest.fixture
def api():
    with httpx.Client(base_url=API_URL, timeout=15) as client:
        yield client


def stream_state(api) -> str:
    response = api.get("/status")
    response.raise_for_status()
    return response.json()["stream"]


def test_status_reachable(api):
    assert stream_state(api) in ("running", "stopped")


def test_stream_start_and_stop(api):
    was_running = stream_state(api) == "running"
    try:
        response = api.post("/stream/start")
        assert response.status_code == 200, response.text
        assert response.json()["status"] in ("started", "already running")
        assert stream_state(api) == "running"
    finally:
        if not was_running:
            assert api.post("/stream/stop").json()["status"] == "stopped"
            assert stream_state(api) == "stopped"


@pytest.mark.skipif(not MEDIAMTX_URL, reason="MEDIAMTX_URL not set")
def test_mediamtx_webrtc_page_reachable():
    response = httpx.get(f"{MEDIAMTX_URL}/stream", timeout=5)
    assert response.status_code == 200
