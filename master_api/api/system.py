"""System-state inspection routes."""

from fastapi import APIRouter

from master_api.dependencies import Services
from master_api.models import SystemStatus

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/state", response_model=SystemStatus)
async def system_state(services: Services) -> SystemStatus:
    return services.state_machine.snapshot()
