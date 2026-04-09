---
title: SQL Review Env
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# 🗄️ SQL Review Environment (`sql-review-env`)

An [OpenEnv](https://github.com/meta-pytorch/OpenEnv) compliant, enterprise-grade reinforcement learning environment designed to train and evaluate AI agents on real-world database engineering tasks — including SQL syntax debugging, query performance tuning, relational schema design, aggregation mastery, data mutation, and advanced join strategies.

---

## 📖 Overview

The **SQL Review Environment** simulates daily, high-stakes tasks performed by professional database engineers. Unlike toy environments, agents placed into this environment must write raw, functional SQL against a **live in-memory SQLite database**, observe the results, interpret errors, and iteratively improve their query until it is both **correct** and **efficient**.

**Key Architectural Features:**
- **Universal Intent-Based Grader:** A single deterministic grading engine that dynamically detects the SQL intent (DQL `SELECT`, DML `UPDATE/DELETE/INSERT`, DDL `CREATE TABLE`) and applies the appropriate state-comparison strategy.
- **Master Template Caching:** `reset()` uses native `sqlite3.Connection.backup()` to clone a pre-built master database into a fresh `:memory:` connection in under **2 milliseconds**, ensuring lightning-fast episode resets.
- **Realistic Fixture Data:** Pre-populated with **10,000+ rows** of e-commerce data (users, orders, products, line_items, reviews) generated deterministically via `Faker(seed=42)`.
- **Production Safety Guardrails:**
  - RAM capping via `PRAGMA max_page_count = 10000`
  - Query timeout via `sqlite3.Connection.set_progress_handler` (aborts at 1.5 seconds)
  - Destructive query penalty for unguarded `DROP`/`DELETE` commands
- **OpenEnv Full Spec Compliance:** Typed Pydantic models, `/reset`, `/step`, `/state`, `/health`, `/metadata`, `/schema`, `/mcp` endpoints — validated via `openenv validate`.

---

## 🎯 Tasks

The environment exposes **6 tasks** covering the full spectrum of SQL engineering skill, organized by difficulty:

| Task ID | Difficulty | Category | Core Objective |
| :--- | :---: | :--- | :--- |
| `syntax-fix` | **Easy** | Debugging | Fix deliberate syntax errors (`SELCET`, `WHRE`) so the query parses, executes, and returns the correct result set. |
| `performance-tune` | **Medium** | Optimization | Refactor a slow, full-table-scan subquery to use indexed joins. Graded on correctness **and** execution plan analysis. |
| `schema-design` | **Hard** | DDL | Write `CREATE TABLE` statements from a plain-text business requirement. Schema presence is verified against `sqlite_master`. |
| `aggregation-mastery` | **Medium** | Analytics | Write a `GROUP BY` + `HAVING` aggregate query. Result rows are hashed and compared against a ground-truth validation query. |
| `data-mutation` | **Medium** | DML | Execute a targeted `UPDATE` or `DELETE` with a `WHERE` clause. The full affected table is cloned, mutated, and compared state-to-state. |
| `advanced-joins` | **Hard** | Joins | Construct a `LEFT JOIN` (or multi-table join) that preserves `NULL` rows correctly. NULL-safe hash comparison is enforced. |

---

## 🏗️ Architecture: The Universal Grader

The core innovation of this environment is the **Universal Intent-Based Grader** in `sql_env/graders.py`. Rather than writing custom logic for each of the 6 tasks, it uses a single evaluation pipeline:

```
Agent SQL
    │
    ▼
┌─────────────────────────────────────┐
│   1. SYNTAX CHECK                   │
│   EXPLAIN <sql> → parse error?      │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│   2. INTENT DETECTION               │
│   SQL keyword → DQL / DML / DDL     │
└─────────────┬───────────────────────┘
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
  DQL        DML       DDL
(SELECT)  (UPDATE/   (CREATE)
           DELETE)
    │         │         │
    ▼         ▼         ▼
Run both  Clone DB  Check
agent +   twice,    sqlite_master
valid.    compare   for required
query,    final     table names
sort &    table
hash      state

              │
              ▼
┌─────────────────────────────────────┐
│   4. PERFORMANCE CHECK (DQL only)   │
│   EXPLAIN QUERY PLAN → index scan?  │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│   5. COMPOSE REWARD VECTOR          │
│   syntax + execution + correctness  │
│   + performance - penalties         │
└─────────────────────────────────────┘
```

---

## 📊 Interaction Spaces

### Observation Space (`SQLObservation`)

| Property | Type | Description |
| :--- | :--- | :--- |
| `task_id` | `string` | The active task being evaluated (e.g., `"performance-tune"`). |
| `db_schema` | `string` | Human-readable SQLite schema (`CREATE TABLE` statements) of the live database. |
| `query` | `string` | The starting SQL query state (often containing deliberate bugs to fix). |
| `expected_hint` | `string` | Natural language description of what the agent must accomplish. |
| `error_message` | `string \| null` | The last execution error returned by SQLite. `null` if clean. |
| `step` | `integer` | Current episode step count (max: 10). |

### Action Space (`SQLAction`)

| Property | Type | Description |
| :--- | :--- | :--- |
| `sql` | `string` | Raw SQL statement to execute against the live SQLite engine. |

---

## 🏆 Reward Function (Dense Signal)

The reward function provides granular **partial progress signals** so RL agents learn from every step — not just success or failure at the end of an episode.

Scores are strictly clamped to `[0.01, 0.99]` (never exactly 0 or 1 to avoid dead-zone gradient issues).

| Component | Max Weight | Trigger Condition |
| :--- | :---: | :--- |
| **Syntax** | `+0.30` | `EXPLAIN <sql>` passes the SQLite parser without error. |
| **Execution** | `+0.25` | The query executes against the live database without a runtime exception. |
| **Correctness** | `+0.35` | The sorted, hashed result set (or final table state for DML) matches the ground truth. |
| **Performance** | `+0.10` | `EXPLAIN QUERY PLAN` confirms the query uses an index scan, not a full table scan. *(DQL only)* |

**Penalties:**
| Penalty | Weight | Condition |
| :--- | :---: | :--- |
| Destructive Command | `-0.05` | `DROP` or unguarded `DELETE` (no `WHERE` clause) detected. |
| Step Timeout | `-0.10` | Agent exceeds `max_steps = 10` without completing the task. |

---

## 🚀 Getting Started

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/)
- Python 3.11+
- `pip install openenv-core`

