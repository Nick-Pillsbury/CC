from fastapi import FastAPI
import movement

app = FastAPI()

@app.get("/status")
def status():
  return movement.get_system_status()

@app.post("/forward")
def forward(delta: float = 100.0):
  return movement.forward(delta)

@app.post("/backward")
def backward(delta: float = 100.0):
  return movement.backward(delta)

@app.post("/left")
def left(deg: float = 25.0):
  return movement.left(deg)

@app.post("/right")
def right(deg: float = 25.0):
  return movement.right(deg)

@app.post("/steer")
def steer(deg: float = 0.0):
  return movement.set_angle(deg)

@app.post("/neutral")
def neutral():
  return movement.neutral()

