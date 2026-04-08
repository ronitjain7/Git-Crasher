from fastapi import FastAPI, Body
from typing import Optional, Dict, Any

from .env import SQLReviewEnv
from .models import SQLObservation, SQLAction, SQLReward

app = FastAPI()
env = SQLReviewEnv()

@app.get("/")
def read_root():
    return {"status": "ok", "message": "SQL Review Env API is running."}

@app.post("/reset", response_model=SQLObservation)
async def reset(payload: Optional[Dict[str, Any]] = Body(default=None)):
    task_id = "syntax-fix"
    if payload and "task_id" in payload:
        task_id = payload["task_id"]
    return await env.reset(task_id=task_id)

@app.post("/step", response_model=SQLReward)
async def step(action: SQLAction):
    return await env.step(action)

@app.get("/state")
def state():
    return env.state()
