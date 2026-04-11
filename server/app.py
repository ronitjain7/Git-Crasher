from fastapi import FastAPI, Body, Request
from fastapi.responses import JSONResponse, RedirectResponse
from typing import Optional, Dict, Any
import asyncio

from sql_env.env import SQLReviewEnv
from sql_env.models import SQLObservation, SQLAction, SQLReward
from sql_env.tasks import TASKS

app = FastAPI(
    title="SQL Review Environment",
    description="OpenEnv RL environment for training AI agents to review, fix, and optimize SQL queries.",
    version="1.0.0",
)
env = SQLReviewEnv()
# Fix 5: Asyncio lock to prevent concurrent /reset + /step race conditions
# on the shared env singleton. Ensures one request at a time touches DB state.
env_lock = asyncio.Lock()

@app.on_event("shutdown")
async def on_shutdown():
    """Cleanly release the SQLite connection when the server stops."""
    env.close()

# ── Core game endpoints ──────────────────────────────────────────────────────

@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/ui")

@app.post("/reset", response_model=SQLObservation)
async def reset(payload: Optional[Dict[str, Any]] = Body(default=None)):
    task_id = "syntax-fix"
    if payload and "task_id" in payload:
        task_id = payload["task_id"]
    async with env_lock:
        return await env.reset(task_id=task_id)

@app.post("/step", response_model=SQLReward)
async def step(action: SQLAction):
    async with env_lock:
        return await env.step(action)

@app.get("/state")
def state():
    return env.state()

# ── Required OpenEnv runtime API endpoints ───────────────────────────────────

@app.get("/health")
def health():
    """Required by openenv validate: must return {"status": "healthy"}"""
    return {"status": "healthy"}

@app.get("/metadata")
def metadata():
    """Required by openenv validate: must return serialized task specs"""
    return {
        "name": "sql-review-env",
        "description": (
            "An OpenEnv reinforcement learning environment where AI agents learn to "
            "review, fix syntax errors, optimize performance, and design schemas for SQL queries."
        ),
        "version": "1.0.0",
        "tasks": [{"id": tid, "has_grader": True} for tid in TASKS.keys()],
    }

@app.get("/schema")
def schema():
    """Required by openenv validate: must return action, observation, and state schemas"""
    return {
        "action": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "The SQL query submitted by the agent"}
            },
            "required": ["sql"],
        },
        "observation": {
            "type": "object",
            "properties": {
                "task_id":       {"type": "string"},
                "db_schema":     {"type": "string"},
                "query":         {"type": "string"},
                "error_message": {"type": ["string", "null"]},
                "expected_hint": {"type": ["string", "null"]},
                "step":          {"type": "integer"},
            },
        },
        "state": {
            "type": "object",
            "properties": {
                "task_id":      {"type": "string"},
                "current_step": {"type": "integer"},
                "max_steps":    {"type": "integer"},
                "last_reward":  {"type": "number"},
                "done":         {"type": "boolean"},
            },
        },
    }

@app.post("/mcp")
async def mcp(request: Request):
    """Required by openenv validate: must return JSON-RPC 2.0 payload"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    return JSONResponse({
        "jsonrpc": "2.0",
        "id": body.get("id", None),
        "result": {
            "name": "sql-review-env",
            "description": "SQL Review OpenEnv MCP interface",
        },
    })
