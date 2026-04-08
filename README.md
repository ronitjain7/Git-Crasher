---
title: SQL Review Env
emoji: 🛠️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
tags:
  - openenv
  - git
  - hackathon
---

# Git‑Crasher

A lightweight tool that deliberately introduces common Git mistakes into a repository, enabling you to test and improve your Git‑workflow robustness. It is designed as an OpenEnv environment for hackathon submissions.

## Quick Start

### Docker (recommended)

```bash
cd git-crasher
docker build -t git-crasher:latest .
docker run --rm -p 7860:7860 git-crasher:latest
```

The server will start on port **7860** exposing OpenEnv endpoints.

### Local (Python)

```bash
cd git-crasher
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
python -m inference
```

The `inference.py` script runs all available tasks (`syntax-fix`, `performance-tune`, `schema-design`).

## Server Setup

The FastAPI server is defined in `server/app.py` and launched via `uvicorn`.

```bash
uvicorn server.app:app --host 0.0.0.0 --port 7860
```

Health endpoint: `GET http://localhost:7860/health` returns `{ "status": "healthy", "service": "git-crasher" }`.

## Client / Usage

The client interacts with the environment through HTTP `reset` and `step` calls. Example workflow (performed by `inference.py`):

1. **Reset** – request a task (`task_id`).
2. **Step** – send an SQL‑like command (here a Git command) to fix the issue.
3. Repeat until `done` is true.

Available tasks (crash scenarios):

- `syntax-fix` – fix deliberately broken Git commands.
- `performance-tune` – optimise a series of Git operations.
- `schema-design` – simulate complex repository restructuring.

## Project Structure

```
git-crasher/
├── Dockerfile
├── README.md          # This file
├── inference.py          # CLI driver for tasks
├── openenv.yaml          # OpenEnv manifest
├── pyproject.toml
├── requirements.txt
├── server/
│   └── app.py           # FastAPI entry point
└── sql_env/             # Environment implementation
```

## Contribution

Contributions are welcome! Please fork the repository, create a feature branch, and open a pull request.

## License

This project is licensed under the MIT License – see the `LICENSE` file for details.

---
