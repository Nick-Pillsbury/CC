"""In-memory downstream clients for development before containers are ready."""

from uuid import UUID

from master_api.clients.errors import RecordingConflictError

from master_api.models import (
    ComponentHealth,
    ControlValues,
    HardwareTelemetry,
    MotionCommand,
    MotionResponse,
    RecordingStatus,
    StreamState,
    VideoStatus,
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

    async def stop(self) -> None:
        self.steering = 0.0
        self.throttle = 0.0

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
        self._status = VideoStatus(stream=StreamState.STOPPED)
        self._recordings: dict[UUID, RecordingStatus] = {}
        self._recording = RecordingStatus(state="idle")

    async def health(self) -> ComponentHealth:
        detail = "mock video ready" if self.ready else "mock video unavailable"
        return ComponentHealth(ready=self.ready, detail=detail)

    async def start_stream(self) -> VideoStatus:
        self._status = VideoStatus(stream=StreamState.RUNNING)
        return self._status

    async def stop_stream(self) -> VideoStatus:
        self._status = VideoStatus(stream=StreamState.STOPPED)
        return self._status

    async def status(self) -> VideoStatus:
        return self._status

    async def recording_status(self) -> RecordingStatus:
        return self._recording.model_copy()

    async def start_recording(self, request_id: UUID) -> RecordingStatus:
        if request_id in self._recordings:
            return self._recordings[request_id].model_copy()
        if self._recording.state == "recording":
            raise RecordingConflictError("video", "Another recording is active.")
        self._recording = RecordingStatus(state="recording", recording_id=request_id, started_at=utc_now())
        self._recordings[request_id] = self._recording
        return self._recording.model_copy()

    async def stop_recording(self, recording_id: UUID) -> RecordingStatus:
        current = self._recordings.get(recording_id)
        if current is None:
            raise RecordingConflictError("video", "Unknown recording.")
        if current.state == "recording":
            current = current.model_copy(update={"state": "stopped", "stopped_at": utc_now()})
            self._recordings[recording_id] = current
            if self._recording.recording_id == recording_id:
                self._recording = current
        return current.model_copy()
