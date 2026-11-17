"""Interfaces for hardware and video container clients."""

from typing import Protocol
from uuid import UUID

from master_api.models import (
    ComponentHealth,
    HardwareTelemetry,
    MotionCommand,
    MotionResponse,
    RecordingStatus,
    VideoStatus,
)


class HardwareClient(Protocol):
    async def health(self) -> ComponentHealth: ...

    async def apply_motion(self, command: MotionCommand) -> MotionResponse: ...

    async def stop(self) -> None: ...

    async def telemetry(self) -> HardwareTelemetry: ...


class VideoClient(Protocol):
    async def health(self) -> ComponentHealth: ...

    async def start_stream(self) -> VideoStatus: ...

    async def stop_stream(self) -> VideoStatus: ...

    async def status(self) -> VideoStatus: ...

    async def recording_status(self) -> RecordingStatus: ...

    async def start_recording(self, request_id: UUID) -> RecordingStatus: ...

    async def stop_recording(self, recording_id: UUID) -> RecordingStatus: ...
