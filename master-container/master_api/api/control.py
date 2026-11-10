"""Exclusive control-session and car-motion routes."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Header, Response, status

from master_api.dependencies import Services
from master_api.models import (
    ControlLeaseRequest,
    ControlLeaseResponse,
    MotionCommand,
    MotionResponse,
    SystemState,
    SystemStatus,
)
from master_api.state import StateConflictError

router = APIRouter(prefix="/control", tags=["control"])
LeaseHeader = Annotated[str, Header(alias="X-Control-Lease", min_length=1)]


@router.post(
    "/lease",
    response_model=ControlLeaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def acquire_control(
    request: ControlLeaseRequest,
    services: Services,
) -> ControlLeaseResponse:
    """Atomically grant exclusive, short-lived driving control."""
    if services.state_machine.snapshot().system_state in {
        SystemState.STARTING, SystemState.DEGRADED,
    }:
        await services.check_readiness()
    return await services.lease_manager.acquire(request.client_id)


@router.post("/lease/heartbeat", response_model=ControlLeaseResponse)
async def heartbeat_control(
    services: Services,
    lease_id: LeaseHeader,
) -> ControlLeaseResponse:
    """Renew the active lease before it expires."""
    return await services.lease_manager.heartbeat(lease_id)


@router.delete("/lease", status_code=status.HTTP_204_NO_CONTENT)
async def release_control(services: Services, lease_id: LeaseHeader) -> Response:
    """Neutralize the car and release exclusive control."""
    await services.lease_manager.release(lease_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/motion", response_model=MotionResponse)
async def set_motion(
    command: MotionCommand,
    services: Services,
    lease_id: LeaseHeader,
) -> MotionResponse:
    """Validate and forward one normalized motion command."""
    return await services.lease_manager.apply_motion(lease_id, command)


@router.post("/emergency-stop", response_model=SystemStatus)
async def emergency_stop(services: Services) -> SystemStatus:
    """Latch emergency state and request immediate hardware neutralization."""
    await services.lease_manager.emergency_stop()
    return services.state_machine.snapshot()


@router.post("/emergency-stop/reset", response_model=SystemStatus)
async def reset_emergency_stop(services: Services) -> SystemStatus:
    """Clear the latch only after both downstream services report healthy."""
    hardware, video = await asyncio.gather(
        services.hardware.health(),
        services.video.health(),
    )
    if not hardware.ready or not video.ready:
        state = services.state_machine.snapshot().system_state
        raise StateConflictError(
            state,
            "Emergency stop cannot be reset while a dependency is unhealthy.",
        )
    await services.lease_manager.reset_emergency_stop()
    return services.state_machine.snapshot()
