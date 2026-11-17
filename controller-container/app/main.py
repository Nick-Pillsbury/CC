"""HTTP API for driving the car."""
from fastapi import FastAPI
from models import MotorResponse, NeutralResponse, SteeringResponse
from movement import CarController

app = FastAPI(title="Controller API")
car = CarController()


@app.post("/forward", response_model=MotorResponse)
def forward(delta: float = 100.0):
    return car.forward(delta)


@app.post("/backward", response_model=MotorResponse)
def backward(delta: float = 100.0):
    return car.backward(delta)


@app.post("/left", response_model=SteeringResponse)
def left(deg: float = 25.0):
    return car.left(deg)


@app.post("/right", response_model=SteeringResponse)
def right(deg: float = 25.0):
    return car.right(deg)


@app.post("/steer", response_model=SteeringResponse)
def steer(deg: float = 0.0):
    return car.set_angle(deg)


@app.post("/neutral", response_model=NeutralResponse)
def neutral():
    return car.neutral()