"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse

from master_api.api import control, health, telemetry, video
from master_api.clients.errors import DownstreamError
from master_api.clients.http import HttpHardwareClient, HttpVideoClient
from master_api.clients.mock import MockHardwareClient, MockVideoClient
from master_api.config import Settings
from master_api.dependencies import ServiceContainer


def create_app(
    services: ServiceContainer | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    """Create an application with replaceable downstream service clients."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if services is not None:
            application.state.services = services
            yield
            return

        runtime_settings = settings or Settings.from_env()
        if runtime_settings.client_mode == "mock":
            application.state.services = ServiceContainer(
                hardware=MockHardwareClient(),
                video=MockVideoClient(),
            )
            yield
            return

        async with httpx.AsyncClient(
            timeout=runtime_settings.http_timeout()
        ) as http_client:
            application.state.services = ServiceContainer(
                hardware=HttpHardwareClient(
                    http_client,
                    runtime_settings.hardware_base_url,
                ),
                video=HttpVideoClient(
                    http_client,
                    runtime_settings.video_base_url,
                ),
            )
            yield

    app = FastAPI(
        title="CC Master API",
        version="0.1.0",
        description="Central API for car control, video, telemetry, and health.",
        lifespan=lifespan,
    )
    if services is not None:
        # Keep explicitly injected services usable by TestClient without requiring
        # lifespan startup. The application still never owns or closes them.
        app.state.services = services

    @app.exception_handler(DownstreamError)
    async def handle_downstream_error(
        request: Request,
        exc: DownstreamError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "component": exc.component,
                    "retryable": exc.retryable,
                }
            },
        )

    api_prefix = "/api/v1"
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(control.router, prefix=api_prefix)
    app.include_router(video.router, prefix=api_prefix)
    app.include_router(telemetry.router, prefix=api_prefix)
    return app


app = create_app()
