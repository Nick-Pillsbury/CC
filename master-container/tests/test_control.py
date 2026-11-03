"""Tests for mock-backed car-control endpoints."""

from datetime import datetime

from tests.base import ApiTestCase
from master_api.models import SystemState


class ControlEndpointTests(ApiTestCase):
    initial_system_state = SystemState.READY

    def setUp(self) -> None:
        super().setUp()
        response = self.client.post(
            "/api/v1/control/lease",
            json={"client_id": "test-driver"},
        )
        self.assertEqual(201, response.status_code)
        self.lease_headers = {"X-Control-Lease": response.json()["lease_id"]}

    def test_motion_command_is_forwarded_to_mock_hardware(self) -> None:
        response = self.client.put(
            "/api/v1/control/motion",
            headers=self.lease_headers,
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
            headers=self.lease_headers,
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
            headers=self.lease_headers,
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
            headers=self.lease_headers,
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

    def test_motion_is_rejected_outside_controlled_state(self) -> None:
        released = self.client.delete(
            "/api/v1/control/lease",
            headers=self.lease_headers,
        )
        self.assertEqual(204, released.status_code)

        response = self.client.put(
            "/api/v1/control/motion",
            headers=self.lease_headers,
            json={
                "steering": 0.0,
                "throttle": 0.0,
                "sequence": 10,
                "client_sent_at": "2026-10-02T18:25:43.511Z",
            },
        )

        self.assertEqual(409, response.status_code)
        self.assertEqual("control_lease_inactive", response.json()["error"]["code"])
        self.assertIsNone(self.hardware.last_sequence)

    def test_second_driver_cannot_replace_active_lease(self) -> None:
        response = self.client.post(
            "/api/v1/control/lease",
            json={"client_id": "second-driver"},
        )

        self.assertEqual(409, response.status_code)
        self.assertEqual("control_lease_held", response.json()["error"]["code"])

    def test_heartbeat_extends_active_lease(self) -> None:
        before = self.client.post(
            "/api/v1/control/lease/heartbeat",
            headers=self.lease_headers,
        )
        after = self.client.post(
            "/api/v1/control/lease/heartbeat",
            headers=self.lease_headers,
        )

        self.assertEqual(200, after.status_code)
        self.assertGreaterEqual(
            datetime.fromisoformat(after.json()["expires_at"]),
            datetime.fromisoformat(before.json()["expires_at"]),
        )

    def test_stale_motion_sequence_is_rejected(self) -> None:
        command = {
            "steering": 0.0,
            "throttle": 0.2,
            "sequence": 25,
            "client_sent_at": "2026-10-02T18:25:43.511Z",
        }
        accepted = self.client.put(
            "/api/v1/control/motion",
            headers=self.lease_headers,
            json=command,
        )
        stale = self.client.put(
            "/api/v1/control/motion",
            headers=self.lease_headers,
            json=command,
        )

        self.assertEqual(200, accepted.status_code)
        self.assertEqual(409, stale.status_code)
        self.assertEqual("motion_sequence_stale", stale.json()["error"]["code"])

    def test_emergency_stop_neutralizes_and_can_be_reset(self) -> None:
        self.client.put(
            "/api/v1/control/motion",
            headers=self.lease_headers,
            json={
                "steering": 0.4,
                "throttle": 0.5,
                "sequence": 30,
                "client_sent_at": "2026-10-02T18:25:43.511Z",
            },
        )

        stopped = self.client.post("/api/v1/control/emergency-stop")
        reset = self.client.post("/api/v1/control/emergency-stop/reset")

        self.assertEqual(200, stopped.status_code)
        self.assertEqual("EMERGENCY_STOP", stopped.json()["system_state"])
        self.assertEqual(0.0, self.hardware.throttle)
        self.assertEqual(0.0, self.hardware.steering)
        self.assertEqual(200, reset.status_code)
        self.assertEqual("READY", reset.json()["system_state"])
