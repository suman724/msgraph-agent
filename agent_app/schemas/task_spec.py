from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class Step:
    step_id: str
    name: str
    assigned_agent: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    retry_policy: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict) # To be populated after execution

@dataclass
class TaskSpec:
    intent: str
    entities: List[str] = field(default_factory=list)
    time_window: Optional[Dict[str, str]] = None
    constraints: Dict[str, Any] = field(default_factory=dict)
    steps: List[Step] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
