"""Contract and failure tests for asynchronous downstream HTTP clients."""

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
from master_api.models import MotionCommand, SystemState
from master_api.state import SystemStateMachine


CONTROLLER_STATUS = {
    "hardware_online": True,
    "frequency_hz": 50,
    "state": {
        "motor_us": 1725.0,
        "steering_us": 1562.5,
        "angle_deg": 11.25,
    },
}


class HttpClientSuccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            responses = {
                ("controller.test", "GET", "/status"): CONTROLLER_STATUS,
                ("controller.test", "POST", "/steer"): {
                    "angle_deg": 11.25,
                    "steering_us": 1562.5,
                },
                ("controller.test", "POST", "/forward"): {
                    "status": "forward",
                    "motor_us": 1725.0,
                },
                ("controller.test", "POST", "/backward"): {
                    "status": "backward",
                    "motor_us": 1375.0,
                },
                ("controller.test", "POST", "/neutral"): {
                    "status": "neutral",
                },
                ("video.test", "GET", "/status"): {"stream": "stopped"},
                ("video.test", "POST", "/stream/start"): {"status": "started"},
                ("video.test", "POST", "/stream/stop"): {"status": "stopped"},
            }
            body = responses[(request.url.host, request.method, request.url.path)]
            return httpx.Response(200, json=body)

        self.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.hardware = HttpHardwareClient(
            self.http_client,
            "http://controller.test",
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
        self.assertEqual(0.25, telemetry.steering)
        self.assertEqual(0.5, telemetry.throttle)

        steering_request = self.requests[1]
        motor_request = self.requests[2]
        self.assertEqual("/steer", steering_request.url.path)
        self.assertEqual("11.25", steering_request.url.params["deg"])
        self.assertEqual("/forward", motor_request.url.path)
        self.assertEqual("175.0", motor_request.url.params["delta"])

    async def test_zero_throttle_stops_before_steering(self) -> None:
        command = MotionCommand.model_validate(
            {
                "steering": 0.25,
                "throttle": 0.0,
                "sequence": 8,
                "client_sent_at": "2026-10-09T11:59:59Z",
            }
        )

        await self.hardware.apply_motion(command)

        self.assertEqual("/neutral", self.requests[0].url.path)
        self.assertEqual("/steer", self.requests[1].url.path)

    async def test_negative_throttle_uses_backward(self) -> None:
        command = MotionCommand.model_validate(
            {
                "steering": 0.0,
                "throttle": -0.5,
                "sequence": 9,
                "client_sent_at": "2026-10-09T11:59:59Z",
            }
        )

        await self.hardware.apply_motion(command)

        self.assertEqual("/steer", self.requests[0].url.path)
        self.assertEqual("/backward", self.requests[1].url.path)
        self.assertEqual("175.0", self.requests[1].url.params["delta"])

    async def test_video_contract_calls(self) -> None:
        health = await self.video.health()
        started = await self.video.start_stream()
        stopped = await self.video.stop_stream()
        current = await self.video.status()

        self.assertTrue(health.ready)
        self.assertEqual("running", started.stream.value)
        self.assertEqual("stopped", stopped.stream.value)
        self.assertEqual("stopped", current.stream.value)
        self.assertEqual("/stream/start", self.requests[1].url.path)
        self.assertEqual("/stream/stop", self.requests[2].url.path)


class HttpClientFailureTests(unittest.IsolatedAsyncioTestCase):
    async def _hardware_with_handler(
        self,
        handler: object,
    ) -> tuple[httpx.AsyncClient, HttpHardwareClient]:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return client, HttpHardwareClient(client, "http://controller.test")

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
                state_machine=SystemStateMachine(SystemState.CONTROLLED),
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
