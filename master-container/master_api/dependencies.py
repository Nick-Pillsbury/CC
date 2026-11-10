"""Application dependencies shared by route modules."""

import asyncio
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from master_api.clients.base import HardwareClient, VideoClient
from master_api.clients.errors import DownstreamError
from master_api.lease import ControlLeaseManager
from master_api.models import ComponentHealth, ReadinessResponse, utc_now
from master_api.state import SystemStateMachine


@dataclass(slots=True)
class ServiceContainer:
    """Clients used by the Master API to coordinate downstream containers."""

    hardware: HardwareClient
    video: VideoClient
    state_machine: SystemStateMachine = field(default_factory=SystemStateMachine)
    lease_duration_seconds: float = 2.0
    lease_manager: ControlLeaseManager = field(init=False)

    def __post_init__(self) -> None:
        self.lease_manager = ControlLeaseManager(
            self.hardware,
            self.state_machine,
            self.lease_duration_seconds,
        )

    async def check_readiness(self) -> ReadinessResponse:
        """Check both existing services, including when one cannot be reached."""
        async def check(client: HardwareClient | VideoClient) -> ComponentHealth:
            try:
                return await client.health()
            except DownstreamError as exc:
                return ComponentHealth(ready=False, detail=exc.message)

        hardware, video = await asyncio.gather(check(self.hardware), check(self.video))
        state = await self.lease_manager.reconcile_health(
            hardware_ready=hardware.ready,
            video_ready=video.ready,
        )
        return ReadinessResponse(
            ready=hardware.ready and video.ready,
            system_state=state.system_state,
            checks={"hardware": hardware, "video": video},
            checked_at=utc_now(),
        )


def get_services(connection: HTTPConnection) -> ServiceContainer:
    return connection.app.state.services


Services = Annotated[ServiceContainer, Depends(get_services)]
