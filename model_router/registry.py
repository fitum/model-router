"""Model registry -- loads models.yaml and answers routing queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "models.yaml"


@dataclass
class ModelCapabilities:
    id: str
    display_name: str
    provider: str
    model_string: str            # exact string passed to the SDK
    context_tokens: int
    cost_input_per_1k: float
    cost_output_per_1k: float
    capability_rank: int         # 1 (weakest) to 10 (strongest)
    max_output_tokens: int
    strengths: list[str] = field(default_factory=list)


@dataclass
class RoutingConfig:
    opus_threshold: float = 0.72
    sonnet_threshold: float = 0.38
    decompose_threshold: float = 0.75
    compress_threshold: int = 6000
    cache_ttl_seconds: int = 300


@dataclass
class TokenEstimationConfig:
    prose_chars_per_token: float = 3.8
    code_chars_per_token: float = 2.5
    overhead_factor: float = 1.2


class ModelRegistry:
    def __init__(self, config_path: Path = DEFAULT_CONFIG) -> None:
        self._config_path = config_path
        self._models: dict[str, ModelCapabilities] = {}
        self.routing = RoutingConfig()
        self.token_estimation = TokenEstimationConfig()
        self.load()

    def load(self) -> None:
        raw = yaml.safe_load(self._config_path.read_text(encoding="utf-8"))

        self._models = {}
        for m in raw.get("models", []):
            cap = ModelCapabilities(
                id=m["id"],
                display_name=m["display_name"],
                provider=m["provider"],
                model_string=m["model_string"],
                context_tokens=m["context_tokens"],
                cost_input_per_1k=m["cost_input_per_1k"],
                cost_output_per_1k=m["cost_output_per_1k"],
                capability_rank=m["capability_rank"],
                max_output_tokens=m["max_output_tokens"],
                strengths=m.get("strengths", []),
            )
            self._models[cap.id] = cap

        if "routing" in raw:
            r = raw["routing"]
            self.routing = RoutingConfig(
                opus_threshold=r.get("opus_threshold", 0.72),
                sonnet_threshold=r.get("sonnet_threshold", 0.38),
                decompose_threshold=r.get("decompose_threshold", 0.75),
                compress_threshold=r.get("compress_threshold", 6000),
                cache_ttl_seconds=r.get("cache_ttl_seconds", 300),
            )

        if "token_estimation" in raw:
            t = raw["token_estimation"]
            self.token_estimation = TokenEstimationConfig(
                prose_chars_per_token=t.get("prose_chars_per_token", 3.8),
                code_chars_per_token=t.get("code_chars_per_token", 2.5),
                overhead_factor=t.get("overhead_factor", 1.2),
            )

    def reload(self) -> None:
        self.load()

    def get(self, model_id: str) -> ModelCapabilities:
        if model_id not in self._models:
            raise KeyError(f"Unknown model ID '{model_id}'. Available: {list(self._models)}")
        return self._models[model_id]

    def all_models(self) -> list[ModelCapabilities]:
        return sorted(self._models.values(), key=lambda m: m.capability_rank, reverse=True)

    def models_by_provider(self, provider: str) -> list[ModelCapabilities]:
        return [m for m in self._models.values() if m.provider == provider]

    def models_within_budget(
        self, budget_usd: float, estimated_tokens: int
    ) -> list[ModelCapabilities]:
        """Return models whose estimated cost stays under budget."""
        affordable = []
        for m in self._models.values():
            est_cost = self.estimate_cost(m.id, estimated_tokens, estimated_tokens // 2)
            if est_cost <= budget_usd:
                affordable.append(m)
        return affordable

    def estimate_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        m = self.get(model_id)
        return (
            input_tokens / 1000 * m.cost_input_per_1k
            + output_tokens / 1000 * m.cost_output_per_1k
        )

    def to_dict_list(self) -> list[dict]:
        """Serialise all models to plain dicts for the API."""
        result = []
        for m in self.all_models():
            result.append({
                "id": m.id,
                "display_name": m.display_name,
                "provider": m.provider,
                "context_tokens": m.context_tokens,
                "cost_input_per_1k": m.cost_input_per_1k,
                "cost_output_per_1k": m.cost_output_per_1k,
                "capability_rank": m.capability_rank,
                "max_output_tokens": m.max_output_tokens,
                "strengths": m.strengths,
            })
        return result
