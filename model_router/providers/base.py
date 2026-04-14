"""Base provider interface -- implement this to add any AI supplier."""

from __future__ import annotations

from abc import ABC, abstractmethod

from model_router.models import ExecutionRecord, RoutedResult, TaskRequest


class BaseProvider(ABC):
    """
    Thin adapter between ModelRouter and a specific AI SDK.

    To add a new provider (e.g. OpenAI):
    1. Create model_router/providers/openai.py
    2. Subclass BaseProvider, set provider_name = "openai"
    3. Implement execute() and supports_model()
    4. Add "openai" entries to config/models.yaml
    5. Register in ModelRouter.__init__: self._providers["openai"] = OpenAIProvider()
    """

    provider_name: str = ""

    @abstractmethod
    async def execute(
        self,
        request: TaskRequest,
        model_string: str,
        fallback_model_string: str | None = None,
    ) -> tuple[str | None, ExecutionRecord]:
        """
        Execute the request against the provider.
        Returns (result_text, execution_record).
        The execution record should have all token/cost/latency fields populated.
        """
        ...

    @abstractmethod
    def supports_model(self, model_id: str) -> bool:
        """Return True if this provider handles the given model ID from models.yaml."""
        ...
