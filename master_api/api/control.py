"""Car-control routes."""

from fastapi import APIRouter

from master_api.dependencies import Services
from master_api.models import MotionCommand, MotionResponse

router = APIRouter(prefix="/control", tags=["control"])


@router.put("/motion", response_model=MotionResponse)
async def set_motion(command: MotionCommand, services: Services) -> MotionResponse:
    """Validate and forward one normalized motion command."""
    await services.state_machine.require_motion_allowed()
    return await services.hardware.apply_motion(command)
