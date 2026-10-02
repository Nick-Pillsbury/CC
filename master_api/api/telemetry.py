"""Telemetry snapshot routes."""

import asyncio

from fastapi import APIRouter

from master_api.dependencies import Services
from master_api.models import TelemetrySnapshot, utc_now

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("", response_model=TelemetrySnapshot)
async def telemetry_snapshot(services: Services) -> TelemetrySnapshot:
    hardware, video = await asyncio.gather(
        services.hardware.telemetry(),
        services.video.status(),
    )
    return TelemetrySnapshot(
        hardware=hardware,
        video=video,
        collected_at=utc_now(),
    )
