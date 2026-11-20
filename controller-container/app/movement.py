import threading
import time
import board
import busio
from adafruit_pca9685 import PCA9685
from models import DriveState, MotorResponse, NeutralResponse, SteeringResponse, StatusResponse

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


class CarController:
    def __init__(self):
        self._i2c = busio.I2C(board.SCL, board.SDA)
        self._pca = PCA9685(self._i2c)
        self._pca.frequency = PWM_FREQUENCY_HZ
        self._lock = threading.Lock()
        self._state = DriveState(motor_us=MOTOR_NEUTRAL_US, steering_us=STEER_CENTER_US, angle_deg=0.0)
        self.neutral()

    def _send(self, channel: int, pulse_us: float) -> None:
        self._pca.channels[channel].duty_cycle = int(pulse_us / PWM_PERIOD_US * 0xFFFF)

    def _is_online(self, lock_timeout_s: float = 1.0) -> bool:
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

    def set_angle(self, deg: float = 0.0) -> SteeringResponse:
        angle = _clamp(float(deg), -MAX_STEER_DEG, MAX_STEER_DEG)
        pulse = STEER_CENTER_US + angle / MAX_STEER_DEG * STEER_RANGE_US
        with self._lock:
            self._send(STEERING_CHANNEL, pulse)
            self._state.angle_deg = angle
            self._state.steering_us = pulse
        return SteeringResponse(angle_deg=angle, steering_us=pulse)

    def left(self, deg: float = 25.0) -> SteeringResponse:
        return self.set_angle(-abs(deg))

    def right(self, deg: float = 25.0) -> SteeringResponse:
        return self.set_angle(abs(deg))

    def forward(self, delta_us: float = 100.0) -> MotorResponse:
        pulse = max(MOTOR_MAX_FORWARD_US, MOTOR_NEUTRAL_US - abs(float(delta_us)))
        self._set_motor(pulse)
        return MotorResponse(status="forward", motor_us=pulse)

    def backward(self, delta_us: float = 100.0) -> MotorResponse:
        pulse = min(MOTOR_MAX_BACKWARD_US, MOTOR_NEUTRAL_US + abs(float(delta_us)))
        self._set_motor(pulse)
        return MotorResponse(status="backwards", motor_us=pulse)

    def neutral(self) -> NeutralResponse:
        self._set_motor(MOTOR_NEUTRAL_US)
        self.set_angle(0.0)
        return NeutralResponse()

    def status(self) -> StatusResponse:
        with self._lock:
            online = self._is_online()
            state = self._state.model_copy()
        return StatusResponse(hardware_online=online, frequency_hz=self._pca.frequency, state=state)

    def _set_motor(self, pulse: float) -> None:
        with self._lock:
            self._send(MOTOR_CHANNEL, pulse)
            self._state.motor_us = pulse


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))