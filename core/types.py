from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal

ToolName = Literal["vector_rag", "graph_rag", "none"]

class TraceStep(BaseModel):
    step: int
    intent: str
    tool: ToolName
    tool_input: str
    observation: str
    reflection: str

class AgentResult(BaseModel):
    answer: str
    trace: List[TraceStep] = Field(default_factory=list)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
