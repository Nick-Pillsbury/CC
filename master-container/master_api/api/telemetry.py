"""Telemetry snapshot routes."""

import anyio

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from master_api.dependencies import Services
from master_api.models import TelemetrySnapshot

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("", response_model=TelemetrySnapshot)
async def telemetry_snapshot(services: Services) -> TelemetrySnapshot:
    return await services.collect_telemetry()


@router.get("/history")
async def telemetry_history(services: Services, after: int = Query(0, ge=0),
                            limit: int = Query(100, ge=1, le=1000)) -> dict:
    items = await services.journal.read("telemetry", after, limit)
    return {"items": items, "next_after": items[-1]["id"] if items else after}


@router.websocket("/ws")
async def telemetry_updates(websocket: WebSocket, services: Services) -> None:
    await websocket.accept()
    async with services.subscribe_telemetry() as updates:
        async def send_updates() -> None:
            while True:
                snapshot = await updates.get()
                await websocket.send_json(snapshot.model_dump(mode="json"))

        async with anyio.create_task_group() as group:
            group.start_soon(send_updates)
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                pass
            finally:
                group.cancel_scope.cancel()
