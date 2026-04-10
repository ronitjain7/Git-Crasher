# Mock verification script to prove inference.py format compliance
import asyncio
from unittest.mock import MagicMock, patch
import os

# Set dummy env vars
os.environ["API_BASE_URL"] = "http://mock-api.com/v1"
os.environ["MODEL_NAME"] = "Mock-Model-72B"
os.environ["HF_TOKEN"] = "mock_hf_token"
os.environ["ENV_URL"] = "http://localhost:7860"

import inference

async def mock_run_task():
    # Mocking the requests.post for /reset and /step
    with patch("requests.post") as mock_post:
        # Step 1: Mock Reset Response
        mock_post.return_value.json.return_value = {
            "task_id": "syntax-fix",
            "db_schema": "users(id, name)",
            "query": "SELECT * FORM users",
            "expected_hint": "Fix the typo in FORM",
            "error_message": None,
            "step": 0
        }
        mock_post.return_value.raise_for_status = MagicMock()

        # Step 2: Mock LLM Response
        with patch("inference.get_llm_action") as mock_llm:
            mock_llm.return_value = "SELECT * FROM users;"

            # Step 3: Mock Step Response
            mock_post.return_value.json.side_effect = [
                # Reset response
                {
                    "task_id": "syntax-fix",
                    "db_schema": "users(id, name)",
                    "query": "SELECT * FORM users",
                    "expected_hint": "Fix the typo in FORM",
                },
                # Step 1 response
                {
                    "value": 0.99,
                    "done": True,
                    "info": {"error": None}
                }
            ]

            # Trigger the actual run_task logic
            client = MagicMock()
            await inference.run_task("syntax-fix", client)

if __name__ == "__main__":
    asyncio.run(mock_run_task())
