"""Claude provider -- wraps claude-agent-sdk."""

from __future__ import annotations

import time
import uuid

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query

from model_router.models import ExecutionRecord, TaskRequest
from model_router.providers.base import BaseProvider


class ClaudeProvider(BaseProvider):
    provider_name = "claude"

    def supports_model(self, model_id: str) -> bool:
        return model_id.startswith("claude-")

    async def execute(
        self,
        request: TaskRequest,
        model_string: str,
        fallback_model_string: str | None = None,
    ) -> tuple[str | None, ExecutionRecord]:
        record = ExecutionRecord(
            record_id=str(uuid.uuid4()),
            model=model_string,
            task_type=request.task_type.value if request.task_type else "chat",
        )
        start = time.monotonic()

        try:
            result_text: str | None = None
            input_tokens = 0
            output_tokens = 0

            options = ClaudeAgentOptions(
                cwd=request.cwd,
                allowed_tools=request.allowed_tools or [],
                permission_mode="acceptEdits",
                system_prompt=request.system_prompt,
                max_turns=request.max_turns or 30,
            )
            # model is set via options if the SDK supports it; otherwise it uses
            # the default configured model. For model selection to work the SDK
            # must accept a model kwarg -- we pass it via the options object.
            if hasattr(options, "model"):
                options.model = model_string  # type: ignore[attr-defined]

            async for message in query(prompt=request.prompt, options=options):
                if isinstance(message, ResultMessage):
                    result_text = message.result
                    if message.usage:
                        input_tokens = message.usage.get("input_tokens", 0)
                        output_tokens = message.usage.get("output_tokens", 0)
                elif isinstance(message, AssistantMessage):
                    if message.usage:
                        input_tokens += message.usage.get("input_tokens", 0)
                        output_tokens += message.usage.get("output_tokens", 0)

            record.input_tokens = input_tokens
            record.output_tokens = output_tokens
            record.success = True

        except Exception as exc:  # noqa: BLE001
            record.success = False
            record.error = str(exc)
            result_text = None

        finally:
            record.latency_ms = int((time.monotonic() - start) * 1000)
            record.timestamp = time.time()

        return result_text, record
