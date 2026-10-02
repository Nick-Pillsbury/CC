"""FastAPI application entry point."""

from fastapi import FastAPI

from master_api.api import control, health, telemetry, video
from master_api.clients.mock import MockHardwareClient, MockVideoClient
from master_api.dependencies import ServiceContainer


def create_app(services: ServiceContainer | None = None) -> FastAPI:
    """Create an application with replaceable downstream service clients."""
    app = FastAPI(
        title="CC Master API",
        version="0.1.0",
        description="Central API for car control, video, telemetry, and health.",
    )
    app.state.services = services or ServiceContainer(
        hardware=MockHardwareClient(),
        video=MockVideoClient(),
    )

    api_prefix = "/api/v1"
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(control.router, prefix=api_prefix)
    app.include_router(video.router, prefix=api_prefix)
    app.include_router(telemetry.router, prefix=api_prefix)
    return app


app = create_app()
