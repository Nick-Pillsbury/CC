import threading
import time
from typing import Literal, Protocol
from pydantic import BaseModel

STEERING_CHANNEL = 0
MOTOR_CHANNEL = 15

PWM_FREQUENCY_HZ = 50
PWM_PERIOD_US = 1_000_000 / PWM_FREQUENCY_HZ

MOTOR_NEUTRAL_US = 1550.0
MOTOR_MAX_FORWARD_US = 1200.0
MOTOR_MAX_BACKWARD_US = 1900.0
STEER_CENTER_US = 1500.0
STEER_RANGE_US = 250.0
MAX_STEER_DEG = 45.0


class DriveState(BaseModel):
    motor_us: float
    steering_us: float
    angle_deg: float


class SteeringResponse(BaseModel):
    angle_deg: float
    steering_us: float


class MotorResponse(BaseModel):
    status: Literal["forward", "backwards"]
    motor_us: float


class NeutralResponse(BaseModel):
    status: Literal["neutral"] = "neutral"


class StatusResponse(BaseModel):
    hardware_online: bool
    frequency_hz: float
    state: DriveState


class PWMDriver(Protocol):
    frequency: float
    def send(self, channel: int, pulse_us: float) -> None: ...
    def is_online(self) -> bool: ...


class PCA9685Driver:
    def __init__(self):
        import board
        import busio
        from adafruit_pca9685 import PCA9685
        self._i2c = busio.I2C(board.SCL, board.SDA)
        self._pca = PCA9685(self._i2c)
        self._pca.frequency = PWM_FREQUENCY_HZ

    @property
    def frequency(self) -> float:
        return self._pca.frequency

    def send(self, channel: int, pulse_us: float) -> None:
        self._pca.channels[channel].duty_cycle = int(pulse_us / PWM_PERIOD_US * 0xFFFF)

    def is_online(self, lock_timeout_s: float = 1.0) -> bool:
        try:
            deadline = time.monotonic() + lock_timeout_s
            while not self._i2c.try_lock():
                if time.monotonic() > deadline:
                    return False
                time.sleep(0.001)
            try:
                return len(self._i2c.scan()) > 0
            finally:
                self._i2c.unlock()
        except Exception:
            return False


class CarController:
    def __init__(self, pwm: PWMDriver):
        self._pwm = pwm
        self._lock = threading.Lock()
        self._state = DriveState(motor_us=MOTOR_NEUTRAL_US, steering_us=STEER_CENTER_US, angle_deg=0.0)
        self.neutral()

    def set_angle(self, deg: float = 0.0) -> SteeringResponse:
        angle = max(-MAX_STEER_DEG, min(MAX_STEER_DEG, float(deg)))
        pulse = STEER_CENTER_US + angle / MAX_STEER_DEG * STEER_RANGE_US
        with self._lock:
            self._pwm.send(STEERING_CHANNEL, pulse)
            self._state.angle_deg = angle
            self._state.steering_us = pulse
        return SteeringResponse(angle_deg=angle, steering_us=pulse)

    def forward(self, delta_us: float = 100.0) -> MotorResponse:
        pulse = max(MOTOR_MAX_FORWARD_US, MOTOR_NEUTRAL_US - abs(float(delta_us)))
        with self._lock:
            self._pwm.send(MOTOR_CHANNEL, pulse)
            self._state.motor_us = pulse
        return MotorResponse(status="forward", motor_us=pulse)

    def backward(self, delta_us: float = 100.0) -> MotorResponse:
        pulse = min(MOTOR_MAX_BACKWARD_US, MOTOR_NEUTRAL_US + abs(float(delta_us)))
        with self._lock:
            self._pwm.send(MOTOR_CHANNEL, pulse)
            self._state.motor_us = pulse
        return MotorResponse(status="backwards", motor_us=pulse)

    def neutral(self) -> NeutralResponse:
        with self._lock:
            self._pwm.send(MOTOR_CHANNEL, MOTOR_NEUTRAL_US)
            self._state.motor_us = MOTOR_NEUTRAL_US
        self.set_angle(0.0)
        return NeutralResponse()

    def status(self) -> StatusResponse:
        with self._lock:
            online = self._pwm.is_online()
            state = self._state.model_copy()
        return StatusResponse(hardware_online=online, frequency_hz=self._pwm.frequency, state=state)
