#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Model Router -- CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "buffer") and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer") and sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the dashboard web server."""
    import uvicorn
    from model_router.router import ModelRouter
    from model_router.tracker import UsageTracker
    from server.app import create_app

    tracker = UsageTracker()
    router = ModelRouter(tracker=tracker)
    app = create_app(tracker, router)

    print(f"Model Router dashboard -> http://localhost:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


async def _run(prompt: str, task_type: str | None, quality: float, budget: float | None) -> None:
    from model_router.models import TaskRequest, TaskType
    from model_router.router import ModelRouter
    from model_router.tracker import UsageTracker

    tracker = UsageTracker()
    router = ModelRouter(tracker=tracker)

    req = TaskRequest(
        prompt=prompt,
        task_type=TaskType(task_type) if task_type else None,
        quality_requirement=quality,
        cost_budget_usd=budget,
    )
    result = await router.execute(req)
    print(f"Model  : {result.decision.selected_model}")
    print(f"Tokens : {result.input_tokens + result.output_tokens}")
    print(f"Cost   : ${result.cost_usd:.5f}")
    print(f"Latency: {result.latency_ms}ms")
    print()
    print(result.content)


def cmd_run(args: argparse.Namespace) -> None:
    """Execute a single routed task from the command line."""
    prompt = args.prompt or sys.stdin.read()
    asyncio.run(_run(prompt, args.task_type, args.quality, args.budget))


async def _preview(prompt: str, task_type: str | None, quality: float, budget: float | None) -> None:
    from model_router.models import TaskRequest, TaskType
    from model_router.router import ModelRouter
    from model_router.tracker import UsageTracker

    tracker = UsageTracker()
    router = ModelRouter(tracker=tracker)

    req = TaskRequest(
        prompt=prompt,
        task_type=TaskType(task_type) if task_type else None,
        quality_requirement=quality,
        cost_budget_usd=budget,
    )
    decision = await router.route_task(req)
    print(json.dumps({
        "selected_model": decision.selected_model,
        "selected_model_string": decision.selected_model_string,
        "complexity_score": round(decision.complexity_score, 4),
        "task_type": decision.task_type,
        "estimated_tokens": decision.estimated_tokens,
        "decomposed": decision.decomposed,
        "subtask_count": decision.subtask_count,
        "reasoning": decision.reasoning,
    }, indent=2))


def cmd_preview(args: argparse.Namespace) -> None:
    """Preview routing decision without executing."""
    prompt = args.prompt or sys.stdin.read()
    asyncio.run(_preview(prompt, args.task_type, args.quality, args.budget))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="model-router",
        description="Intelligent AI model router for Claude.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # serve
    p_serve = sub.add_parser("serve", help="Start the dashboard server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.set_defaults(func=cmd_serve)

    # run
    p_run = sub.add_parser("run", help="Execute a routed task")
    p_run.add_argument("prompt", nargs="?", help="Prompt text (or pipe via stdin)")
    p_run.add_argument("--task-type", choices=["coding", "review", "docs", "reasoning", "chat"])
    p_run.add_argument("--quality", type=float, default=0.5)
    p_run.add_argument("--budget", type=float, default=None)
    p_run.set_defaults(func=cmd_run)

    # preview
    p_prev = sub.add_parser("preview", help="Preview routing decision (no execution)")
    p_prev.add_argument("prompt", nargs="?", help="Prompt text (or pipe via stdin)")
    p_prev.add_argument("--task-type", choices=["coding", "review", "docs", "reasoning", "chat"])
    p_prev.add_argument("--quality", type=float, default=0.5)
    p_prev.add_argument("--budget", type=float, default=None)
    p_prev.set_defaults(func=cmd_preview)

    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
