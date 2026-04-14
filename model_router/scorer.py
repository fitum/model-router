"""Complexity scorer -- analyses a task and selects the best model."""

from __future__ import annotations

import re

from model_router.models import TaskFeatures, TaskRequest, TaskType, RoutingDecision
from model_router.registry import ModelRegistry

# ---------------------------------------------------------------------------
# Keyword maps: (pattern, weight) pairs.  Positive = harder, negative = easier.
# ---------------------------------------------------------------------------
_COMPLEXITY_KEYWORDS: list[tuple[str, float]] = [
    # Hard / high-value signals
    (r"\barchitect\b|\barchitecture\b|\bsystem design\b", 0.30),
    (r"\boptimiz\b|\bperformance\b|\bbottleneck\b|\bprofil\b", 0.20),
    (r"\brefactor\b|\bdebt\b|\bmigrat\b", 0.20),
    (r"\bdebug\b|\btrace\b|\broot cause\b|\bdiagnos\b", 0.20),
    (r"\bimplement\b|\bbuild\b|\bcreate\b|\bwrite\b", 0.15),
    (r"\bsecurity\b|\bvulnerabilit\b|\bauthentication\b|\bauthorization\b", 0.15),
    (r"\bscal\b|\bconcurren\b|\bdistributed\b|\bmicroservice\b", 0.25),
    (r"\btradeoff\b|\btrade-off\b|\bpros and cons\b|\bcompare\b", 0.20),
    # Easy / low-value signals
    (r"\bsummariz\b|\bsummar[iy]\b|\bbrief\b|\boverview\b", -0.20),
    (r"\bsimple\b|\bquick\b|\bbasic\b|\beasy\b", -0.25),
    (r"\bexplain\b|\bwhat is\b|\bhow does\b|\bdescribe\b", -0.15),
    (r"\blist\b|\bbullet\b|\benumerat\b", -0.10),
    (r"\bfix typo\b|\bformat\b|\brendering\b|\bspelling\b", -0.20),
]

_TASK_TYPE_SIGNALS: dict[TaskType, list[str]] = {
    TaskType.CODING:    [r"\bcode\b", r"\bfunction\b", r"\bclass\b", r"\bimplement\b",
                         r"\bbug\b", r"```", r"\bapi\b", r"\bmodule\b"],
    TaskType.REVIEW:    [r"\breview\b", r"\baudit\b", r"\bcheck\b", r"\blook at\b",
                         r"\bfeedback\b", r"\bpull request\b", r"\bpr\b"],
    TaskType.DOCS:      [r"\bdocument\b", r"\breadme\b", r"\bguide\b", r"\bchangelog\b",
                         r"\binstruction\b", r"\bexplain\b"],
    TaskType.REASONING: [r"\banalyze\b", r"\banalyse\b", r"\breason\b", r"\bthink\b",
                         r"\bplan\b", r"\bdesign\b", r"\barchitect\b", r"\bstrategy\b"],
    TaskType.CHAT:      [r"\bhello\b", r"\bhi\b", r"\bhelp\b", r"\bquestion\b",
                         r"\bwhat\b", r"\bhow\b", r"\bwhy\b"],
}


