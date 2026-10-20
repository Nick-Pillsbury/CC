import board
import busio
from adafruit_pca9685 import PCA9685

i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c)
pca.frequency = 50

def send(us):
  pca.channels[15].duty_cycle = int(us / 20000 * 0xFFFF)

def neutral():
  send(1550) 

def forward():
  send(1650) #range forward: 1650-2000

def backward():
  send(1450) #range backward: 1450-1000
