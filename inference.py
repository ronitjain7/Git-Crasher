import asyncio
import os
import requests
import textwrap
from typing import List, Optional, Dict
from openai import OpenAI

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME   = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN     = os.getenv("HF_TOKEN")

if HF_TOKEN is None:
    raise ValueError("HF_TOKEN environment variable is required")

API_KEY      = HF_TOKEN
MAX_STEPS    = 8
ENV_URL      = os.getenv("ENV_URL", "http://localhost:7860")
BENCHMARK    = "sql-review-env"

SUCCESS_SCORE_THRESHOLD = 0.5

# ── Expanded SQLite-specific system prompt ────────────────────────────────────
SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert SQL agent operating against a live SQLite database.

    CRITICAL SQLITE SYNTAX RULES — violations will score 0.01:
    - NEVER use AUTO_INCREMENT. SQLite uses: id INTEGER PRIMARY KEY (auto-increments implicitly)
    - NEVER use VARCHAR(n). Use TEXT instead.
    - NEVER use INT — use INTEGER.
    - NEVER use BOOLEAN — use INTEGER (0 or 1).
    - NEVER use TINYINT, BIGINT, or FLOAT — use REAL for decimals.
    - Column and table names are case-sensitive — match the schema exactly.
    - Submit ONLY ONE single SQL statement. Do not combine multiple statements with semicolons.
    - Do not use CREATE INDEX. Assume indexes already exist in the database.
    - Use strictly SQLite syntax only. No MySQL, PostgreSQL, or MSSQL syntax.

    YOUR TASK:
    - Read the task hint and schema carefully.
    - Submit ONLY raw SQL — no markdown, no code fences, no explanation.
    - After each step, you will receive your score and any error message.
    - Read the feedback carefully and CHANGE YOUR APPROACH if your score is not improving.
    - If you get the same score twice in a row, your current strategy is wrong — try something different.
""").strip()

# ── Logging helpers — DO NOT MODIFY (OpenEnv spec) ───────────────────────────

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)

def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}", flush=True)

def log_end(success: bool, steps: int, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={str(success).lower()} steps={steps} rewards={rewards_str}", flush=True)

# ── Fix 1 & 3: Stateful LLM call with rolling conversation history ────────────

def get_llm_action(client: OpenAI, messages: List[Dict]) -> str:
    """Call the LLM with the full conversation history so the agent can self-correct."""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.0,
            max_tokens=400
        )
        sql = response.choices[0].message.content.strip()
        # Strip markdown fences if model adds them despite instructions
        if "```sql" in sql:
            sql = sql.split("```sql", 1)[1].split("```")[0].strip()
        elif "```" in sql:
            sql = sql.split("```")[1].split("```")[0].strip()
        return sql.strip().replace("\n", " ").replace("\r", " ")
    except Exception as exc:
        print(f"[WARNING] LLM API limit reached or request failed. Falling back to safe query. Error: {exc}", flush=True)
        return "SELECT 1;"


def build_initial_user_message(obs: dict) -> str:
    """Construct the first user message from the reset() observation."""
    return textwrap.dedent(f"""
        Task:   {obs.get('expected_hint', 'No hint provided')}
        Schema: {obs.get('db_schema', 'No schema provided')}

        Starting query (may contain bugs):
        {obs.get('query', '')}

        Submit a corrected, optimized SQL query.
    """).strip()


def build_feedback_message(reward: float, error: Optional[str], prev_reward: float, stuck_count: int) -> str:
    """
    Construct the environment's feedback as the next user turn.
    Fix 4: Inject a strategy-change instruction if the agent is stuck.
    """
    lines = [f"Score: {reward:.2f}"]

    if error:
        lines.append(f"Error: {error}")
        lines.append("Your query caused an error. Read the error message above and fix it in your next submission.")
    elif reward >= 0.99:
        lines.append("Excellent! Task complete.")
    elif reward >= 0.85:
        lines.append("Very close! Small refinement needed — check column names and filter conditions.")
    elif reward >= 0.55:
        lines.append(
            "Partial credit: your query executes but the results do not match the expected output. "
            "Check your WHERE clause conditions and column selections carefully."
        )
    else:
        lines.append("Your query did not execute correctly. Review the SQLite syntax rules.")

    # Fix 4: Strategy-change trigger — fire after 2 consecutive identical scores
    if stuck_count >= 2:
        lines.append(
            "\nWARNING: You have submitted the same or equivalent query multiple times with the same score. "
            "Your current approach is NOT working. You MUST try a fundamentally different query structure. "
            "Re-read the schema, reconsider which columns and tables to use, and write a completely new query."
        )

    return "\n".join(lines)


# ── Main task runner ──────────────────────────────────────────────────────────

def run_task(task_id: str, client: OpenAI):
    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    try:
        # Reset the environment for this task
        res = requests.post(f"{ENV_URL}/reset", json={"task_id": task_id})
        res.raise_for_status()
        obs = res.json()

        # Fix 1: Initialize conversation history with system prompt + first user message
        messages: List[Dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_initial_user_message(obs)},
        ]

        prev_reward: float = -1.0
        stuck_count: int = 0

        for step in range(1, MAX_STEPS + 1):
            # Get the LLM action using full conversation history
            action_sql = get_llm_action(client, messages)

            # Fix 1: Append agent's action to conversation as assistant turn
            messages.append({"role": "assistant", "content": action_sql})

            # Submit action to environment
            step_res = requests.post(f"{ENV_URL}/step", json={"sql": action_sql})
            step_res.raise_for_status()
            reward_data = step_res.json()

            reward = float(reward_data["value"])
            done   = reward_data["done"]
            error_val = reward_data.get("info", {}).get("error") or None
            if error_val:
                error_val = repr(error_val).replace("\\n", " ")

            rewards.append(reward)
            steps_taken = step

            action_clean = repr(action_sql).replace("\\n", " ")
            log_step(step=step, action=action_clean, reward=reward, done=done, error=error_val)

            if done:
                break

            # Fix 4: Track consecutive identical scores for strategy trigger
            if abs(reward - prev_reward) < 0.001:
                stuck_count += 1
            else:
                stuck_count = 0
            prev_reward = reward

            # Fix 1 & 3: Append environment feedback back into conversation as next user turn
            feedback = build_feedback_message(
                reward=reward,
                error=reward_data.get("info", {}).get("error"),
                prev_reward=prev_reward,
                stuck_count=stuck_count
            )
            messages.append({"role": "user", "content": feedback})

        score = sum(rewards) / float(steps_taken) if steps_taken > 0 else 0.0
        score = min(max(score, 0.0), 1.0)
        success = score >= SUCCESS_SCORE_THRESHOLD

    except Exception as e:
        print(f"[DEBUG] Runtime error occurred: {e}", flush=True)

    finally:
        if not rewards:
            rewards = [0.01]
        log_end(success=success, steps=steps_taken, rewards=rewards)


def main():
    if not API_KEY:
        print("[DEBUG] Missing API_KEY, HF_TOKEN, or OPENAI_API_KEY environment variable.", flush=True)
        return

    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    TASKS = [
        "syntax-fix",
        "performance-tune",
        "schema-design",
        "aggregation-mastery",
        "data-mutation",
        "advanced-joins",
    ]
    for t in TASKS:
        run_task(t, client)


if __name__ == "__main__":
    main()
