"""ModelRouter -- the central orchestrator. Import this from other modules."""

from __future__ import annotations

import time
import uuid
from dataclasses import replace
from pathlib import Path

from model_router.decomposer import TaskDecomposer
from model_router.models import (
    ExecutionRecord,
    RoutedResult,
    RoutingDecision,
    TaskRequest,
    TaskType,
)
from model_router.optimizer import TokenOptimizer
from model_router.providers.base import BaseProvider
from model_router.providers.claude import ClaudeProvider
from model_router.registry import ModelRegistry
from model_router.scorer import ComplexityScorer
from model_router.tracker import UsageTracker

DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "models.yaml"


class ModelRouter:
    """
    Route any TaskRequest to the best model(s), execute it, track usage, return result.

    Usage from any module:
        from model_router import ModelRouter, TaskRequest, TaskType
        router = ModelRouter()
        result = await router.route_and_run(TaskRequest(prompt="..."))
    """

    def __init__(
        self,
        config_path: Path | None = None,
        tracker: UsageTracker | None = None,
    ) -> None:
        self.registry = ModelRegistry(config_path or DEFAULT_CONFIG)
        self.scorer = ComplexityScorer(self.registry)
        self.decomposer = TaskDecomposer(self.registry)
        self.optimizer = TokenOptimizer(
            cache_ttl_seconds=self.registry.routing.cache_ttl_seconds
        )
        self.tracker = tracker or UsageTracker()
        self._providers: dict[str, BaseProvider] = {
            "claude": ClaudeProvider(),
            # "openai": OpenAIProvider(),   # add more providers here
        }
        self._session_id = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def route_task(self, request: TaskRequest) -> RoutingDecision:
        """Analyse the request and return a routing decision WITHOUT executing."""
        _, decision = self.scorer.build_routing_decision(request)
        return decision

    async def route_and_run(self, request: TaskRequest) -> RoutedResult:
        """Full pipeline: optimise -> score -> decompose? -> execute -> track -> return."""
        wall_start = time.monotonic()

        # 1. Cache check (skip for large/multi-tool requests)
        if not request.allowed_tools:
            cache_key = self.optimizer.build_cache_key(
                request.prompt, request.task_type.value if request.task_type else "chat"
            )
            cached = self.optimizer.get_cached(cache_key)
            if cached:
                features, decision = self.scorer.build_routing_decision(request)
                return RoutedResult(
                    decision=decision,
                    result=cached,
                    records=[],
                    total_cost_usd=0.0,
                    total_input_tokens=0,
                    total_output_tokens=0,
                    duration_ms=int((time.monotonic() - wall_start) * 1000),
                )
        else:
            cache_key = None

        # 2. Compress prompt if over threshold
        compress_at = self.registry.routing.compress_threshold
        optimized_prompt = self.optimizer.compress_prompt(request.prompt, compress_at)
        if optimized_prompt != request.prompt:
            request = replace(request, prompt=optimized_prompt)

        # 3. Score and build routing decision
        features, decision = self.scorer.build_routing_decision(request)

        # 4. Execute: decomposed or direct
        all_records: list[ExecutionRecord] = []
        result_text: str | None = None
        combined = False

        if decision.decomposed:
            result_text, all_records = await self._run_decomposed(request, features, decision)
            combined = True
        else:
            result_text, record = await self._run_direct(request, decision)
            all_records = [record]

        # 5. Enrich records and track
        total_cost = 0.0
        total_in = 0
        total_out = 0
        for rec in all_records:
            rec.session_id = self._session_id
            rec.complexity_score = decision.complexity_score
            rec.decomposed = decision.decomposed
            # Estimate cost from registry if SDK didn't provide it
            if rec.cost_usd == 0.0 and rec.input_tokens > 0:
                rec.cost_usd = self.registry.estimate_cost(
                    decision.selected_model, rec.input_tokens, rec.output_tokens
                )
            total_cost += rec.cost_usd
            total_in += rec.input_tokens
            total_out += rec.output_tokens
            await self.tracker.record(rec)

        # 6. Cache successful result
        if cache_key and result_text:
            self.optimizer.set_cached(cache_key, result_text)

        return RoutedResult(
            decision=decision,
            result=result_text,
            records=all_records,
            total_cost_usd=round(total_cost, 8),
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            duration_ms=int((time.monotonic() - wall_start) * 1000),
            combined=combined,
        )

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------

    async def _run_direct(
        self, request: TaskRequest, decision: RoutingDecision
    ) -> tuple[str | None, ExecutionRecord]:
        model = self.registry.get(decision.selected_model)
        provider = self._providers.get(model.provider)
        if not provider:
            raise ValueError(f"No provider registered for '{model.provider}'")

        result_text, record = await provider.execute(
            request,
            model.model_string,
            decision.fallback_model_string,
        )
        record.model = model.model_string
        return result_text, record

    async def _run_decomposed(
        self, request: TaskRequest, features, decision: RoutingDecision
    ) -> tuple[str | None, list[ExecutionRecord]]:
        subtasks = self.decomposer.decompose(request, features)
        all_records: list[ExecutionRecord] = []
        subtask_results: list[str] = []

        for subtask in subtasks:
            # Build context from prior results if needed
            context_prefix = ""
            if subtask.context_from:
                prior = [subtask_results[i] for i in subtask.context_from
                         if i < len(subtask_results)]
                if prior:
                    context_prefix = "### Prior results:\n\n" + "\n\n---\n\n".join(prior) + "\n\n---\n\n"

            sub_prompt = context_prefix + subtask.prompt
            sub_model_id = subtask.model_hint or decision.selected_model
            sub_model = self.registry.get(sub_model_id)
            provider = self._providers.get(sub_model.provider)
            if not provider:
                raise ValueError(f"No provider for '{sub_model.provider}'")

            sub_request = replace(request, prompt=sub_prompt, task_type=subtask.task_type)
            result_text, record = await provider.execute(
                sub_request, sub_model.model_string, None
            )
            record.model = sub_model.model_string
            record.subtask_index = subtask.index
            all_records.append(record)
            subtask_results.append(result_text or "")

        combined = self.decomposer.combine(subtask_results)
        return combined, all_records

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def reload_config(self) -> None:
        """Hot-reload models.yaml without restarting."""
        self.registry.reload()

    @property
    def session_id(self) -> str:
        return self._session_id