### 1. Run via Docker (Recommended)

```bash
# Build the image
docker build -t sql-review-env .

# Run the container
docker run -p 7860:7860 sql-review-env
```

### 2. Local Python Setup

```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Start the server
python app.py
```

The Gradio UI will be available at `http://localhost:7860`.

---

### 💻 Running Inference

A standardized baseline agent script (`inference.py`) is included. It uses an LLM via the OpenAI client interface to autonomously attempt all tasks.

```bash
# Set your API credentials
export HF_TOKEN="your_token_here"
# OR
export OPENAI_API_KEY="your_key_here"

# Optional: override model or endpoint
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"

# Run the evaluation loop
python inference.py
```

The script emits structured logs in the **exact** OpenEnv standard format:
```
[START] task=syntax-fix env=sql-review-env model=Qwen/Qwen2.5-72B-Instruct
[STEP] step=1 action=SELECT ... reward=0.55 done=false error=null
[STEP] step=2 action=SELECT ... reward=0.90 done=false error=null
[END] success=true steps=2 score=0.900 rewards=0.55,0.90
```

---

## 📈 Baseline Scores

Results achieved using the baseline zero-shot agent (Qwen/Qwen2.5-72B-Instruct, max 8 steps):

| Task | Score | Notes |
| :--- | :---: | :--- |
| `syntax-fix` | **1.00** | Solved in 1–2 steps consistently. |
| `performance-tune` | **0.90** | Correctness achieved; occasional index miss costs -0.10. |
| `schema-design` | **0.90** | Frontier models occasionally hallucinate MySQL syntax (`AUTO_INCREMENT`). |
| `aggregation-mastery` | **0.85** | GROUP BY logic generally solid; HAVING clause occasionally omitted. |
| `data-mutation` | **0.85** | UPDATE/DELETE correctly scoped; minor WHERE clause precision issues. |
| `advanced-joins` | **0.75** | NULL preservation in LEFT JOINs challenges most zero-shot models. |

---

## 📁 Project Structure

```
sql-review-env/
├── app.py                  # Gradio UI + FastAPI app entry point
├── inference.py            # OpenEnv-compliant LLM evaluation script
├── requirements.txt        # Python dependencies
├── pyproject.toml          # Project metadata
├── uv.lock                 # Deterministic dependency lockfile
├── openenv.yaml            # OpenEnv environment metadata
├── Dockerfile              # Container definition (python:3.11-slim)
├── README.md               # This file
└── sql_env/
    ├── models.py           # Pydantic typed models (SQLObservation, SQLAction, SQLReward)
    ├── env.py              # Core environment logic (reset, step, state, timeouts, RAM cap)
    ├── graders.py          # Universal Intent-Based Grader (DQL/DML/DDL evaluation)
    ├── tasks.py            # Task definitions + master DB template cache
    └── server.py           # FastAPI route handlers (/reset /step /state /health /schema /mcp)
```

---

## 🧩 OpenEnv Compliance

| Endpoint | Method | Status |
| :--- | :--- | :---: |
| `/reset` | `POST` | ✅ |
| `/step` | `POST` | ✅ |
| `/state` | `GET` | ✅ |
| `/health` | `GET` | ✅ |
| `/metadata` | `GET` | ✅ |
| `/schema` | `GET` | ✅ |
| `/mcp` | `POST` | ✅ |

Validated via `openenv validate` — all checks pass.
