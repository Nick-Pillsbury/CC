"""HTTP API for controlling the camera stream."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from config import Settings
from models import ActionResponse, ActionStatus, StatusResponse, StreamState
from stream import StreamService, StreamStartError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(service: StreamService | None = None) -> FastAPI:
    service = service or StreamService(Settings.from_env())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await service.stop()  # don't leave ffmpeg running when the API shuts down

    app = FastAPI(title="Video API", lifespan=lifespan)

    @app.post("/stream/start", response_model=ActionResponse)
    async def start_stream() -> ActionResponse:
        try:
            started = await service.start()
        except StreamStartError as exc:
            raise HTTPException(500, "ffmpeg failed to start") from exc
        return ActionResponse(status=ActionStatus.STARTED if started else ActionStatus.ALREADY_RUNNING)

    @app.post("/stream/stop", response_model=ActionResponse)
    async def stop_stream() -> ActionResponse:
        stopped = await service.stop()
        return ActionResponse(status=ActionStatus.STOPPED if stopped else ActionStatus.NOT_RUNNING)

    @app.get("/status", response_model=StatusResponse)
    async def status() -> StatusResponse:
        return StatusResponse(stream=StreamState.RUNNING if service.is_running else StreamState.STOPPED)

    return app


app = create_app()
