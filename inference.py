import asyncio
import os
import requests
import textwrap
from typing import List, Optional
from openai import OpenAI

API_BASE_URL = os.getenv("API_BASE_URL") or "https://router.huggingface.co/v1"
MODEL_NAME   = os.getenv("MODEL_NAME") or "Qwen/Qwen2.5-72B-Instruct"
API_KEY      = os.getenv("HF_TOKEN") or os.getenv("API_KEY") or os.getenv("OPENAI_API_KEY")
MAX_STEPS    = 8
ENV_URL      = os.getenv("ENV_URL", "http://localhost:7860")
BENCHMARK    = "sql-review-env"

SUCCESS_SCORE_THRESHOLD = 0.5 

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)

def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}", flush=True)

def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}", flush=True)

def get_llm_action(client: OpenAI, prompt: str) -> str:
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a SQL expert agent. You receive a task description and a broken or slow SQL query. Reply with ONLY valid SQL — no explanation, no markdown. Just the raw SQL statement."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=150
        )
        sql = response.choices[0].message.content.strip()
        if sql.startswith("```sql"): sql = sql[6:]
        if sql.endswith("```"): sql = sql[:-3]
        return sql.strip().replace("\n", " ").replace("\r", " ")
    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", flush=True)
        return "SELECT 1;"

def run_task(task_id: str, client: OpenAI):
    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)
    
    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    try:
        res = requests.post(f"{ENV_URL}/reset", json={"task_id": task_id})
        res.raise_for_status()
        obs = res.json()
        
        for step in range(1, MAX_STEPS + 1):
            prompt = f"Task: {obs.get('expected_hint')}\nSchema: {obs.get('db_schema')}\nQuery: {obs.get('query')}"
            action_sql = get_llm_action(client, prompt)

            step_res = requests.post(f"{ENV_URL}/step", json={"sql": action_sql})
            step_res.raise_for_status()
            reward_data = step_res.json()

            reward = float(reward_data['value'])
            done = reward_data['done']
            
            error_val = reward_data.get('info', {}).get('error')
            if error_val:
                error_val = repr(error_val).replace("\\n", " ")
                
            rewards.append(reward)
            steps_taken = step
            
            action_clean = repr(action_sql).replace("\\n", " ")
            log_step(step=step, action=action_clean, reward=reward, done=done, error=error_val)

            if done:
                break

        # Since SQL paths cap easily at 0.99 early, normalizing the sum over max steps.
        # However, OpenEnv standard is the total sum, normalized to [0,1].
        # In our env, 1 success ends the episode with ~1.0.
        score = sum(rewards) / float(steps_taken) if steps_taken > 0 else 0.0
        score = min(max(score, 0.0), 1.0)
        success = score >= SUCCESS_SCORE_THRESHOLD

    except Exception as e:
        print(f"[DEBUG] Runtime error occurred: {e}", flush=True)
        
    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

def main():
    if not API_KEY:
        print("Missing API_KEY or HF_TOKEN")
        return
        
    client = OpenAI(
        base_url=API_BASE_URL,
        api_key=API_KEY
    )

    TASKS = ["syntax-fix", "performance-tune", "schema-design", "aggregation-mastery", "data-mutation", "advanced-joins"]
    for t in TASKS:
        run_task(t, client)

if __name__ == "__main__":
    main()