class ComplexityScorer:
    def __init__(self, registry: ModelRegistry) -> None:
        self._registry = registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_features(self, request: TaskRequest) -> TaskFeatures:
        prompt = request.prompt.lower()
        has_code = bool(re.search(r"```|\bdef \b|\bclass \b|\bfunction\b|\bconst \b|\bvar \b", prompt))
        cfg = self._registry.token_estimation
        cpt = cfg.code_chars_per_token if has_code else cfg.prose_chars_per_token
        estimated_tokens = int(len(request.prompt) / cpt * cfg.overhead_factor)

        return TaskFeatures(
            char_count=len(request.prompt),
            estimated_tokens=estimated_tokens,
            keyword_complexity=self._keyword_score(prompt),
            task_type=request.task_type or self._detect_task_type(prompt),
            has_code=has_code,
            has_multifile=self._has_multifile(prompt),
            has_architecture=bool(re.search(
                r"\barchitect\b|\bsystem design\b|\bcomponent\b|\bmodule\b", prompt
            )),
            quality_requirement=request.quality_requirement,
            cost_budget_usd=request.cost_budget_usd,
        )

    def composite_score(self, features: TaskFeatures) -> float:
        token_score = min(features.estimated_tokens / 8000, 1.0)
        score = (
            0.35 * token_score
            + 0.30 * features.keyword_complexity
            + 0.20 * features.quality_requirement
            + 0.10 * (1.0 if features.has_architecture else 0.0)
            + 0.05 * (1.0 if features.has_multifile else 0.0)
        )
        return round(min(max(score, 0.0), 1.0), 4)

    def select_model(self, features: TaskFeatures) -> str:
        """Return the model ID best suited to the task."""
        score = self.composite_score(features)
        cfg = self._registry.routing

        # Hard budget override: pick best affordable model
        if features.cost_budget_usd is not None:
            affordable = self._registry.models_within_budget(
                features.cost_budget_usd, features.estimated_tokens
            )
            if affordable:
                best = max(affordable, key=lambda m: m.capability_rank)
                return best.id

        # Threshold routing
        if score >= cfg.opus_threshold:
            return "claude-opus-4-6"
        elif score >= cfg.sonnet_threshold:
            return "claude-sonnet-4-6"
        else:
            return "claude-haiku-4-5"

    def build_routing_decision(self, request: TaskRequest) -> tuple[TaskFeatures, RoutingDecision]:
        features = self.extract_features(request)
        score = self.composite_score(features)
        model_id = self.select_model(features)
        model = self._registry.get(model_id)

        # Fallback: one tier down
        fallback_id = self._fallback(model_id)
        fallback = self._registry.get(fallback_id) if fallback_id else None

        from model_router.decomposer import TaskDecomposer
        decomposed = TaskDecomposer(self._registry).should_decompose(features, model)
        subtask_count = 0
        if decomposed:
            subtask_count = TaskDecomposer(self._registry).estimate_subtask_count(features, model)

        reasoning = self._explain(score, features, model_id)

        decision = RoutingDecision(
            selected_model=model_id,
            selected_model_string=model.model_string,
            fallback_model=fallback_id,
            fallback_model_string=fallback.model_string if fallback else None,
            complexity_score=score,
            estimated_tokens=features.estimated_tokens,
            task_type=features.task_type,
            decomposed=decomposed,
            subtask_count=subtask_count,
            reasoning=reasoning,
        )
        return features, decision

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _keyword_score(self, text: str) -> float:
        score = 0.0
        for pattern, weight in _COMPLEXITY_KEYWORDS:
            if re.search(pattern, text):
                score += weight
        return round(min(max(score, 0.0), 1.0), 4)

    def _detect_task_type(self, text: str) -> TaskType:
        counts: dict[TaskType, int] = {}
        for task_type, patterns in _TASK_TYPE_SIGNALS.items():
            counts[task_type] = sum(1 for p in patterns if re.search(p, text))
        best = max(counts, key=lambda t: counts[t])
        return best if counts[best] > 0 else TaskType.CHAT

    @staticmethod
    def _has_multifile(text: str) -> bool:
        # Detect references to multiple file paths
        path_matches = re.findall(r"[\w./\\-]+\.\w{1,5}", text)
        return len(set(path_matches)) >= 2

    @staticmethod
    def _fallback(model_id: str) -> str | None:
        fallbacks = {
            "claude-opus-4-6": "claude-sonnet-4-6",
            "claude-sonnet-4-6": "claude-haiku-4-5",
            "claude-haiku-4-5": None,
        }
        return fallbacks.get(model_id)

    @staticmethod
    def _explain(score: float, features: TaskFeatures, model_id: str) -> str:
        parts = [
            f"Complexity score: {score:.2f}.",
            f"Task type: {features.task_type.value}.",
            f"Estimated tokens: {features.estimated_tokens:,}.",
        ]
        if features.has_architecture:
            parts.append("Architecture/design signals detected.")
        if features.has_multifile:
            parts.append("Multi-file references detected.")
        if features.has_code:
            parts.append("Code content detected.")
        model_names = {
            "claude-opus-4-6": "Opus 4.6 (highest capability)",
            "claude-sonnet-4-6": "Sonnet 4.6 (balanced)",
            "claude-haiku-4-5": "Haiku 4.5 (fast/cheap)",
        }
        parts.append(f"Selected: {model_names.get(model_id, model_id)}.")
        return " ".join(parts)
