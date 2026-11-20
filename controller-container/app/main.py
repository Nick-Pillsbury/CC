"""HTTP API for driving the car."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query
from models import MotorResponse, NeutralResponse, SteeringResponse, StatusResponse
from movement import CarController

car = CarController()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    car.neutral()


app = FastAPI(title="Controller API", lifespan=lifespan)


@app.get("/status", response_model=StatusResponse)
def status():
    return car.status()


@app.post("/forward", response_model=MotorResponse)
def forward(delta: float = Query(100.0, allow_inf_nan=False)):
    return car.forward(delta)


@app.post("/backward", response_model=MotorResponse)
def backward(delta: float = Query(100.0, allow_inf_nan=False)):
    return car.backward(delta)


@app.post("/left", response_model=SteeringResponse)
def left(deg: float = Query(25.0, allow_inf_nan=False)):
    return car.left(deg)


@app.post("/right", response_model=SteeringResponse)
def right(deg: float = Query(25.0, allow_inf_nan=False)):
    return car.right(deg)


@app.post("/steer", response_model=SteeringResponse)
def steer(deg: float = Query(0.0, allow_inf_nan=False)):
    return car.set_angle(deg)


@app.post("/neutral", response_model=NeutralResponse)
def neutral():
    return car.neutral()