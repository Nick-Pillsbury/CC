import board
import busio
from adafruit_pca9685 import PCA9685
from models import MotorResponse, NeutralResponse, SteeringResponse

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
        i2c = busio.I2C(board.SCL, board.SDA)
        self._pca = PCA9685(i2c)
        self._pca.frequency = PWM_FREQUENCY_HZ
        self.neutral()

    def _send(self, channel: int, pulse_us: float) -> None:
        self._pca.channels[channel].duty_cycle = int(pulse_us / PWM_PERIOD_US * 0xFFFF)

    def set_angle(self, deg: float = 0.0) -> SteeringResponse:
        angle = max(-MAX_STEER_DEG, min(MAX_STEER_DEG, float(deg)))
        pulse = STEER_CENTER_US + angle / MAX_STEER_DEG * STEER_RANGE_US
        self._send(STEERING_CHANNEL, pulse)
        return SteeringResponse(angle_deg=angle, steering_us=pulse)

    def left(self, deg: float = 25.0) -> SteeringResponse:
        return self.set_angle(-abs(deg))

    def right(self, deg: float = 25.0) -> SteeringResponse:
        return self.set_angle(abs(deg))

    def forward(self, delta_us: float = 100.0) -> MotorResponse:
        pulse = max(MOTOR_MAX_FORWARD_US, MOTOR_NEUTRAL_US - abs(float(delta_us)))
        self._send(MOTOR_CHANNEL, pulse)
        return MotorResponse(status="forward", motor_us=pulse)

    def backward(self, delta_us: float = 100.0) -> MotorResponse:
        pulse = min(MOTOR_MAX_BACKWARD_US, MOTOR_NEUTRAL_US + abs(float(delta_us)))
        self._send(MOTOR_CHANNEL, pulse)
        return MotorResponse(status="backwards", motor_us=pulse)

    def neutral(self) -> NeutralResponse:
        self._send(MOTOR_CHANNEL, MOTOR_NEUTRAL_US)
        self.set_angle(0.0)
        return NeutralResponse()