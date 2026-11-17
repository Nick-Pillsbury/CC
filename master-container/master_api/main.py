"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse

from master_api.api import control, health, system, telemetry, video
from master_api.audit import AuditMiddleware
from master_api.clients.errors import DownstreamError
from master_api.clients.http import HttpHardwareClient, HttpVideoClient
from master_api.clients.mock import MockHardwareClient, MockVideoClient
from master_api.config import Settings
from master_api.dependencies import ServiceContainer
from master_api.journal import Journal
from master_api.lease import ControlLeaseError
from master_api.models import PingResponse, SystemState
from master_api.state import StateConflictError


def create_app(
    services: ServiceContainer | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    """Create an application with replaceable downstream service clients."""

    @asynccontextmanager
    async def run_services(application: FastAPI, current: ServiceContainer,
                           *, owned: bool) -> AsyncIterator[None]:
        application.state.services = current
        await current.lease_manager.start()
        try:
            if owned:
                await current.check_readiness()
                await current.start_monitoring()
            yield
        finally:
            try:
                # Stop monitoring before neutralizing to prevent a late health transition.
                try:
                    await current.stop_monitoring()
                finally:
                    await current.lease_manager.shutdown()
            finally:
                await current.state_machine.transition(
                    SystemState.SHUTTING_DOWN, "Application shutdown started",
                )
                await current.journal.flush()
                if owned:
                    await current.journal.close()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Tests can provide their own clients instead of creating runtime clients.
        if services is not None:
            async with run_services(application, services, owned=False):
                yield
            return

        runtime_settings = settings or Settings.from_env()
        common = dict(
            lease_duration_seconds=runtime_settings.control_lease_seconds,
            monitor_interval_seconds=runtime_settings.monitor_interval_seconds,
            journal=Journal(runtime_settings.history_path, runtime_settings.history_limit),
        )

        # Mock mode lets students run the API without car hardware.
        if runtime_settings.client_mode == "mock":
            runtime_services = ServiceContainer(
                hardware=MockHardwareClient(),
                video=MockVideoClient(),
                **common,
            )
            async with run_services(application, runtime_services, owned=True):
                yield
            return

        # HTTP mode shares one client between the hardware and video services.
        async with httpx.AsyncClient(
            timeout=runtime_settings.http_timeout()
        ) as http_client:
            runtime_services = ServiceContainer(
                hardware=HttpHardwareClient(
                    http_client,
                    runtime_settings.controller_base_url,
                ),
                video=HttpVideoClient(
                    http_client,
                    runtime_settings.video_base_url,
                ),
                **common,
            )
            async with run_services(application, runtime_services, owned=True):
                yield

    app = FastAPI(
        title="CC Master API",
        version="0.2.0",
        description="Central API for car control, video, telemetry, and health.",
        lifespan=lifespan,
    )
    app.add_middleware(AuditMiddleware)
    if services is not None:
        # Keep explicitly injected services usable by TestClient without requiring
        # lifespan startup. The application still never owns or closes them.
        app.state.services = services

    @app.exception_handler(DownstreamError)
    async def handle_downstream_error(
        request: Request,
        exc: DownstreamError,
    ) -> JSONResponse:
        await request.app.state.services.journal.record(
            "downstream_error", code=exc.code, component=exc.component,
            request_id=request.state.request_id,
        )
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
        await request.app.state.services.journal.record(
            "state_conflict", state=exc.current_state.value,
            request_id=request.state.request_id,
        )
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
        await request.app.state.services.journal.record(
            "control_rejected", code=exc.code, request_id=request.state.request_id,
        )
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
