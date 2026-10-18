"""Tests for liveness, readiness, and API discovery."""

from tests.base import ApiTestCase


class HealthEndpointTests(ApiTestCase):
    def test_liveness_reports_alive(self) -> None:
        response = self.client.get("/api/v1/health/live")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "alive"}, response.json())

    def test_readiness_reports_all_mock_services(self) -> None:
        response = self.client.get("/api/v1/health/ready")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertTrue(body["ready"])
        self.assertEqual("READY", body["system_state"])
        self.assertTrue(body["checks"]["hardware"]["ready"])
        self.assertTrue(body["checks"]["video"]["ready"])

    def test_readiness_returns_503_when_hardware_is_unavailable(self) -> None:
        self.hardware.ready = False

        response = self.client.get("/api/v1/health/ready")

        self.assertEqual(503, response.status_code)
        self.assertFalse(response.json()["ready"])
        self.assertEqual("DEGRADED", response.json()["system_state"])

    def test_openapi_lists_skeleton_routes(self) -> None:
        paths = self.client.get("/openapi.json").json()["paths"]

        expected = {
            "/api/v1/control/motion",
            "/api/v1/health/live",
            "/api/v1/health/ready",
            "/api/v1/system/state",
            "/api/v1/telemetry",
            "/api/v1/video/recordings",
            "/api/v1/video/recordings/current",
            "/api/v1/video/status",
        }
        self.assertEqual(expected, set(paths))

    def test_system_state_reports_latest_health_transition(self) -> None:
        self.video.ready = False
        self.client.get("/api/v1/health/ready")

        response = self.client.get("/api/v1/system/state")

        self.assertEqual(200, response.status_code)
        self.assertEqual("DEGRADED", response.json()["system_state"])
        self.assertEqual("Video service is unavailable", response.json()["reason"])

    def test_state_websocket_pushes_health_transitions(self) -> None:
        with self.client.websocket_connect("/api/v1/system/state/ws") as websocket:
            initial = websocket.receive_json()
            self.video.ready = False
            self.client.get("/api/v1/health/ready")
            changed = websocket.receive_json()

        self.assertEqual("READY", initial["system_state"])
        self.assertEqual("DEGRADED", changed["system_state"])
        self.assertEqual("Video service is unavailable", changed["reason"])
