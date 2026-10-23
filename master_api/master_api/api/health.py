"""Liveness and readiness routes."""

import asyncio

from fastapi import APIRouter, Response, status

from master_api.dependencies import Services
from master_api.models import LivenessResponse, ReadinessResponse, utc_now

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(services: Services, response: Response) -> ReadinessResponse:
    hardware, video = await asyncio.gather(
        services.hardware.health(),
        services.video.health(),
    )
    ready = hardware.ready and video.ready
    state = await services.state_machine.reconcile_health(
        hardware_ready=hardware.ready,
        video_ready=video.ready,
    )
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        ready=ready,
        system_state=state.system_state,
        checks={"hardware": hardware, "video": video},
        checked_at=utc_now(),
    )
