"""Video stream routes."""

from fastapi import APIRouter
from uuid import UUID

from master_api.api.control import LeaseHeader
from master_api.dependencies import Services
from master_api.models import RecordingRequest, RecordingStatus, VideoStatus

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


@router.get("/recordings/current", response_model=RecordingStatus)
async def recording_status(services: Services) -> RecordingStatus:
    return await services.video.recording_status()


@router.post("/recordings", response_model=RecordingStatus)
async def start_recording(request: RecordingRequest, services: Services,
                          lease_id: LeaseHeader) -> RecordingStatus:
    await services.lease_manager.authorize(lease_id)
    result = await services.video.start_recording(request.request_id)
    await services.journal.record("recording_start", state=result.state,
                                  recording_id=str(result.recording_id))
    return result


@router.delete("/recordings/{recording_id}", response_model=RecordingStatus)
async def stop_recording(recording_id: UUID, services: Services,
                         lease_id: LeaseHeader) -> RecordingStatus:
    await services.lease_manager.authorize(lease_id)
    result = await services.video.stop_recording(recording_id)
    await services.journal.record("recording_stop", state=result.state,
                                  recording_id=str(result.recording_id))
    return result
