"""Exclusive, expiring control ownership for safe driving commands."""

import asyncio
from datetime import timedelta
from uuid import uuid4

from master_api.clients.base import HardwareClient
from master_api.models import (
    ControlLeaseResponse,
    MotionCommand,
    MotionResponse,
    SystemState,
    utc_now,
)
from master_api.state import StateConflictError, SystemStateMachine


class ControlLeaseError(Exception):
    """Stable public error for lease conflicts and stale commands."""

    status_code = 409
    retryable = False

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ControlLeaseManager:
    """Serialize lease changes, motion, expiry, and neutralization."""

    def __init__(
        self,
        hardware: HardwareClient,
        state_machine: SystemStateMachine,
        duration_seconds: float = 2.0,
    ) -> None:
        self._hardware = hardware
        self._state_machine = state_machine
        self._duration = timedelta(seconds=duration_seconds)
        self._lock = asyncio.Lock()
        self._active: ControlLeaseResponse | None = None
        self._last_sequence: int | None = None
        self._stop_event = asyncio.Event()
        self._watchdog_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._watchdog_task is None:
            self._stop_event.clear()
            self._watchdog_task = asyncio.create_task(self._watchdog())

    async def shutdown(self) -> None:
        self._stop_event.set()
        if self._watchdog_task is not None:
            await self._watchdog_task
            self._watchdog_task = None

        async with self._lock:
            if self._active is not None:
                self._active = None
                self._last_sequence = None
                await self._hardware.stop()

    async def acquire(self, client_id: str) -> ControlLeaseResponse:
        async with self._lock:
            await self._expire_if_needed_locked()
            if self._active is not None:
                raise ControlLeaseError(
                    "control_lease_held",
                    "Another driver currently controls the car.",
                )
            if self._state_machine.snapshot().system_state != SystemState.READY:
                state = self._state_machine.snapshot().system_state
                raise StateConflictError(
                    state,
                    "Control can only be acquired while the system is READY.",
                )

            acquired_at = utc_now()
            lease = ControlLeaseResponse(
                lease_id=str(uuid4()),
                client_id=client_id,
                acquired_at=acquired_at,
                expires_at=acquired_at + self._duration,
            )
            await self._state_machine.transition(
                SystemState.CONTROLLED,
                "Driver acquired control",
            )
            self._active = lease
            self._last_sequence = None
            return lease.model_copy()

    async def heartbeat(self, lease_id: str) -> ControlLeaseResponse:
        async with self._lock:
            await self._expire_if_needed_locked()
            lease = self._require_active_locked(lease_id)
            lease = lease.model_copy(update={"expires_at": utc_now() + self._duration})
            self._active = lease
            return lease.model_copy()

    async def apply_motion(
        self,
        lease_id: str,
        command: MotionCommand,
    ) -> MotionResponse:
        async with self._lock:
            await self._expire_if_needed_locked()
            self._require_active_locked(lease_id)
            await self._state_machine.require_motion_allowed()
            if self._last_sequence is not None and command.sequence <= self._last_sequence:
                raise ControlLeaseError(
                    "motion_sequence_stale",
                    "Motion sequence must be greater than the last accepted sequence.",
                )

            response = await self._hardware.apply_motion(command)
            self._last_sequence = command.sequence
            return response

    async def release(self, lease_id: str) -> None:
        async with self._lock:
            await self._expire_if_needed_locked()
            self._require_active_locked(lease_id)
            self._active = None
            self._last_sequence = None
            await self._neutralize_locked("Driver released control")

    async def emergency_stop(self) -> None:
        async with self._lock:
            self._active = None
            self._last_sequence = None
            state = self._state_machine.snapshot().system_state
            if state not in {SystemState.EMERGENCY_STOP, SystemState.SHUTTING_DOWN}:
                await self._state_machine.transition(
                    SystemState.EMERGENCY_STOP,
                    "Emergency stop requested",
                )
            await self._hardware.stop()

    async def reset_emergency_stop(self) -> None:
        async with self._lock:
            state = self._state_machine.snapshot().system_state
            if state != SystemState.EMERGENCY_STOP:
                raise StateConflictError(
                    state,
                    "Emergency stop can only be reset from EMERGENCY_STOP.",
                )
            await self._hardware.stop()
            await self._state_machine.transition(
                SystemState.READY,
                "Emergency stop reset after successful health checks",
            )

    def _require_active_locked(self, lease_id: str) -> ControlLeaseResponse:
        if self._active is None or self._active.lease_id != lease_id:
            raise ControlLeaseError(
                "control_lease_inactive",
                "The supplied control lease is not active.",
            )
        return self._active

    async def _expire_if_needed_locked(self) -> None:
        if self._active is None or utc_now() < self._active.expires_at:
            return
        self._active = None
        self._last_sequence = None
        await self._neutralize_locked("Control lease expired")

    async def _neutralize_locked(self, reason: str) -> None:
        try:
            await self._hardware.stop()
        except Exception:
            state = self._state_machine.snapshot().system_state
            if state not in {SystemState.EMERGENCY_STOP, SystemState.SHUTTING_DOWN}:
                await self._state_machine.transition(
                    SystemState.EMERGENCY_STOP,
                    f"{reason}; hardware neutralization failed",
                )
            raise

        if self._state_machine.snapshot().system_state == SystemState.CONTROLLED:
            await self._state_machine.transition(SystemState.READY, reason)

    async def _watchdog(self) -> None:
        interval = min(max(self._duration.total_seconds() / 4, 0.05), 0.25)
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except TimeoutError:
                try:
                    async with self._lock:
                        await self._expire_if_needed_locked()
                except Exception:
                    # The state machine records the emergency condition. Keep
                    # the process alive so health endpoints can report it.
                    continue
