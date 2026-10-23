"""In-memory downstream clients for development before containers are ready."""

from uuid import uuid4

from master_api.models import (
    ComponentHealth,
    ControlValues,
    HardwareTelemetry,
    MotionCommand,
    MotionResponse,
    RecordingState,
    RecordingStatus,
    utc_now,
)


class MockHardwareClient:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.steering = 0.0
        self.throttle = 0.0
        self.last_sequence: int | None = None

    async def health(self) -> ComponentHealth:
        detail = "mock hardware ready" if self.ready else "mock hardware unavailable"
        return ComponentHealth(ready=self.ready, detail=detail)

    async def apply_motion(self, command: MotionCommand) -> MotionResponse:
        self.steering = command.steering
        self.throttle = command.throttle
        self.last_sequence = command.sequence
        values = ControlValues(steering=self.steering, throttle=self.throttle)
        return MotionResponse(
            accepted_sequence=command.sequence,
            requested=values,
            applied=values,
            hardware_received_at=utc_now(),
        )

    async def telemetry(self) -> HardwareTelemetry:
        return HardwareTelemetry(
            steering=self.steering,
            throttle=self.throttle,
            last_sequence=self.last_sequence,
            sampled_at=utc_now(),
        )


class MockVideoClient:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self._status = RecordingStatus(state=RecordingState.IDLE)

    async def health(self) -> ComponentHealth:
        detail = "mock video ready" if self.ready else "mock video unavailable"
        return ComponentHealth(ready=self.ready, detail=detail)

    async def start_recording(self, request_id: str) -> RecordingStatus:
        if self._status.state == RecordingState.RECORDING:
            return self._status

        self._status = RecordingStatus(
            state=RecordingState.RECORDING,
            recording_id=str(uuid4()),
            request_id=request_id,
            started_at=utc_now(),
        )
        return self._status

    async def stop_recording(self) -> RecordingStatus:
        if self._status.state != RecordingState.RECORDING:
            return self._status

        self._status = self._status.model_copy(
            update={"state": RecordingState.STOPPED, "stopped_at": utc_now()}
        )
        return self._status

    async def status(self) -> RecordingStatus:
        return self._status
