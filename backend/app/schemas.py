from typing import List, Optional
from pydantic import BaseModel, Field


class RedactIn(BaseModel):
    text: str = Field(min_length=1)
    max_new_tokens: Optional[int] = None


class RedactOut(BaseModel):
    safe_text: str                
    redacted_text: str            
    placeholders: List[str]       
    base_model: str
    adapter_repo: str
    seq_len: int
    max_new_tokens: int
    latency_ms: int


class HealthOut(BaseModel):
    status: str
    device: str
    threads: int
    base_model: str
    adapter_repo: str
