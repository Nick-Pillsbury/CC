"""Contract and failure tests for asynchronous downstream HTTP clients."""

import json
import unittest

import httpx
from fastapi.testclient import TestClient

from master_api.clients.errors import (
    DownstreamHttpError,
    DownstreamResponseError,
    DownstreamTimeoutError,
    DownstreamUnavailableError,
)
from master_api.clients.http import HttpHardwareClient, HttpVideoClient
from master_api.dependencies import ServiceContainer
from master_api.main import create_app
from master_api.models import MotionCommand


HEALTH = {"ready": True, "detail": "ready"}
MOTION = {
    "accepted_sequence": 7,
    "requested": {"steering": 0.25, "throttle": 0.5},
    "applied": {"steering": 0.25, "throttle": 0.5},
    "limited_by": [],
    "hardware_received_at": "2026-10-09T12:00:00Z",
}
TELEMETRY = {
    "steering": 0.25,
    "throttle": 0.5,
    "last_sequence": 7,
    "sampled_at": "2026-10-09T12:00:00Z",
}
RECORDING = {
    "state": "recording",
    "recording_id": "recording-1",
    "request_id": "request-1",
    "started_at": "2026-10-09T12:00:00Z",
    "stopped_at": None,
}


class HttpClientSuccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            responses = {
                ("hardware.test", "GET", "/v1/health/ready"): HEALTH,
                ("hardware.test", "PUT", "/v1/motion"): MOTION,
                ("hardware.test", "GET", "/v1/telemetry"): TELEMETRY,
                ("video.test", "GET", "/v1/health/ready"): HEALTH,
                ("video.test", "POST", "/v1/recordings"): RECORDING,
                ("video.test", "DELETE", "/v1/recordings/current"): {
                    **RECORDING,
                    "state": "stopped",
                    "stopped_at": "2026-10-09T12:01:00Z",
                },
                ("video.test", "GET", "/v1/status"): RECORDING,
            }
            body = responses[(request.url.host, request.method, request.url.path)]
            return httpx.Response(200, json=body)

        self.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.hardware = HttpHardwareClient(
            self.http_client,
            "http://hardware.test",
        )
        self.video = HttpVideoClient(self.http_client, "http://video.test")

    async def asyncTearDown(self) -> None:
        await self.http_client.aclose()

    async def test_hardware_contract_calls(self) -> None:
        command = MotionCommand.model_validate(
            {
                "steering": 0.25,
                "throttle": 0.5,
                "sequence": 7,
                "client_sent_at": "2026-10-09T11:59:59Z",
            }
        )

        health = await self.hardware.health()
        motion = await self.hardware.apply_motion(command)
        telemetry = await self.hardware.telemetry()

        self.assertTrue(health.ready)
        self.assertEqual(7, motion.accepted_sequence)
        self.assertEqual(7, telemetry.last_sequence)
        sent_motion = self.requests[1]
        self.assertEqual("PUT", sent_motion.method)
        self.assertEqual(7, json.loads(sent_motion.content)["sequence"])

    async def test_video_contract_calls(self) -> None:
        health = await self.video.health()
        started = await self.video.start_recording("request-1")
        stopped = await self.video.stop_recording()
        current = await self.video.status()

        self.assertTrue(health.ready)
        self.assertEqual("recording-1", started.recording_id)
        self.assertEqual("stopped", stopped.state.value)
        self.assertEqual("recording-1", current.recording_id)
        start_request = self.requests[1]
        self.assertEqual(
            {"request_id": "request-1"},
            json.loads(start_request.content),
        )


class HttpClientFailureTests(unittest.IsolatedAsyncioTestCase):
    async def _hardware_with_handler(
        self,
        handler: object,
    ) -> tuple[httpx.AsyncClient, HttpHardwareClient]:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return client, HttpHardwareClient(client, "http://hardware.test")

    async def test_timeout_has_stable_failure(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("simulated timeout", request=request)

        client, hardware = await self._hardware_with_handler(handler)
        async with client:
            with self.assertRaises(DownstreamTimeoutError) as caught:
                await hardware.telemetry()

        self.assertEqual("downstream_timeout", caught.exception.code)
        self.assertEqual(504, caught.exception.status_code)

    async def test_refused_connection_has_stable_failure(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("simulated refusal", request=request)

        client, hardware = await self._hardware_with_handler(handler)
        async with client:
            with self.assertRaises(DownstreamUnavailableError) as caught:
                await hardware.health()

        self.assertEqual("downstream_unavailable", caught.exception.code)
        self.assertEqual(503, caught.exception.status_code)

    async def test_500_has_stable_failure(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"secret": "must not escape"})

        client, hardware = await self._hardware_with_handler(handler)
        async with client:
            with self.assertRaises(DownstreamHttpError) as caught:
                await hardware.health()

        self.assertEqual("downstream_http_error", caught.exception.code)
        self.assertNotIn("secret", str(caught.exception))

    async def test_invalid_response_has_stable_failure(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ready": "not-a-boolean"})

        client, hardware = await self._hardware_with_handler(handler)
        async with client:
            with self.assertRaises(DownstreamResponseError) as caught:
                await hardware.health()

        self.assertEqual("downstream_response_invalid", caught.exception.code)


class DownstreamErrorEndpointTests(unittest.TestCase):
    def test_timeout_is_returned_in_public_error_shape(self) -> None:
        class TimedOutHardware:
            async def apply_motion(self, command: MotionCommand) -> object:
                del command
                raise DownstreamTimeoutError(
                    "hardware",
                    "The hardware service did not respond before its deadline.",
                )

        app = create_app(
            ServiceContainer(
                hardware=TimedOutHardware(),  # type: ignore[arg-type]
                video=object(),  # type: ignore[arg-type]
            )
        )
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/control/motion",
                json={
                    "steering": 0.0,
                    "throttle": 0.0,
                    "sequence": 1,
                    "client_sent_at": "2026-10-09T12:00:00Z",
                },
            )

        self.assertEqual(504, response.status_code)
        self.assertEqual(
            {
                "error": {
                    "code": "downstream_timeout",
                    "message": "The hardware service did not respond before its deadline.",
                    "component": "hardware",
                    "retryable": True,
                }
            },
            response.json(),
        )
