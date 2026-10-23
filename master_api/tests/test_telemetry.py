"""Tests for combined telemetry snapshots."""

from tests.base import ApiTestCase


class TelemetryEndpointTests(ApiTestCase):
    def test_initial_snapshot_contains_hardware_and_video_data(self) -> None:
        response = self.client.get("/api/v1/telemetry")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(0.0, body["hardware"]["steering"])
        self.assertEqual(0.0, body["hardware"]["throttle"])
        self.assertIsNone(body["hardware"]["last_sequence"])
        self.assertEqual("idle", body["video"]["state"])
        self.assertIn("collected_at", body)
