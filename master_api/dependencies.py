"""Application dependencies shared by route modules."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from master_api.clients.base import HardwareClient, VideoClient


@dataclass(slots=True)
class ServiceContainer:
    """Clients used by the Master API to coordinate downstream containers."""

    hardware: HardwareClient
    video: VideoClient


def get_services(request: Request) -> ServiceContainer:
    return request.app.state.services


Services = Annotated[ServiceContainer, Depends(get_services)]
