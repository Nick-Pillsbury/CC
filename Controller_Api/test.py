import time, board, busio
from adafruit_pca9685 import PCA9685

pca = PCA9685(busio.I2C(board.SCL, board.SDA))
pca.frequency = 50

def send(us):
    pca.channels[15].duty_cycle = int(us / 20000 * 0xFFFF)

def neutral():
    send(1550)

neutral()
time.sleep(5)
send(1000)
time.sleep(3)
neutral()




# 1550 nuetral
# 1450 - 1000 forward
# 1650 - 2000 backward
# channel 15 is motor
# channel 0 is servo