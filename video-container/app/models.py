"""Request/response models for the HTTP API."""
from enum import StrEnum
from pydantic import BaseModel


class StreamState(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"


class ActionStatus(StrEnum):
    STARTED = "started"
    ALREADY_RUNNING = "already running"
    STOPPED = "stopped"
    NOT_RUNNING = "not running"


class ActionResponse(BaseModel):
    status: ActionStatus


class StatusResponse(BaseModel):
    stream: StreamState
