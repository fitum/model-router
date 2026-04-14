# model-router

**Intelligent AI model routing, orchestration, and cost tracking for Claude.**

Model Router sits between your code and the Claude API. It scores every task's complexity, automatically selects the most cost-effective model (Opus / Sonnet / Haiku), splits oversized tasks into type-aware subtasks, compresses prompts to reduce token spend, and records every call to a local SQLite database. A live web dashboard gives you real-time visibility into cost, latency, and model usage.

---

## Features

| Capability | Details |
|---|---|
| Automatic model selection | Five-signal weighted scoring picks Opus, Sonnet, or Haiku |
| Cost-budget routing | Hard USD ceiling overrides threshold routing |
| Task decomposition | Splits coding/review/docs/reasoning tasks into parallel subtasks |
| Prompt optimisation | Three-pass compression (whitespace → boilerplate → truncation) |
| In-memory caching | SHA-256-keyed TTL cache avoids duplicate API calls |
| Usage tracking | Every call persisted to `data/usage.db` (SQLite) |
| Live dashboard | Starlette + SSE web UI at `http://localhost:8765` |
| Provider-agnostic | Add any provider in one file by subclassing `BaseProvider` |

---

## Quick Start

```bash
# Install
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."

# Preview routing (no API call)
python main.py preview "Refactor the auth service to use async PostgreSQL"

# Execute a task
python main.py run "Write a Python binary search function" --quality 0.6

# Launch dashboard
python main.py serve          # → http://localhost:8765
```

### Python API

```python
import anyio
from model_router import ModelRouter, TaskRequest, TaskType

router = ModelRouter()

result = anyio.run(router.route_and_run, TaskRequest(
    prompt="Implement a Redis-backed rate limiter",
    task_type=TaskType.CODING,
    quality_requirement=0.8,
))

print(result.result)
print(f"Model : {result.decision.selected_model}")
print(f"Cost  : ${result.total_cost_usd:.6f}")
```

---

## Project Structure

```
model-router/
├── config/
│   └── models.yaml          # Model definitions + routing thresholds
├── data/
│   └── usage.db             # SQLite usage log (auto-created)
├── model_router/
│   ├── __init__.py          # Public API exports
│   ├── models.py            # Core dataclasses (TaskRequest, RoutedResult, …)
│   ├── router.py            # ModelRouter — main orchestrator
│   ├── scorer.py            # ComplexityScorer — model selection logic
│   ├── decomposer.py        # TaskDecomposer — large-task splitting
│   ├── optimizer.py         # TokenOptimizer — compression + caching
│   ├── registry.py          # ModelRegistry — config loader
│   ├── tracker.py           # UsageTracker — SQLite telemetry
│   └── providers/
│       ├── base.py          # BaseProvider — interface for AI providers
│       └── claude.py        # ClaudeProvider — claude-agent-sdk adapter
├── server/
│   ├── app.py               # Starlette app factory
│   ├── routes.py            # REST + SSE API endpoints
│   └── static/              # Dashboard HTML/CSS/JS
├── main.py                  # CLI entry point
├── requirements.txt
└── mkdocs.yml
```

---

## Configuration

Edit **`config/models.yaml`** to tune routing thresholds, add models, or adjust token estimation:

```yaml
routing:
  opus_threshold: 0.72      # complexity ≥ this → Opus
  sonnet_threshold: 0.38    # complexity ≥ this → Sonnet, else Haiku
  compress_threshold: 6000  # compress prompt when estimated tokens exceed this
  cache_ttl_seconds: 300    # in-memory result cache TTL
```

Hot-reload without restart:

```bash
# Dashboard → Settings → Reload
# or programmatically:
router.reload_config()
```

Full configuration reference → [docs/configuration.md](docs/configuration.md)

---

## Adding a Provider

1. Add entries to `config/models.yaml` with `provider: yourprovider`
2. Create `model_router/providers/yourprovider.py`, subclass `BaseProvider`, implement `execute()` and `supports_model()`
3. Register: `self._providers["yourprovider"] = YourProvider()` in `router.py`
4. Reload config

---

## Documentation

Full documentation lives in the `docs/` folder and is built with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/).

```bash
pip install mkdocs-material
mkdocs serve        # live preview at http://127.0.0.1:8000
mkdocs build        # build static site to site/
```

| Doc page | Description |
|---|---|
| [docs/index.md](docs/index.md) | Overview and quick start |
| [docs/architecture.md](docs/architecture.md) | Component diagram and data flow |
| [docs/configuration.md](docs/configuration.md) | All config options and CLI flags |
| [docs/api/index.md](docs/api/index.md) | Full API reference |
| [docs/guides/getting-started.md](docs/guides/getting-started.md) | Step-by-step tutorial |

---

## Requirements

- Python ≥ 3.11
- `ANTHROPIC_API_KEY` environment variable
- Dependencies: `claude-agent-sdk`, `pydantic≥2`, `PyYAML≥6`, `starlette`, `uvicorn`, `sse-starlette`, `httpx`, `anyio`
