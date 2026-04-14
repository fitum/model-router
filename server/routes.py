"""REST + SSE route handlers for the model-router dashboard."""

from __future__ import annotations

import asyncio
import json
import time

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from model_router.router import ModelRouter
from model_router.tracker import UsageTracker

try:
    from sse_starlette.sse import EventSourceResponse
    _SSE_AVAILABLE = True
except ImportError:
    _SSE_AVAILABLE = False


def make_routes(tracker: UsageTracker, router: ModelRouter) -> list[Route]:
    async def live_stats(request: Request) -> Response:
        """SSE stream -- emits live totals every 2 seconds."""
        if not _SSE_AVAILABLE:
            data = await tracker.get_live_totals()
            return JSONResponse(data)

        async def generator():
            while True:
                if await request.is_disconnected():
                    break
                data = await tracker.get_live_totals()
                yield {"data": json.dumps(data)}
                await asyncio.sleep(2)

        return EventSourceResponse(generator())

    async def session_stats(request: Request) -> JSONResponse:
        data = await tracker.get_session_stats()
        return JSONResponse(data)

    async def cost_by_model(request: Request) -> JSONResponse:
        since = request.query_params.get("since")
        since_ts = float(since) if since else None
        data = await tracker.get_cost_by_model(since_ts)
        return JSONResponse(data)

    async def task_history(request: Request) -> JSONResponse:
        limit = int(request.query_params.get("limit", 100))
        offset = int(request.query_params.get("offset", 0))
        data = await tracker.get_task_history(limit, offset)
        return JSONResponse(data)

    async def list_models(request: Request) -> JSONResponse:
        return JSONResponse(router.registry.to_dict_list())

    async def reload_models(request: Request) -> JSONResponse:
        try:
            router.reload_config()
            return JSONResponse({"status": "ok", "message": "models.yaml reloaded"})
        except Exception as exc:
            return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)

    async def preview_route(request: Request) -> JSONResponse:
        """Return routing decision for a prompt without executing."""
        body = await request.json()
        from model_router.models import TaskRequest, TaskType
        task_type_raw = body.get("task_type")
        req = TaskRequest(
            prompt=body.get("prompt", ""),
            task_type=TaskType(task_type_raw) if task_type_raw else None,
            quality_requirement=float(body.get("quality_requirement", 0.5)),
            cost_budget_usd=body.get("cost_budget_usd"),
        )
        decision = await router.route_task(req)
        return JSONResponse({
            "selected_model": decision.selected_model,
            "selected_model_string": decision.selected_model_string,
            "complexity_score": decision.complexity_score,
            "estimated_tokens": decision.estimated_tokens,
            "task_type": decision.task_type.value,
            "decomposed": decision.decomposed,
            "subtask_count": decision.subtask_count,
            "reasoning": decision.reasoning,
        })

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({
            "status": "ok",
            "version": "0.1.0",
            "session_id": tracker.session_id,
            "uptime_s": round(time.time() - _START_TIME, 1),
        })

    return [
        Route("/api/stats/live",         live_stats),
        Route("/api/stats/session",      session_stats),
        Route("/api/stats/cost-by-model", cost_by_model),
        Route("/api/history",            task_history),
        Route("/api/models",             list_models),
        Route("/api/models/reload",      reload_models, methods=["POST"]),
        Route("/api/route",              preview_route, methods=["POST"]),
        Route("/api/health",             health),
    ]


_START_TIME = time.time()
