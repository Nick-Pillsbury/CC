"""System-state inspection routes."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from master_api.dependencies import Services
from master_api.models import SystemStatus

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/state", response_model=SystemStatus)
async def system_state(services: Services) -> SystemStatus:
    return services.state_machine.snapshot()


@router.websocket("/state/ws")
async def system_state_updates(websocket: WebSocket, services: Services) -> None:
    """Push the current state and each subsequent committed transition."""
    await websocket.accept()
    try:
        async with services.state_machine.subscribe() as updates:
            while True:
                state = await updates.get()
                await websocket.send_json(state.model_dump(mode="json"))
    except WebSocketDisconnect:
        return
