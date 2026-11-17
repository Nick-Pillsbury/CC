"""Typed request and response contracts for the public API."""

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SystemState(str, Enum):
    STARTING = "STARTING"
    READY = "READY"
    CONTROLLED = "CONTROLLED"
    DEGRADED = "DEGRADED"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    SHUTTING_DOWN = "SHUTTING_DOWN"


class SystemStatus(BaseModel):
    system_state: SystemState
    reason: str
    changed_at: datetime


class ComponentHealth(BaseModel):
    ready: bool
    detail: str = "ready"


class LivenessResponse(BaseModel):
    status: str = "alive"


class PingResponse(BaseModel):
    status: str = "ok"


class ReadinessResponse(BaseModel):
    ready: bool
    system_state: SystemState
    checks: dict[str, ComponentHealth]
    checked_at: datetime


class MotionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steering: float = Field(ge=-1.0, le=1.0, allow_inf_nan=False)
    throttle: float = Field(ge=-1.0, le=1.0, allow_inf_nan=False)
    sequence: int = Field(ge=0)
    client_sent_at: datetime


class ControlLeaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(min_length=1, max_length=128)


class ControlLeaseResponse(BaseModel):
    lease_id: str
    client_id: str
    acquired_at: datetime
    expires_at: datetime


class ControlValues(BaseModel):
    steering: float
    throttle: float


class MotionResponse(BaseModel):
    accepted_sequence: int
    requested: ControlValues
    applied: ControlValues
    limited_by: list[str] = Field(default_factory=list)
    hardware_received_at: datetime


class StreamState(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"


class VideoStatus(BaseModel):
    stream: StreamState


class HardwareTelemetry(BaseModel):
    steering: float
    throttle: float
    last_sequence: int | None
    sampled_at: datetime


class RecordingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID


class RecordingStatus(BaseModel):
    state: str = Field(pattern="^(idle|recording|stopped|failed|unsupported|unavailable)$")
    recording_id: UUID | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    detail: str | None = None


class TelemetrySnapshot(BaseModel):
    hardware: HardwareTelemetry | None
    video: VideoStatus | None
    collected_at: datetime
    recording: RecordingStatus | None = None
    stale_components: list[str] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)
    observed_at: dict[str, datetime] = Field(default_factory=dict)
    system_state: SystemState = SystemState.STARTING
