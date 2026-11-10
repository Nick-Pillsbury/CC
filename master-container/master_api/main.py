"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse

from master_api.api import control, health, system, telemetry, video
from master_api.clients.errors import DownstreamError
from master_api.clients.http import HttpHardwareClient, HttpVideoClient
from master_api.clients.mock import MockHardwareClient, MockVideoClient
from master_api.config import Settings
from master_api.dependencies import ServiceContainer
from master_api.lease import ControlLeaseError
from master_api.models import PingResponse, SystemState
from master_api.state import StateConflictError


def create_app(
    services: ServiceContainer | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    """Create an application with replaceable downstream service clients."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Tests can provide their own clients instead of creating runtime clients.
        if services is not None:
            application.state.services = services
            await services.lease_manager.start()
            try:
                yield
            finally:
                try:
                    await services.lease_manager.shutdown()
                finally:
                    await services.state_machine.transition(
                        target=SystemState.SHUTTING_DOWN,
                        reason="Application shutdown started",
                    )
            return

        runtime_settings = settings or Settings.from_env()

        # Mock mode lets students run the API without car hardware.
        if runtime_settings.client_mode == "mock":
            application.state.services = ServiceContainer(
                hardware=MockHardwareClient(),
                video=MockVideoClient(),
                lease_duration_seconds=runtime_settings.control_lease_seconds,
            )
            runtime_services = application.state.services
            await runtime_services.lease_manager.start()
            try:
                await runtime_services.check_readiness()
                yield
            finally:
                try:
                    await runtime_services.lease_manager.shutdown()
                finally:
                    await runtime_services.state_machine.transition(
                        target=SystemState.SHUTTING_DOWN,
                        reason="Application shutdown started",
                    )
            return

        # HTTP mode shares one client between the hardware and video services.
        async with httpx.AsyncClient(
            timeout=runtime_settings.http_timeout()
        ) as http_client:
            application.state.services = ServiceContainer(
                hardware=HttpHardwareClient(
                    http_client,
                    runtime_settings.controller_base_url,
                ),
                video=HttpVideoClient(
                    http_client,
                    runtime_settings.video_base_url,
                ),
                lease_duration_seconds=runtime_settings.control_lease_seconds,
            )
            runtime_services = application.state.services
            await runtime_services.lease_manager.start()
            try:
                await runtime_services.check_readiness()
                yield
            finally:
                try:
                    await runtime_services.lease_manager.shutdown()
                finally:
                    await runtime_services.state_machine.transition(
                        target=SystemState.SHUTTING_DOWN,
                        reason="Application shutdown started",
                    )

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

    @app.exception_handler(StateConflictError)
    async def handle_state_conflict(
        request: Request,
        exc: StateConflictError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "system_state": exc.current_state.value,
                    "retryable": exc.retryable,
                }
            },
        )

    @app.exception_handler(ControlLeaseError)
    async def handle_control_lease_error(
        request: Request,
        exc: ControlLeaseError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                }
            },
        )

    @app.get("/ping", response_model=PingResponse, tags=["health"])
    async def ping() -> PingResponse:
        """Lightweight server reachability check for WireGuard clients."""
        return PingResponse()

    api_prefix = "/api/v1"
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(system.router, prefix=api_prefix)
    app.include_router(control.router, prefix=api_prefix)
    app.include_router(video.router, prefix=api_prefix)
    app.include_router(telemetry.router, prefix=api_prefix)
    return app


app = create_app()
