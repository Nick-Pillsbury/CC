"""Video-control routes."""

from fastapi import APIRouter, status

from master_api.dependencies import Services
from master_api.models import RecordingStart, RecordingStatus

router = APIRouter(prefix="/video", tags=["video"])


@router.get("/status", response_model=RecordingStatus)
async def video_status(services: Services) -> RecordingStatus:
    return await services.video.status()


@router.post(
    "/recordings",
    response_model=RecordingStatus,
    status_code=status.HTTP_201_CREATED,
)
async def start_recording(
    request: RecordingStart,
    services: Services,
) -> RecordingStatus:
    return await services.video.start_recording(request.request_id)


@router.delete("/recordings/current", response_model=RecordingStatus)
async def stop_recording(services: Services) -> RecordingStatus:
    return await services.video.stop_recording()
