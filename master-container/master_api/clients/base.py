"""Interfaces for hardware and video container clients."""

from typing import Protocol

from master_api.models import (
    ComponentHealth,
    HardwareTelemetry,
    MotionCommand,
    MotionResponse,
    VideoStatus,
)


class HardwareClient(Protocol):
    async def health(self) -> ComponentHealth: ...

    async def apply_motion(self, command: MotionCommand) -> MotionResponse: ...

    async def telemetry(self) -> HardwareTelemetry: ...


class VideoClient(Protocol):
    async def health(self) -> ComponentHealth: ...

    async def start_stream(self) -> VideoStatus: ...

    async def stop_stream(self) -> VideoStatus: ...

    async def status(self) -> VideoStatus: ...
