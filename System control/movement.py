import board
import busio
from adafruit_pca9685 import PCA9685

i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c)
pca.frequency = 50

MOTOR_CH = 15
STEER_CH = 0

MOTOR_NEUTRAL = 1550 #forward: 1650-2000 #backward: 1450-1000
STEER_NEUTRAL = 1500

def send_motor(us):
  pca.channels[MOTOR_CH].duty_cycle = int(us / 20000 * 0xFFFF)

def send_steering(us):
  pca.channels[STEER_CH].duty_cycle = int(us / 20000 * 0xFFFF)

def neutral():
  send_motor(MOTOR_NEUTRAL)
  send_steering(STEER_NEUTRAL)

def forward(delta_us=100):
  send_motor(MOTOR_NEUTRAL + delta_us)

def backward(delta_us=100):
  send_motor(MOTOR_NEUTRAL - delta_us)

def left(delta_us=150):
  send_steering(STEER_NEUTRAL - delta_us)

def right(delta_us=150):
  send_steering(STEER_NEUTRAL + delta_us)
