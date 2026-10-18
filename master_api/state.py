"""Concurrency-safe state transitions for Master API orchestration."""

import asyncio

from master_api.models import SystemState, SystemStatus, utc_now


class StateConflictError(Exception):
    """Raised when an operation is not legal in the current system state."""

    code = "system_state_conflict"
    status_code = 409
    retryable = False

    def __init__(self, current_state: SystemState, message: str) -> None:
        super().__init__(message)
        self.current_state = current_state
        self.message = message


class SystemStateMachine:
    """Own and guard the process-wide system state."""

    _allowed_transitions = {
        SystemState.STARTING: {
            SystemState.READY,
            SystemState.DEGRADED,
            SystemState.EMERGENCY_STOP,
            SystemState.SHUTTING_DOWN,
        },
        SystemState.READY: {
            SystemState.CONTROLLED,
            SystemState.DEGRADED,
            SystemState.EMERGENCY_STOP,
            SystemState.SHUTTING_DOWN,
        },
        SystemState.CONTROLLED: {
            SystemState.READY,
            SystemState.DEGRADED,
            SystemState.EMERGENCY_STOP,
            SystemState.SHUTTING_DOWN,
        },
        SystemState.DEGRADED: {
            SystemState.READY,
            SystemState.EMERGENCY_STOP,
            SystemState.SHUTTING_DOWN,
        },
        SystemState.EMERGENCY_STOP: {
            SystemState.READY,
            SystemState.SHUTTING_DOWN,
        },
        SystemState.SHUTTING_DOWN: set(),
    }

    def __init__(self, initial_state: SystemState = SystemState.STARTING) -> None:
        self._state = initial_state
        self._reason = "Master API process created"
        self._changed_at = utc_now()
        self._lock = asyncio.Lock()

    def snapshot(self) -> SystemStatus:
        """Return an immutable view of the latest committed state."""
        return SystemStatus(
            system_state=self._state,
            reason=self._reason,
            changed_at=self._changed_at,
        )

    async def transition(
        self,
        target: SystemState,
        reason: str,
    ) -> SystemStatus:
        async with self._lock:
            return self._transition_locked(target, reason)

    async def reconcile_health(
        self,
        *,
        hardware_ready: bool,
        video_ready: bool,
    ) -> SystemStatus:
        """Update state from dependency health without clearing a safety latch."""
        async with self._lock:
            if self._state in {
                SystemState.EMERGENCY_STOP,
                SystemState.SHUTTING_DOWN,
            }:
                return self.snapshot()

            if not hardware_ready:
                target = (
                    SystemState.EMERGENCY_STOP
                    if self._state == SystemState.CONTROLLED
                    else SystemState.DEGRADED
                )
                return self._transition_locked(target, "Hardware is unavailable")

            if not video_ready:
                return self._transition_locked(
                    SystemState.DEGRADED,
                    "Video service is unavailable",
                )

            if self._state in {SystemState.STARTING, SystemState.DEGRADED}:
                return self._transition_locked(
                    SystemState.READY,
                    "Required services are ready",
                )

            return self.snapshot()

    async def require_motion_allowed(self) -> None:
        async with self._lock:
            if self._state != SystemState.CONTROLLED:
                raise StateConflictError(
                    self._state,
                    "Motion commands require the CONTROLLED system state.",
                )

    def _transition_locked(
        self,
        target: SystemState,
        reason: str,
    ) -> SystemStatus:
        if target == self._state:
            return self.snapshot()
        if target not in self._allowed_transitions[self._state]:
            raise StateConflictError(
                self._state,
                f"Cannot transition from {self._state.value} to {target.value}.",
            )

        self._state = target
        self._reason = reason
        self._changed_at = utc_now()
        return self.snapshot()
