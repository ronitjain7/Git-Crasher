import asyncio
import os
import requests
import textwrap
from typing import List, Optional, Dict
from openai import OpenAI

# ── MANDATORY ENVIRONMENT VARIABLES ──────────────────────────────────────────
# Before submitting, ensure these are set in your environment.
API_BASE_URL = os.getenv("API_BASE_URL") or "https://router.huggingface.co/v1"
MODEL_NAME   = os.getenv("MODEL_NAME") or "Qwen/Qwen2.5-72B-Instruct"
API_KEY      = os.getenv("HF_TOKEN") or os.getenv("API_KEY") 
ENV_URL      = os.getenv("ENV_URL", "http://localhost:7860")
BENCHMARK    = "sql-review-env"

MAX_STEPS    = 8
SUCCESS_SCORE_THRESHOLD = 0.5  # normalized score in [0, 1]

# Max possible reward per step is 1.0 in this environment
MAX_TOTAL_REWARD = MAX_STEPS * 1.0

# ── Expanded SQLite-specific system prompt ────────────────────────────────────
SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert SQL agent operating against a live SQLite database.

    CRITICAL SQLITE SYNTAX RULES:
    - NEVER use AUTO_INCREMENT. SQLite uses: id INTEGER PRIMARY KEY
    - NEVER use VARCHAR(n). Use TEXT instead.
    - NEVER use INT — use INTEGER.
    - NEVER use BOOLEAN — use INTEGER (0 or 1).
    - NEVER use TINYINT, BIGINT, or FLOAT — use REAL.
    - Submit ONLY ONE single SQL statement. No semicolons.
    - Use strictly SQLite syntax only. 

    YOUR TASK:
    - Submit raw SQL — no markdown, no explanation.
    - Read feedback and CHANGE YOUR APPROACH if your score is not improving.
""").strip()

# ── STDOUT FORMAT (MANDATORY) ────────────────────────────────────────────────

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)

def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    # Formatting reward to 2 decimal places per spec
    print(f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}", flush=True)

def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    # Formatting score to 3 decimal places per spec
    print(f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}", flush=True)

# ── Helper Logic ────────────────────────────────────────────────────────────

def get_llm_action(client: OpenAI, messages: List[Dict]) -> str:
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.0,
            max_tokens=400
        )
        sql = response.choices[0].message.content.strip()
        if "```sql" in sql:
            sql = sql.split("```sql", 1)[1].split("```")[0].strip()
        elif "```" in sql:
            sql = sql.split("```")[1].split("```")[0].strip()
        return sql.strip().replace("\n", " ").replace("\r", " ")
    except Exception as exc:
        return "SELECT 1;"

def build_feedback_message(reward: float, error: Optional[str]) -> str:
    lines = [f"Score: {reward:.2f}"]
    if error:
        lines.append(f"Error: {error}")
    elif reward >= 0.99:
        lines.append("Excellent! Task complete.")
    elif reward >= 0.55:
        lines.append("Partial credit: output mismatch. Check WHERE clause.")
    else:
        lines.append("Query did not execute correctly.")
    return "\n".join(lines)

# ── Main task runner ──────────────────────────────────────────────────────────

async def run_task(task_id: str, client: OpenAI):
    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    try:
        # 1. Reset
        res = requests.post(f"{ENV_URL}/reset", json={"task_id": task_id})
        res.raise_for_status()
        obs = res.json()

        messages: List[Dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Task: {obs.get('expected_hint')}\nSchema: {obs.get('db_schema')}\nQuery: {obs.get('query')}"},
        ]

        # 2. Step Loop
        for step in range(1, MAX_STEPS + 1):
            action_sql = get_llm_action(client, messages)
            messages.append({"role": "assistant", "content": action_sql})

            step_res = requests.post(f"{ENV_URL}/step", json={"sql": action_sql})
            step_res.raise_for_status()
            reward_data = step_res.json()

            reward = float(reward_data["value"])
            done   = reward_data["done"]
            error_val = reward_data.get("info", {}).get("error") or None
            
            rewards.append(reward)
            steps_taken = step
            
            action_clean = repr(action_sql).replace("\\n", " ")
            log_step(step=step, action=action_clean, reward=reward, done=done, error=error_val)

            if done:
                break

            messages.append({"role": "user", "content": build_feedback_message(reward, error_val)})

        # 3. Scoring (Normalized per spec)
        score = sum(rewards) / MAX_TOTAL_REWARD if MAX_TOTAL_REWARD > 0 else 0.0
        score = min(max(score, 0.0), 1.0)
        success = score >= SUCCESS_SCORE_THRESHOLD

    except Exception as e:
        print(f"[DEBUG] Runtime error occurred: {e}", flush=True)

    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)


def main():
    if not API_KEY:
        print("[DEBUG] Missing API_KEY/HF_TOKEN environment variable.", flush=True)
        return

    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    TASKS = ["syntax-fix", "performance-tune", "schema-design", "aggregation-mastery", "data-mutation", "advanced-joins"]
    
    for t in TASKS:
        asyncio.run(run_task(t, client))


if __name__ == "__main__":
    main()
