"""Application dependencies shared by route modules."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from master_api.clients.base import HardwareClient, VideoClient
from master_api.clients.errors import DownstreamError
from master_api.lease import ControlLeaseManager
from master_api.journal import Journal
from master_api.models import (ComponentHealth, ReadinessResponse, RecordingStatus,
                               TelemetrySnapshot, utc_now)
from master_api.state import SystemStateMachine


@dataclass(slots=True)
class ServiceContainer:
    """Clients used by the Master API to coordinate downstream containers."""

    hardware: HardwareClient
    video: VideoClient
    state_machine: SystemStateMachine = field(default_factory=SystemStateMachine)
    lease_duration_seconds: float = 2.0
    monitor_interval_seconds: float = 1.0
    journal: Journal = field(default_factory=Journal)
    lease_manager: ControlLeaseManager = field(init=False)
    last_readiness: ReadinessResponse | None = field(default=None, init=False)
    last_monitor_error: str | None = field(default=None, init=False)
    last_telemetry_error: str | None = field(default=None, init=False)
    _tasks: list[asyncio.Task] = field(default_factory=list, init=False)
    _stop: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _health_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _telemetry_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _latest: TelemetrySnapshot | None = field(default=None, init=False)
    _subscribers: set[asyncio.Queue] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        self.state_machine.journal = self.journal
        self.lease_manager = ControlLeaseManager(
            self.hardware,
            self.state_machine,
            self.lease_duration_seconds,
        )

    async def check_readiness(self) -> ReadinessResponse:
        """Check both existing services, including when one cannot be reached."""
        async with self._health_lock:
            return await self._check_readiness()

    async def _check_readiness(self) -> ReadinessResponse:
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
        result = ReadinessResponse(
            ready=hardware.ready and video.ready,
            system_state=state.system_state,
            checks={"hardware": hardware, "video": video},
            checked_at=utc_now(),
        )
        previous = self.last_readiness
        self.last_readiness = result
        if previous is None or previous.checks != result.checks:
            await self.journal.record("dependency_health", checks={
                name: item.model_dump() for name, item in result.checks.items()
            })
        return result

    async def collect_telemetry(self) -> TelemetrySnapshot:
        async with self._telemetry_lock:
            results = await asyncio.gather(
                self.hardware.telemetry(), self.video.status(), self.video.recording_status(),
                return_exceptions=True,
            )
            values = {}
            observed: dict[str, datetime] = dict(self._latest.observed_at) if self._latest else {}
            errors = {}
            now = utc_now()
            for name, result in zip(("hardware", "video", "recording"), results):
                if isinstance(result, Exception):
                    errors[name] = result.code if isinstance(result, DownstreamError) else "collection_failed"
                    values[name] = getattr(self._latest, name) if self._latest else None
                else:
                    values[name] = result
                    observed[name] = now
            if values["recording"] is None:
                values["recording"] = RecordingStatus(state="unavailable")
            snapshot = TelemetrySnapshot(
                **values, collected_at=now, observed_at=observed,
                errors=errors, stale_components=list(errors),
                system_state=self.state_machine.snapshot().system_state,
            )
            previous_errors = self._latest.errors if self._latest else {}
            if errors != previous_errors:
                await self.journal.record("telemetry_health", errors=errors)
            self._latest = snapshot
            await self.journal.append("telemetry", snapshot.model_dump(mode="json"))
            for queue in self._subscribers:
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(snapshot)
            return snapshot

    async def start_monitoring(self) -> None:
        if self._tasks:
            return
        self._stop.clear()
        self._tasks = [asyncio.create_task(self._monitor()), asyncio.create_task(self._sample())]

    async def stop_monitoring(self) -> None:
        self._stop.set()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self.journal.flush()

    async def _wait_interval(self) -> bool:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=self.monitor_interval_seconds)
            return False
        except TimeoutError:
            return True

    async def _monitor(self) -> None:
        while await self._wait_interval():
            try:
                await self.check_readiness()
                self.last_monitor_error = None
            except Exception:
                self.last_monitor_error = "monitor_failed"
                # Unexpected monitoring failures must revoke driving too.
                try:
                    await self.lease_manager.reconcile_health(hardware_ready=False, video_ready=False)
                except Exception:
                    self.last_monitor_error = "monitor_neutralization_failed"
                await self.journal.record("monitor_error", code=self.last_monitor_error)

    async def _sample(self) -> None:
        while await self._wait_interval():
            try:
                await self.collect_telemetry()
                self.last_telemetry_error = None
            except Exception:
                self.last_telemetry_error = "telemetry_sampling_failed"
                await self.journal.record("telemetry_error", code=self.last_telemetry_error)

    def monitoring_status(self) -> dict:
        now = utc_now()
        checked_at = self.last_readiness.checked_at if self.last_readiness else None
        sampled_at = self._latest.collected_at if self._latest else None
        return {
            "running": len(self._tasks) == 2 and all(not task.done() for task in self._tasks),
            "interval_seconds": self.monitor_interval_seconds,
            "health_checked_at": checked_at,
            "telemetry_sampled_at": sampled_at,
            "health_stale": checked_at is None or (now - checked_at).total_seconds() > max(5, self.monitor_interval_seconds * 3),
            "last_error": self.last_monitor_error,
            "telemetry_error": self.last_telemetry_error,
            "history_error": self.journal.last_error,
            "checks": self.last_readiness.checks if self.last_readiness else {},
        }

    @asynccontextmanager
    async def subscribe_telemetry(self) -> AsyncIterator[asyncio.Queue]:
        if self._latest is None:
            await self.collect_telemetry()
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._subscribers.add(queue)
        queue.put_nowait(self._latest)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)


def get_services(connection: HTTPConnection) -> ServiceContainer:
    return connection.app.state.services


Services = Annotated[ServiceContainer, Depends(get_services)]
