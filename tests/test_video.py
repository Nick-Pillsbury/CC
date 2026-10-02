"""Tests for mock-backed video recording endpoints."""

from tests.base import ApiTestCase


class VideoEndpointTests(ApiTestCase):
    def test_recording_can_start_and_stop(self) -> None:
        started = self.client.post(
            "/api/v1/video/recordings",
            json={"request_id": "recording-request-1"},
        )

        self.assertEqual(201, started.status_code)
        self.assertEqual("recording", started.json()["state"])
        self.assertIsNotNone(started.json()["recording_id"])

        stopped = self.client.delete("/api/v1/video/recordings/current")

        self.assertEqual(200, stopped.status_code)
        self.assertEqual("stopped", stopped.json()["state"])
        self.assertIsNotNone(stopped.json()["stopped_at"])

    def test_repeated_start_returns_same_mock_recording(self) -> None:
        first = self.client.post(
            "/api/v1/video/recordings",
            json={"request_id": "recording-request-2"},
        )
        second = self.client.post(
            "/api/v1/video/recordings",
            json={"request_id": "recording-request-2"},
        )

        self.assertEqual(
            first.json()["recording_id"],
            second.json()["recording_id"],
        )

    def test_video_status_starts_idle(self) -> None:
        response = self.client.get("/api/v1/video/status")

        self.assertEqual(200, response.status_code)
        self.assertEqual("idle", response.json()["state"])

    def test_empty_recording_request_id_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/video/recordings",
            json={"request_id": ""},
        )

        self.assertEqual(422, response.status_code)
