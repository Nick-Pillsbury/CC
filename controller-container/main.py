from fastapi import FastAPI, Query
from movement import CarController, PCA9685Driver

app = FastAPI()
car = CarController(PCA9685Driver())

@app.get("/status")
def get_status():
  return car.status()

@app.post("/steer")
def steer(deg: float = Query(0.0, ge=-45.0, le=45.0)):
  return car.set_angle(deg)

@app.post("/forward")
def forward(delta: float = Query(100.0, ge=0.0)):
  return car.forward(delta)

@app.post("/backward")
def backward(delta: float = Query(100.0, ge=0.0)):
  return car.backward(delta)

@app.post("/neutral")
def neutral():
  return car.neutral()