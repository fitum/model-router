"""Core data structures for the model router."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskType(str, Enum):
    CODING = "coding"
    REVIEW = "review"
    DOCS = "docs"
    REASONING = "reasoning"
    CHAT = "chat"


@dataclass
class TaskRequest:
    """Everything needed to route and execute a task."""
    prompt: str
    task_type: TaskType | None = None        # auto-detected if None
    quality_requirement: float = 0.5         # 0.0 (speed/cheap) to 1.0 (best)
    cost_budget_usd: float | None = None     # hard ceiling; None = unlimited
    cwd: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    system_prompt: str | None = None
    max_turns: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class TaskFeatures:
    """Extracted features used by the scorer."""
    char_count: int
    estimated_tokens: int
    keyword_complexity: float        # 0.0 to 1.0
    task_type: TaskType
    has_code: bool
    has_multifile: bool
    has_architecture: bool
    quality_requirement: float
    cost_budget_usd: float | None


@dataclass
class RoutingDecision:
    """The scorer's verdict — what model(s) to use and why."""
    selected_model: str              # model ID (e.g. "claude-opus-4-6")
    selected_model_string: str       # actual SDK string
    fallback_model: str | None
    fallback_model_string: str | None
    complexity_score: float
    estimated_tokens: int
    task_type: TaskType
    decomposed: bool
    subtask_count: int
    reasoning: str


@dataclass
class ExecutionRecord:
    """One row in the usage tracking database."""
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    model: str = ""
    task_type: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    timestamp: float = field(default_factory=time.time)
    complexity_score: float = 0.0
    decomposed: bool = False
    subtask_index: int = -1          # -1 means not decomposed
    success: bool = True
    error: str | None = None


@dataclass
class RoutedResult:
    """Final return value from ModelRouter.route_and_run()."""
    decision: RoutingDecision
    result: str | None
    records: list[ExecutionRecord]
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    duration_ms: int
    combined: bool = False           # True if subtask results were merged
