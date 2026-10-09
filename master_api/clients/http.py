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
    HardwareTelemetry,
    MotionCommand,
    MotionResponse,
    RecordingStatus,
)

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


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

    async def health(self) -> ComponentHealth:
        return await self._request("GET", "/v1/health/ready", ComponentHealth)

    async def apply_motion(self, command: MotionCommand) -> MotionResponse:
        return await self._request(
            "PUT",
            "/v1/motion",
            MotionResponse,
            json=command.model_dump(mode="json"),
        )

    async def telemetry(self) -> HardwareTelemetry:
        return await self._request("GET", "/v1/telemetry", HardwareTelemetry)


class HttpVideoClient(_HttpDownstreamClient):
    def __init__(self, http_client: httpx.AsyncClient, base_url: str) -> None:
        super().__init__(http_client, base_url, "video")

    async def health(self) -> ComponentHealth:
        return await self._request("GET", "/v1/health/ready", ComponentHealth)

    async def start_recording(self, request_id: str) -> RecordingStatus:
        return await self._request(
            "POST",
            "/v1/recordings",
            RecordingStatus,
            json={"request_id": request_id},
        )

    async def stop_recording(self) -> RecordingStatus:
        return await self._request(
            "DELETE",
            "/v1/recordings/current",
            RecordingStatus,
        )

    async def status(self) -> RecordingStatus:
        return await self._request("GET", "/v1/status", RecordingStatus)
