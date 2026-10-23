"""Interfaces for hardware and video container clients."""

from typing import Protocol

from master_api.models import (
    ComponentHealth,
    HardwareTelemetry,
    MotionCommand,
    MotionResponse,
    RecordingStatus,
)


class HardwareClient(Protocol):
    async def health(self) -> ComponentHealth: ...

    async def apply_motion(self, command: MotionCommand) -> MotionResponse: ...

    async def telemetry(self) -> HardwareTelemetry: ...


class VideoClient(Protocol):
    async def health(self) -> ComponentHealth: ...

    async def start_recording(self, request_id: str) -> RecordingStatus: ...

    async def stop_recording(self) -> RecordingStatus: ...

    async def status(self) -> RecordingStatus: ...
