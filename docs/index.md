# Model Router

**Model Router** is an intelligent AI model orchestration layer for Claude. It analyses every incoming task, scores its complexity, and automatically routes it to the most cost-effective Claude model — Opus, Sonnet, or Haiku — while tracking token usage and cost in real time.

<div class="screenshot-placeholder">
  📷 Screenshot: Model Router dashboard showing live cost stats, model usage chart, and sidebar navigation
</div>

## Key Features

- **Automatic complexity scoring** — five-signal weighted formula picks the right model every time
- **Task decomposition** — oversized tasks are split into type-aware subtasks (coding by file, reviews by concern, docs by section) and merged into a single coherent result
- **Prompt optimization** — three-pass compression (whitespace → boilerplate stripping → middle-truncation) keeps token counts and costs low
- **In-memory result cache** — configurable TTL avoids redundant API calls for repeated prompts
- **Persistent usage tracking** — every call is recorded to SQLite; query totals by model, session, or time window
- **Live dashboard** — Starlette + SSE web UI for real-time cost monitoring, task history, and route previews
- **Provider-agnostic design** — add OpenAI, Gemini, or any other provider with a single file
- **CLI & Python API** — use from the terminal or embed in any Python application

## Prerequisites

| Requirement | Version |
|---|---|
| Python | ≥ 3.11 |
| `claude-agent-sdk` | latest |
| `pydantic` | ≥ 2.0 |
| `PyYAML` | ≥ 6.0 |
| `starlette` + `uvicorn` | latest |
| `sse-starlette` | latest |
| `httpx` | latest |
| `anyio` | latest |

An **Anthropic API key** must be available to the `claude-agent-sdk` (typically via `ANTHROPIC_API_KEY`).

## Quick Start

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd model-router

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."

# 4. Preview how a prompt would be routed (no API call)
python main.py preview "Refactor this microservice to use async database queries"

# 5. Start the live dashboard
python main.py serve
# → open http://localhost:8765
```

### Python API quick start

```python
import anyio
from model_router import ModelRouter, TaskRequest, TaskType

router = ModelRouter()

result = anyio.run(router.route_and_run, TaskRequest(
    prompt="Implement a binary search function in Python",
    task_type=TaskType.CODING,
    quality_requirement=0.7,
))

print(result.result)
print(f"Model : {result.decision.selected_model}")
print(f"Tokens: {result.total_input_tokens + result.total_output_tokens}")
print(f"Cost  : ${result.total_cost_usd:.6f}")
```

## Further Reading

- [Architecture](architecture.md) — system components, data flow, and design decisions
- [Configuration](configuration.md) — all config options, routing thresholds, and environment variables
- [API Reference](api/index.md) — every public class, method, and data structure
- [Guides](guides/getting-started.md) — step-by-step tutorials
