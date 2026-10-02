"""Typed request and response contracts for the public API."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SystemState(str, Enum):
    STARTING = "STARTING"
    READY = "READY"
    CONTROLLED = "CONTROLLED"
    DEGRADED = "DEGRADED"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class ComponentHealth(BaseModel):
    ready: bool
    detail: str = "ready"


class LivenessResponse(BaseModel):
    status: str = "alive"


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


class ControlValues(BaseModel):
    steering: float
    throttle: float


class MotionResponse(BaseModel):
    accepted_sequence: int
    requested: ControlValues
    applied: ControlValues
    limited_by: list[str] = Field(default_factory=list)
    hardware_received_at: datetime


class RecordingStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)


class RecordingState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    STOPPED = "stopped"


class RecordingStatus(BaseModel):
    state: RecordingState
    recording_id: str | None = None
    request_id: str | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None


class HardwareTelemetry(BaseModel):
    steering: float
    throttle: float
    last_sequence: int | None
    sampled_at: datetime


class TelemetrySnapshot(BaseModel):
    hardware: HardwareTelemetry
    video: RecordingStatus
    collected_at: datetime
