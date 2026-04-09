---
title: SQL Review Env
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# 🗄️ SQL Review Environment (`sql-review-env`)

An [OpenEnv](https://github.com/meta-pytorch/OpenEnv) compliant reinforcement learning environment designed to train AI agents in real-world SQL code review, debugging, and optimization tasks.

## 📖 Overview

The **SQL Review Environment** simulates a daily task for software engineers: reviewing and fixing SQL queries. Rather than simple multiple-choice questions, agents are placed in an interactive loop where they must write raw SQL, execute it against a live database, observe the results (or errors), and iterate until the query works efficiently. 

**Key Features:**
* **Live Deterministic Database:** Spins up an isolated, in-memory SQLite database (`:memory:`) on every `reset()`.
* **Realistic Data:** Pre-populated with over 10,000 rows of realistic e-commerce fixture data (users, orders, products, line_items, reviews) generated deterministically via the `Faker` library (seed 42).
* **Dense Reward Shaping:** Provides granular, partial rewards for syntactically valid code, clean execution, precise result matching, and performance optimization.
* **Exploit-Proof Grading:** Validates output rows using SHA-256 hashing to ensure agents achieve exact result set matches.

---

## 🎯 Tasks

The environment supports three distinct tasks, progressing from basic debugging to complex architectural design:

| Task ID | Difficulty | Objective | Grader Criteria |
| :--- | :---: | :--- | :--- |
| `syntax-fix` | **Easy** | Fix deliberate syntax errors (`SELCET`, `WHRE`) in a query so it successfully executes. | Query parses, executes cleanly, and matches expected output rows exactly. |
| `performance-tune` | **Medium** | Optimize a slow subquery that forces a full table scan on large fixture tables. | Result must match expected output, and `EXPLAIN QUERY PLAN` must confirm the use of indexed joins rather than full table scans. |
| `schema-design` | **Hard** | Design a normalized relational schema (CREATE TABLE statements) based on a plain-text business requirement. | Tables must execute properly, and required schemas must be present in `sqlite_master`. |

---

## 📊 Interaction Spaces

### Observation Space
The environment state (`SQLObservation`) returned to the agent after every step or reset.

| Property | Type | Description |
| :--- | :--- | :--- |
| `task_id` | `string` | The active task being evaluated (e.g., "performance-tune"). |
| `db_schema` | `string` | Human-readable representation of the active database schema. |
| `query` | `string` | The current SQL query state (often containing bugs to fix). |
| `expected_hint` | `string` | A natural language hint specifying the agent's goal. |
| `error_message` | `string` (nullable) | The last execution error (Null if successful). |
| `step` | `integer` | Current episode step count. |

### Action Space
The action (`SQLAction`) the agent takes to interact with the database.

| Property | Type | Description |
| :--- | :--- | :--- |
| `sql` | `string` | Raw SQL statement to be executed against the SQLite engine. |

---

## 🏆 Reward Function (Dense Signal)

Unlike binary (0/1) success metrics, this environment utilizes a dense reward structure (`SQLReward`) allowing RL agents to learn from partial progress. Scores are strictly clamped between `[0.0, 1.0]`.

* **+0.30 (Syntax):** `EXPLAIN <sql>` passes without SQLite parsing errors.
* **+0.25 (Execution):** Query executes against the database without runtime exceptions.
* **+0.35 (Correctness):** The SHA-256 hash of the resulting dataset perfectly matches the ground-truth validation query.
* **+0.10 (Performance):** Query plan analysis confirms optimal execution (e.g., not scanning full tables when indexes are available).

**Penalties:**
* **-0.05:** Submitting destructive commands (`DROP`/`DELETE`) without a `WHERE` clause.
* **-0.10:** Exceeding the maximum allowed steps (`max_steps = 10`) without resolving the task.

---

## 🚀 Getting Started

### Prerequisites
* [Docker](https://docs.docker.com/get-docker/)
* Python 3.10+
* OpenEnv Core: `pip install openenv-core`

### 1. Run via Docker (Recommended)
The easiest way to run the environment is via the provided container, which spins up the FastAPI server on port 7860.

```bash
# Build the image
docker build -t sql-env .

# Run the container
docker run -p 7860:7860 sql-env
```

### 2. Local Python Setup
Alternatively, run it natively using uvicorn:

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn sql_env.server:app --host 0.0.0.0 --port 7860
```

### 💻 Running Inference
We provide a standardized baseline script (`inference.py`) that uses an LLM (via the OpenAI client format) to solve the tasks.

Ensure you have your API credentials set. By default, this connects to the Hugging Face Serverless API router using Qwen/Qwen2.5-72B-Instruct.

```bash
# Set your Hugging Face or OpenAI Token
export HF_TOKEN="your_token_here"

# Run the evaluation loop
python inference.py
```

The inference script outputs logs perfectly formatted to the OpenEnv standard `[START]`, `[STEP]`, and `[END]` tags for automated evaluation.

---

## 📈 Baseline Scores
Results achieved using the baseline standard agent (Zero-shot, max 8 steps):

- Task 1 (syntax-fix): 1.0
- Task 2 (performance-tune): 0.9
- Task 3 (schema-design): 1.0

---
