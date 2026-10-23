from fastapi import FastAPI
import movement

app = FastAPI()

@app.post("/neutral")
def neutral():
  movement.neutral()
  return {"status": "neutral"}

@app.post("/forward")
def forward(delta_us: float = 100.0):
  movement.forward(delta_us)
  return {"status": "forward", "delta_us": delta_us}

@app.post("/backward")
def backward(delta_us: float = 100.0):
  movement.backward(delta_us)
  return {"status": "backward", "delta_us": delta_us}

@app.post("/left")
def left(delta_us: float = 150.0):
  movement.left(delta_us)
  return {"status": "left", "delta_us": delta_us}

@app.post("/right")
def right(delta_us: float = 150.0):
  movement.right(delta_us)
  return {"status": "right", "delta_us": delta_us}
