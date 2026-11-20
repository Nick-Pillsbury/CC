"""Response models for the HTTP API."""
from typing import Literal
from pydantic import BaseModel


class DriveState(BaseModel):
    motor_us: float
    steering_us: float
    angle_deg: float


class SteeringResponse(BaseModel):
    angle_deg: float
    steering_us: float


class MotorResponse(BaseModel):
    status: Literal["forward", "backwards"]
    motor_us: float


class NeutralResponse(BaseModel):
    status: Literal["neutral"] = "neutral"


class StatusResponse(BaseModel):
    hardware_online: bool
    frequency_hz: float
    state: DriveState