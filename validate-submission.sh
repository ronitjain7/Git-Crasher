#!/usr/bin/env bash
# =============================================================================
#  OpenEnv Submission Validator — validate-submission.sh
#  Usage:  bash validate-submission.sh [PING_URL]
#  Example: bash validate-submission.sh http://127.0.0.1:7860
#
#  Runs 3 checks required by the hackathon pre-submission checklist:
#    Step 1 — Ping the running Space URL (checks /reset returns 200)
#    Step 2 — Docker build (checks Dockerfile is valid)
#    Step 3 — openenv validate (checks full OpenEnv spec compliance)
# =============================================================================

set -euo pipefail

PING_URL="${1:-http://127.0.0.1:7860}"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP() { date "+%H:%M:%S"; }
PASS="\033[0;32mPASSED\033[0m"
FAIL="\033[0;31mFAILED\033[0m"

echo ""
echo "========================================"
echo "  OpenEnv Submission Validator"
echo "========================================"
echo "[$(TIMESTAMP)] Repo:     $REPO_DIR"
echo "[$(TIMESTAMP)] Ping URL: $PING_URL"
echo ""

ISSUES=()
STEP_FAILED=0

# ── Step 1: Ping the running server ──────────────────────────────────────────
echo "[$(TIMESTAMP)] Step 1/3: Pinging server ($PING_URL/reset) ..."

RESET_PAYLOAD='{"task_id": "syntax-fix"}'
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$PING_URL/reset" \
  -H "Content-Type: application/json" \
  -d "$RESET_PAYLOAD" \
  --connect-timeout 10 \
  --max-time 20 2>/dev/null || echo "000")

if [ "$HTTP_STATUS" = "200" ]; then
  echo "[$(TIMESTAMP)] $PASS -- Server is live and /reset returns HTTP 200"
else
  echo "[$(TIMESTAMP)] $FAIL -- /reset returned HTTP $HTTP_STATUS (is 'python app.py' running?)"
  ISSUES+=("Server ping failed (HTTP $HTTP_STATUS) — start the server with: python app.py")
  STEP_FAILED=1
fi

# ── Step 2: Docker build ──────────────────────────────────────────────────────
echo "[$(TIMESTAMP)] Step 2/3: Running docker build ..."

if [ ! -f "$REPO_DIR/Dockerfile" ]; then
  echo "[$(TIMESTAMP)] $FAIL -- No Dockerfile found in $REPO_DIR"
  ISSUES+=("Missing Dockerfile")
  STEP_FAILED=1
else
  echo "[$(TIMESTAMP)]   Found Dockerfile in $REPO_DIR"
  if docker build -t sql-review-env-test "$REPO_DIR" --quiet 2>/dev/null; then
    echo "[$(TIMESTAMP)] $PASS -- Docker build succeeded"
  else
    DOCKER_LOG=$(docker build -t sql-review-env-test "$REPO_DIR" 2>&1 | tail -20)
    echo "[$(TIMESTAMP)] $FAIL -- Docker build failed"
    echo "$DOCKER_LOG"
    ISSUES+=("Docker build failed — see output above")
    STEP_FAILED=1
  fi
fi

# ── Step 3: openenv validate ──────────────────────────────────────────────────
echo "[$(TIMESTAMP)] Step 3/3: Running openenv validate ..."

# Auto-detect openenv binary (supports local venv on Windows + Linux)
OPENENV_BIN=""
for candidate in \
  "./.venv/Scripts/openenv" \
  "./.venv/bin/openenv" \
  "$(which openenv 2>/dev/null || true)"; do
  if [ -n "$candidate" ] && [ -f "$candidate" ]; then
    OPENENV_BIN="$candidate"
    break
  fi
done

if [ -z "$OPENENV_BIN" ]; then
  echo "[$(TIMESTAMP)] $FAIL -- 'openenv' not found. Run: pip install openenv-core"
  ISSUES+=("openenv binary not found — run: pip install openenv-core")
  STEP_FAILED=1
else
  echo "[$(TIMESTAMP)]   Using openenv at: $OPENENV_BIN"
  if VALIDATE_OUT=$("$OPENENV_BIN" validate "$PING_URL" 2>&1); then
    echo "[$(TIMESTAMP)] $PASS -- openenv validate passed"
  else
    echo "[$(TIMESTAMP)] $FAIL -- openenv validate failed"
    echo "$VALIDATE_OUT"
    # Extract specific failures
    while IFS= read -r line; do
      if echo "$line" | grep -qE "^\s*-\s+"; then
        ISSUES+=("$line")
      fi
    done <<< "$VALIDATE_OUT"
    STEP_FAILED=1
  fi
fi

# ── Final Summary ─────────────────────────────────────────────────────────────
echo ""
echo "========================================"
if [ "$STEP_FAILED" -eq 0 ]; then
  echo -e "\033[0;32m  ALL CHECKS PASSED — Ready for submission!\033[0m"
  echo "========================================"
  echo ""
  echo "  Next steps:"
  echo "  1. git push to GitHub (both users)"
  echo "  2. git push to Hugging Face Spaces"
  echo "  3. Submit your HF Space URL to the hackathon portal"
  echo ""
  exit 0
else
  echo -e "\033[0;31m  VALIDATION FAILED\033[0m"
  echo "========================================"
  echo ""
  echo "Issues found:"
  for issue in "${ISSUES[@]}"; do
    echo "  - $issue"
  done
  echo ""
  exit 1
fi
