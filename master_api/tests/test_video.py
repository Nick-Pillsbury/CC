"""Tests for mock-backed video stream endpoints."""

from tests.base import ApiTestCase


class VideoEndpointTests(ApiTestCase):
    def test_stream_can_start_and_stop(self) -> None:
        started = self.client.post("/api/v1/video/stream/start")

        self.assertEqual(200, started.status_code)
        self.assertEqual("running", started.json()["stream"])

        stopped = self.client.post("/api/v1/video/stream/stop")

        self.assertEqual(200, stopped.status_code)
        self.assertEqual("stopped", stopped.json()["stream"])

    def test_repeated_start_keeps_stream_running(self) -> None:
        first = self.client.post("/api/v1/video/stream/start")
        second = self.client.post("/api/v1/video/stream/start")

        self.assertEqual("running", first.json()["stream"])
        self.assertEqual("running", second.json()["stream"])

    def test_video_status_starts_stopped(self) -> None:
        response = self.client.get("/api/v1/video/status")

        self.assertEqual(200, response.status_code)
        self.assertEqual("stopped", response.json()["stream"])
