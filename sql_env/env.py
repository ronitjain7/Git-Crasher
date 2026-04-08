import sqlite3
from typing import Optional, Dict, Any, Tuple
from .models import SQLObservation, SQLAction, SQLReward
from .tasks import TASKS, load_fixtures
from .graders import grade_sql

class SQLReviewEnv:
    def __init__(self):
        self.conn = None
        self.task_id = "syntax-fix"
        self.step_count = 0
        self.max_steps = 10
        self.last_reward = 0.0
        self.done = False
        
    async def reset(self, task_id: str = "syntax-fix") -> SQLObservation:
        self.task_id = task_id
        if self.task_id not in TASKS:
            self.task_id = "syntax-fix"
            
        self.step_count = 0
        self.done = False
        self.last_reward = 0.0
        
        if self.conn:
             self.conn.close()
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        load_fixtures(self.conn)
        
        task_data = TASKS[self.task_id]
        
        return SQLObservation(
            task_id=self.task_id,
            db_schema=task_data["db_schema"],
            query=task_data["query"],
            error_message=None,
            expected_hint=task_data["expected_hint"],
            step=self.step_count
        )
        
    async def step(self, action: SQLAction) -> SQLReward:
        if self.done:
             return SQLReward(value=self.last_reward, breakdown={}, done=True, info={})
             
        self.step_count += 1
        
        task_data = TASKS[self.task_id]
        expected_sql = task_data["validation_query"]
        
        reward_val, breakdown, done, info = grade_sql(
            self.task_id, self.conn, action.sql, expected_sql, self.step_count, self.max_steps
        )
        
        self.last_reward = reward_val
        self.done = done
        
        return SQLReward(
            value=reward_val,
            breakdown=breakdown,
            done=done,
            info=info
        )
        
    def state(self) -> dict:
        return {
            "task_id": self.task_id,
            "current_step": self.step_count,
            "max_steps": self.max_steps,
            "last_reward": self.last_reward,
            "done": self.done
        }
