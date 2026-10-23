import board
import busio
from adafruit_pca9685 import PCA9685

i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c)
pca.frequency = 50

# Channels
STEERING_CHANNEL = 0
MOTOR_CHANNEL = 15

# Microsecond neutral points
MOTOR_NEUTRAL_US = 1550.0
STEER_CENTER_US = 1500.0

# Current state tracking
_state = {
  "motor_us": MOTOR_NEUTRAL_US,
  "steering_us": STEER_CENTER_US,
  "angle_deg": 0.0,
}

def _send(channel: int, us: float):
  """Raw 16-bit PWM pulse conversion."""
  pca.channels[channel].duty_cycle = int(us / 20000.0 * 0xFFFF)

def set_angle(deg: float = 0.0):
  """Sets steering from -45° (full left) to +45° (full right)."""
  clamped_deg = max(-45.0, min(45.0, float(deg)))
  target_us = STEER_CENTER_US + (clamped_deg / 45.0 * 250.0)
  _send(STEERING_CHANNEL, target_us)
  _state["angle_deg"] = clamped_deg
  _state["steering_us"] = target_us
  return {"angle_deg": clamped_deg, "steering_us": target_us}

def left(deg: float = 25.0):
  return set_angle(-abs(deg))

def right(deg: float = 25.0):
  return set_angle(abs(deg))

def forward(delta_us: float = 100.0):
  target_us = min(1900.0, MOTOR_NEUTRAL_US + abs(float(delta_us)))
  _send(MOTOR_CHANNEL, target_us)
  _state["motor_us"] = target_us
  return {"status": "forward", "motor_us": target_us}

def backward(delta_us: float = 100.0):
  target_us = max(1200.0, MOTOR_NEUTRAL_US - abs(float(delta_us)))
  _send(MOTOR_CHANNEL, target_us)
  _state["motor_us"] = target_us
  return {"status": "backward", "motor_us": target_us}

def neutral():
  _send(MOTOR_CHANNEL, MOTOR_NEUTRAL_US)
  set_angle(0.0)
  _state["motor_us"] = MOTOR_NEUTRAL_US
  return {"status": "neutral"}

def get_system_status():
  """Checks hardware communication and returns current state."""
  is_connected = False
  try:
    while not i2c.try_lock():
      pass
    addresses = i2c.scan()
    i2c.unlock()
    is_connected = len(addresses) > 0
  except Exception:
    is_connected = False

  return {
    "hardware_online": is_connected,
    "frequency_hz": pca.frequency,
    "state": _state
  }

# Start centered and stopped
neutral()
