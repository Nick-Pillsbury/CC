"""Response models for the HTTP API."""
from typing import Literal
from pydantic import BaseModel


class SteeringResponse(BaseModel):
    angle_deg: float
    steering_us: float


class MotorResponse(BaseModel):
    status: Literal["forward", "backwards"]
    motor_us: float


class NeutralResponse(BaseModel):
    status: Literal["neutral"] = "neutral"