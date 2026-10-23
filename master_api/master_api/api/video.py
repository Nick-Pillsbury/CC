"""Video stream routes."""

from fastapi import APIRouter

from master_api.dependencies import Services
from master_api.models import VideoStatus

router = APIRouter(prefix="/video", tags=["video"])


@router.get("/status", response_model=VideoStatus)
async def video_status(services: Services) -> VideoStatus:
    return await services.video.status()


@router.post("/stream/start", response_model=VideoStatus)
async def start_stream(services: Services) -> VideoStatus:
    return await services.video.start_stream()


@router.post("/stream/stop", response_model=VideoStatus)
async def stop_stream(services: Services) -> VideoStatus:
    return await services.video.stop_stream()
