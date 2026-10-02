"""Tests for mock-backed car-control endpoints."""

from tests.base import ApiTestCase


class ControlEndpointTests(ApiTestCase):
    def test_motion_command_is_forwarded_to_mock_hardware(self) -> None:
        response = self.client.put(
            "/api/v1/control/motion",
            json={
                "steering": -0.35,
                "throttle": 0.6,
                "sequence": 12,
                "client_sent_at": "2026-10-02T18:25:43.511Z",
            },
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(12, body["accepted_sequence"])
        self.assertEqual(-0.35, body["applied"]["steering"])
        self.assertEqual(0.6, body["applied"]["throttle"])
        self.assertEqual(12, self.hardware.last_sequence)

    def test_motion_values_outside_normalized_range_are_rejected(self) -> None:
        response = self.client.put(
            "/api/v1/control/motion",
            json={
                "steering": 1.01,
                "throttle": 0.0,
                "sequence": 1,
                "client_sent_at": "2026-10-02T18:25:43.511Z",
            },
        )

        self.assertEqual(422, response.status_code)
        self.assertIsNone(self.hardware.last_sequence)

    def test_motion_rejects_unknown_fields(self) -> None:
        response = self.client.put(
            "/api/v1/control/motion",
            json={
                "steering": 0.0,
                "throttle": 0.0,
                "sequence": 1,
                "client_sent_at": "2026-10-02T18:25:43.511Z",
                "unsafe_override": True,
            },
        )

        self.assertEqual(422, response.status_code)
        self.assertIsNone(self.hardware.last_sequence)

    def test_applied_motion_appears_in_telemetry(self) -> None:
        self.client.put(
            "/api/v1/control/motion",
            json={
                "steering": 0.25,
                "throttle": -0.4,
                "sequence": 9,
                "client_sent_at": "2026-10-02T18:25:43.511Z",
            },
        )

        telemetry = self.client.get("/api/v1/telemetry").json()["hardware"]

        self.assertEqual(0.25, telemetry["steering"])
        self.assertEqual(-0.4, telemetry["throttle"])
        self.assertEqual(9, telemetry["last_sequence"])
