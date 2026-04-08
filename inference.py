import os
import requests
from openai import OpenAI

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME   = os.getenv("MODEL_NAME",   "Qwen/Qwen2.5-72B-Instruct")
API_KEY      = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
MAX_STEPS    = 8
ENV_URL      = "http://localhost:7860"

def get_llm_action(client, prompt: str) -> str:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": "You are a SQL expert agent. You receive a task description and a broken or slow SQL query. Reply with ONLY valid SQL — no explanation, no markdown, no code fences. Just the raw SQL statement."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0
    )
    sql = response.choices[0].message.content.strip()
    if sql.startswith("```sql"):
        sql = sql[6:]
    if sql.endswith("```"):
        sql = sql[:-3]
    return sql.strip().replace("\n", " ").replace("\r", " ")

def run_task(task_id: str, client: OpenAI):
    try:
        res = requests.post(f"{ENV_URL}/reset", json={"task_id": task_id})
        res.raise_for_status()
        obs = res.json()
    except Exception as e:
        print(f"[START] task={task_id} env=sql-review-env model={MODEL_NAME}")
        print(f"[END] success=false steps=0 score=0.000 rewards=")
        return

    print(f"[START] task={task_id} env=sql-review-env model={MODEL_NAME}")

    done = False
    step_count = 0
    rewards = []
    success = False
    error_msg = "null"

    try:
        while not done and step_count < MAX_STEPS:
            prompt = f"Task: {obs.get('expected_hint')}\\nSchema: {obs.get('db_schema')}\\nQuery: {obs.get('query')}"
            action_sql = get_llm_action(client, prompt)

            step_res = requests.post(f"{ENV_URL}/step", json={"sql": action_sql})
            step_res.raise_for_status()
            reward_data = step_res.json()

            val = float(reward_data['value'])
            rewards.append(val)
            done = reward_data['done']

            formatted_reward = f"{val:.2f}"
            formatted_done = str(done).lower()

            action_clean = repr(action_sql).replace("\\n", " ")
            print(f"[STEP] step={step_count+1} action={action_clean} reward={formatted_reward} done={formatted_done} error=null")

            step_count += 1
            if done:
                break

        score = sum(rewards)
        score = max(0.0, min(1.0, score))
        if score >= 0.5:
             success = True

    except Exception as e:
        error_msg = repr(str(e)).replace("\\n", " ")
        score = 0.0
        success = False
        print(f"[STEP] step={step_count+1} action=null reward=0.00 done=true error={error_msg}")

    finally:
        f_score = f"{score:.3f}"
        f_success = str(success).lower()
        f_rewards = ",".join([f"{r:.2f}" for r in rewards])
        print(f"[END] success={f_success} steps={step_count} score={f_score} rewards={f_rewards}")

def main():
    if not API_KEY:
        print("Missing API_KEY or HF_TOKEN")
        return
        
    client = OpenAI(
        base_url=API_BASE_URL,
        api_key=API_KEY
    )

    TASKS = ["syntax-fix", "performance-tune", "schema-design"]
    for t in TASKS:
        run_task(t, client)

if __name__ == "__main__":
    main()
