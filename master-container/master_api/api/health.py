"""Liveness and readiness routes."""

from fastapi import APIRouter, Response, status

from master_api.dependencies import Services
from master_api.models import LivenessResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(services: Services, response: Response) -> ReadinessResponse:
    result = await services.check_readiness()
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
