from fastapi import FastAPI
import stage1_movement as movement

app = FastAPI()

@app.post("/neutral")
def neutral():
  movement.neutral()
  return {"status": "neutral"}

@app.post("/forward")
def forward():
  movement.forward()
  return {"status": "forward"}

@app.post("/backward")
def backward():
  movement.backward()
  return {"status": "backward"}
