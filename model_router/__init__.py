"""
model-router: intelligent AI model selection, orchestration, and cost tracking.

Quick start:
    from model_router import ModelRouter, TaskRequest, TaskType
    import anyio

    router = ModelRouter()
    result = anyio.run(router.route_and_run, TaskRequest(
        prompt="Implement a binary search function in Python",
        quality_requirement=0.7,
    ))
    print(result.result)
    print(f"Model used: {result.decision.selected_model}")
    print(f"Cost: ${result.total_cost_usd:.6f}")
"""

from model_router.models import (
    ExecutionRecord,
    RoutedResult,
    RoutingDecision,
    TaskFeatures,
    TaskRequest,
    TaskType,
)
from model_router.router import ModelRouter

__all__ = [
    "ModelRouter",
    "TaskRequest",
    "TaskType",
    "RoutedResult",
    "RoutingDecision",
    "TaskFeatures",
    "ExecutionRecord",
]

__version__ = "0.1.0"
