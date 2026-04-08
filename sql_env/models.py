from pydantic import BaseModel
from typing import Optional, Dict, Any

class SQLObservation(BaseModel):
    task_id: str
    db_schema: str
    query: str
    error_message: Optional[str] = None
    expected_hint: Optional[str] = None
    step: int = 0

class SQLAction(BaseModel):
    sql: str

class SQLReward(BaseModel):
    value: float
    breakdown: Dict[str, float]
    done: bool
    info: Dict[str, Any]
