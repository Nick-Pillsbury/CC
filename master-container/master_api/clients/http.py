"""Asynchronous HTTP clients for hardware and video containers."""

from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from master_api.clients.errors import (
    DownstreamHttpError,
    DownstreamResponseError,
    DownstreamTimeoutError,
    DownstreamUnavailableError,
)
from master_api.models import (
    ComponentHealth,
    ControlValues,
    HardwareTelemetry,
    MotionCommand,
    MotionResponse,
    StreamState,
    VideoStatus,
    utc_now,
)

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)

MAX_STEERING_DEGREES = 45.0
MOTOR_NEUTRAL_US = 1550.0
MOTOR_RANGE_US = 350.0


class _ControllerState(BaseModel):
    motor_us: float
    angle_deg: float


class _ControllerStatus(BaseModel):
    hardware_online: bool
    state: _ControllerState


class _ControllerCommandResponse(BaseModel):
    status: str | None = None
    angle_deg: float | None = None


class _VideoCommandResponse(BaseModel):
    status: str


class _HttpDownstreamClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        base_url: str,
        component: str,
    ) -> None:
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")
        self._component = component

    async def _request(
        self,
        method: str,
        path: str,
        response_model: type[ResponseModel],
        **kwargs: object,
    ) -> ResponseModel:
        try:
            response = await self._http_client.request(
                method,
                f"{self._base_url}{path}",
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise DownstreamTimeoutError(
                self._component,
                f"The {self._component} service did not respond before its deadline.",
            ) from exc
        except httpx.RequestError as exc:
            raise DownstreamUnavailableError(
                self._component,
                f"The {self._component} service is unavailable.",
            ) from exc

        if response.is_error:
            raise DownstreamHttpError(
                self._component,
                f"The {self._component} service returned an unsuccessful response.",
            )

        try:
            return response_model.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise DownstreamResponseError(
                self._component,
                f"The {self._component} service returned an invalid response.",
            ) from exc


class HttpHardwareClient(_HttpDownstreamClient):
    def __init__(self, http_client: httpx.AsyncClient, base_url: str) -> None:
        super().__init__(http_client, base_url, "hardware")
        self._last_sequence: int | None = None

    async def health(self) -> ComponentHealth:
        status = await self._status()
        detail = "controller hardware ready"
        if not status.hardware_online:
            detail = "controller hardware unavailable"
        return ComponentHealth(ready=status.hardware_online, detail=detail)

    async def apply_motion(self, command: MotionCommand) -> MotionResponse:
        steering_degrees = command.steering * MAX_STEERING_DEGREES
        throttle_delta = abs(command.throttle) * MOTOR_RANGE_US

        if command.throttle == 0:
            # Stop first so a steering failure cannot leave the car moving.
            await self._send_command("/neutral")
            await self._send_command("/steer", deg=steering_degrees)
        else:
            # Set steering before starting the motor.
            await self._send_command("/steer", deg=steering_degrees)
            direction = "/forward" if command.throttle > 0 else "/backward"
            await self._send_command(direction, delta=throttle_delta)

        self._last_sequence = command.sequence
        values = ControlValues(
            steering=command.steering,
            throttle=command.throttle,
        )
        return MotionResponse(
            accepted_sequence=command.sequence,
            requested=values,
            applied=values,
            hardware_received_at=utc_now(),
        )

    async def telemetry(self) -> HardwareTelemetry:
        status = await self._status()
        steering = status.state.angle_deg / MAX_STEERING_DEGREES
        throttle = (status.state.motor_us - MOTOR_NEUTRAL_US) / MOTOR_RANGE_US
        return HardwareTelemetry(
            steering=max(-1.0, min(1.0, steering)),
            throttle=max(-1.0, min(1.0, throttle)),
            last_sequence=self._last_sequence,
            sampled_at=utc_now(),
        )

    async def _status(self) -> _ControllerStatus:
        return await self._request("GET", "/status", _ControllerStatus)

    async def _send_command(self, path: str, **parameters: float) -> None:
        await self._request(
            "POST",
            path,
            _ControllerCommandResponse,
            params=parameters,
        )


class HttpVideoClient(_HttpDownstreamClient):
    def __init__(self, http_client: httpx.AsyncClient, base_url: str) -> None:
        super().__init__(http_client, base_url, "video")

    async def health(self) -> ComponentHealth:
        status = await self.status()
        return ComponentHealth(
            ready=True,
            detail=f"video API ready; stream is {status.stream.value}",
        )

    async def start_stream(self) -> VideoStatus:
        await self._request("POST", "/stream/start", _VideoCommandResponse)
        return VideoStatus(stream=StreamState.RUNNING)

    async def stop_stream(self) -> VideoStatus:
        await self._request("POST", "/stream/stop", _VideoCommandResponse)
        return VideoStatus(stream=StreamState.STOPPED)

    async def status(self) -> VideoStatus:
        return await self._request("GET", "/status", VideoStatus)
