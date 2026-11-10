"""Exercise public routes through real HTTP adapters with simulated peers."""

import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from master_api.config import Settings
from master_api.main import create_app


class ServerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.stream = "stopped"
        self.fail_motor = False

        def downstream(request):
            self.requests.append(request)
            if request.url.host == "controller-api":
                if request.url.path == "/status":
                    body = {"hardware_online": True,
                            "state": {"motor_us": 1550, "angle_deg": 0}}
                elif request.url.path == "/steer":
                    body = {"angle_deg": float(request.url.params["deg"])}
                elif request.url.path == "/forward" and self.fail_motor:
                    return httpx.Response(500)
                else:
                    body = {"status": request.url.path.lstrip("/")}
            elif request.url.host == "host.docker.internal":
                if request.url.path == "/stream/start":
                    # Simulate the real service's minimum response delay.
                    if request.extensions["timeout"]["read"] < 1:
                        raise httpx.ReadTimeout("startup needs one second", request=request)
                    self.stream = "running"
                    body = {"status": "started"}
                elif request.url.path == "/stream/stop":
                    if request.extensions["timeout"]["read"] < 5:
                        raise httpx.ReadTimeout("stop may need five seconds", request=request)
                    self.stream = "stopped"
                    body = {"status": "stopped"}
                else:
                    body = {"stream": self.stream}
            else:
                raise AssertionError(f"Unexpected destination: {request.url}")
            return httpx.Response(200, json=body)

        settings = Settings.from_env({
            "MASTER_API_CLIENT_MODE": "http",
            "MASTER_API_CONTROLLER_BASE_URL": "http://controller-api:8002",
            "MASTER_API_VIDEO_BASE_URL": "http://host.docker.internal:8001",
        })
        real_client = httpx.AsyncClient
        factory = lambda **kwargs: real_client(
            transport=httpx.MockTransport(downstream), **kwargs,
        )
        self.enterContext(patch("master_api.main.httpx.AsyncClient", side_effect=factory))
        self.client = self.enterContext(TestClient(create_app(settings=settings)))
        self.requests.clear()  # Startup checks are separate from each operation.

    def acquire(self):
        self.assertEqual(200, self.client.get("/api/v1/health/ready").status_code)
        response = self.client.post("/api/v1/control/lease", json={"client_id": "test"})
        self.assertEqual(201, response.status_code)
        return {"X-Control-Lease": response.json()["lease_id"]}

    def motion(self, headers):
        return self.client.put("/api/v1/control/motion", headers=headers, json={
            "steering": 0.25, "throttle": 0.1, "sequence": 1,
            "client_sent_at": "2026-11-03T12:00:00Z",
        })

    def test_public_motion_reaches_controller_and_release_sends_neutral(self):
        headers = self.acquire()
        self.assertEqual(200, self.motion(headers).status_code)
        self.assertEqual(204, self.client.delete("/api/v1/control/lease", headers=headers).status_code)
        posts = [r for r in self.requests if r.method == "POST"]
        self.assertEqual(["/steer", "/forward", "/neutral"], [r.url.path for r in posts])
        self.assertEqual("11.25", posts[0].url.params["deg"])
        self.assertEqual("35.0", posts[1].url.params["delta"])
        self.assertTrue(all(r.url.port == 8002 for r in posts))
        self.assertEqual(0.5, posts[1].extensions["timeout"]["read"])

    def test_startup_allows_control_without_a_readiness_request(self):
        state = self.client.get("/api/v1/system/state").json()
        self.assertEqual("READY", state["system_state"])
        response = self.client.post("/api/v1/control/lease", json={"client_id": "driver"})
        self.assertEqual(201, response.status_code)

    def test_public_video_commands_reach_host_with_sufficient_timeout(self):
        self.assertEqual({"stream": "running"}, self.client.post("/api/v1/video/stream/start").json())
        self.assertEqual({"stream": "stopped"}, self.client.post("/api/v1/video/stream/stop").json())
        self.assertEqual(["/stream/start", "/stream/stop"], [r.url.path for r in self.requests])
        self.assertTrue(all(r.url.port == 8001 for r in self.requests))

    def test_motor_failure_attempts_stop_and_invalidates_control(self):
        headers = self.acquire()
        self.fail_motor = True
        self.assertEqual(502, self.motion(headers).status_code)
        self.assertEqual("/neutral", self.requests[-1].url.path)
        state = self.client.get("/api/v1/system/state").json()
        self.assertEqual("EMERGENCY_STOP", state["system_state"])
        self.assertEqual(409, self.client.post("/api/v1/control/lease/heartbeat", headers=headers).status_code)

    def test_dependency_can_start_after_master(self):
        available = False

        def downstream(request):
            if request.url.host == "controller.test":
                if not available:
                    raise httpx.ConnectError("not started yet", request=request)
                if request.url.path == "/neutral":
                    return httpx.Response(200, json={"status": "neutral"})
                return httpx.Response(200, json={
                    "hardware_online": True, "state": {"motor_us": 1550, "angle_deg": 0},
                })
            return httpx.Response(200, json={"stream": "stopped"})

        # The outer fixture has patched the constructor; use the actual class
        # behind its existing client to build this independent runtime.
        real_client = type(self.client.app.state.services.hardware._http_client)
        factory = lambda **kwargs: real_client(transport=httpx.MockTransport(downstream), **kwargs)
        settings = Settings(client_mode="http", controller_base_url="http://controller.test",
                            video_base_url="http://video.test")
        with patch("master_api.main.httpx.AsyncClient", side_effect=factory):
            with TestClient(create_app(settings=settings)) as client:
                self.assertEqual(200, client.get("/ping").status_code)
                readiness = client.get("/api/v1/health/ready")
                self.assertEqual(503, readiness.status_code)
                self.assertFalse(readiness.json()["checks"]["hardware"]["ready"])
                self.assertTrue(readiness.json()["checks"]["video"]["ready"])
                self.assertEqual(409, client.post("/api/v1/control/lease",
                                                 json={"client_id": "driver"}).status_code)
                available = True
                self.assertEqual(201, client.post("/api/v1/control/lease",
                                                 json={"client_id": "driver"}).status_code)
