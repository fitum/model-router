# Usage

This guide covers day-to-day use of Model Router: running tasks from the CLI, embedding it in Python applications, controlling cost and quality, and querying the usage database.

---

## CLI reference

### `preview` — inspect routing without executing

Use `preview` whenever you want to understand *why* a prompt would be sent to a particular model without spending any API credits.

```bash
python main.py preview "<prompt>" [flags]
```

| Flag | Default | Description |
|---|---|---|
| `--task-type` | auto-detected | One of `coding`, `review`, `docs`, `reasoning`, `chat` |
| `--quality` | `0.5` | Quality requirement 0.0–1.0 (higher = more likely to pick Opus) |
| `--budget` | none | Hard USD ceiling (changes model selection logic) |

**Examples:**

```bash
# Auto-detect task type
python main.py preview "Implement a thread-safe LRU cache in Python"

# Override quality to see how it affects model selection
python main.py preview "Write a haiku" --quality 0.1
python main.py preview "Write a haiku" --quality 0.95

# Preview with a budget constraint
python main.py preview "Analyse this codebase for security vulnerabilities" --budget 0.005
```

The output is a JSON object you can pipe to `jq` or parse in scripts:

```bash
python main.py preview "Explain CRDT data structures" | jq .selected_model
```

---

### `run` — execute a routed task

```bash
python main.py run "<prompt>" [flags]
```

Same flags as `preview`. The command prints the model used, token count, cost, latency, and then the full response.

**Inline prompt:**

```bash
python main.py run "List five common HTTP caching headers and their purpose" --quality 0.4
```

**Piped prompt from stdin:**

```bash
echo "Summarise this article:" | cat - article.txt | python main.py run --task-type docs
```

**Task types and when to use them:**

| Task type | Auto-detected when prompt contains… | Best model tier |
|---|---|---|
| `coding` | function, class, implement, refactor, bug, test, async | Sonnet / Opus |
| `review` | review, audit, check, security, performance, improve | Sonnet / Opus |
| `docs` | document, readme, guide, explain, describe, comment | Haiku / Sonnet |
| `reasoning` | analyse, design, architecture, tradeoff, why, evaluate | Opus |
| `chat` | general conversation, simple questions | Haiku |

!!! tip "When to override `--task-type`"
    Auto-detection works well for most prompts. Override it when your prompt is brief and context-free — for example, a short prompt piped from a file that lacks the keywords the scorer looks for.

---

### `serve` — start the monitoring dashboard

```bash
python main.py serve [--host HOST] [--port PORT]
```

| Flag | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address (use `0.0.0.0` to expose on all interfaces) |
| `--port` | `8765` | TCP port |

The dashboard provides:

- **Live stat cards** — Today's cost, token count, call count, session cost (updated via SSE)
- **Model usage chart** — calls and cost breakdown by model
- **Task history** — every recorded call with model, tokens, cost, latency
- **Route Preview** — interactive tool to score any prompt without executing it

<div class="screenshot-placeholder">
  📷 Screenshot: Dashboard with the Task History table open, showing several rows with model, task type, tokens, cost, and latency columns
</div>

---

## Python API patterns

### Basic usage

```python
import anyio
from model_router import ModelRouter, TaskRequest, TaskType

router = ModelRouter()   # reads config/models.yaml automatically

result = anyio.run(
    router.route_and_run,
    TaskRequest(prompt="Explain the actor model of concurrency"),
)

print(result.result)
```

### All `TaskRequest` fields

```python
from model_router import TaskRequest, TaskType

request = TaskRequest(
    # Required
    prompt="Refactor the payment service to use async I/O",

    # Optional — all have sensible defaults
    task_type=TaskType.CODING,      # coding | review | docs | reasoning | chat
                                    # auto-detected from prompt if omitted
    quality_requirement=0.8,        # 0.0 (cheapest) → 1.0 (best); default 0.5
    cost_budget_usd=0.02,           # hard ceiling in USD; None = unlimited
    system_prompt="You are a senior Python engineer.",
    max_turns=3,                    # max agent turns (passed to claude-agent-sdk)
    allowed_tools=["read_file"],    # tools forwarded to the SDK
    cwd="/path/to/project",        # working directory for tool-using agents
    metadata={"user_id": "u123"},   # arbitrary key-value pairs for your records
)
```

### Async usage (FastAPI / Starlette)

```python
from fastapi import FastAPI
from model_router import ModelRouter, TaskRequest

app = FastAPI()
router = ModelRouter()   # create once at startup

@app.post("/ask")
async def ask(body: dict):
    result = await router.route_and_run(TaskRequest(prompt=body["prompt"]))
    return {
        "answer": result.result,
        "model": result.decision.selected_model,
        "cost_usd": result.total_cost_usd,
    }
```

### Preview routing decision in Python

```python
import anyio
from model_router import ModelRouter, TaskRequest

router = ModelRouter()

decision = anyio.run(
    router.route_task,
    TaskRequest(
        prompt="Implement a distributed rate limiter using Redis",
        quality_requirement=0.9,
    ),
)

print(f"Model          : {decision.selected_model}")
print(f"Complexity     : {decision.complexity_score:.4f}")
print(f"Task type      : {decision.task_type}")
print(f"Est. tokens    : {decision.estimated_tokens}")
print(f"Will decompose : {decision.decomposed} ({decision.subtask_count} subtasks)")
print(f"Reasoning      : {decision.reasoning}")
```

### Inspecting `RoutedResult`

```python
result = anyio.run(router.route_and_run, request)

# The generated response
print(result.result)

# Routing metadata
print(result.decision.selected_model)
print(result.decision.complexity_score)
print(result.decision.decomposed)        # True if task was split into subtasks

# Cost and token totals across all subtasks
print(result.total_cost_usd)
print(result.total_input_tokens)
print(result.total_output_tokens)
print(result.duration_ms)

# Individual execution records (one per subtask if decomposed, else one)
for rec in result.records:
    print(rec.model, rec.input_tokens, rec.output_tokens, rec.cost_usd)
```

---

## Controlling cost and quality

### The `quality_requirement` dial

`quality_requirement` (0.0–1.0) feeds directly into the complexity score:

| Value | Practical effect |
|---|---|
| 0.0 – 0.2 | Strongly biases towards Haiku; choose for bulk/cheap tasks |
| 0.3 – 0.6 | Default range; model is chosen primarily by prompt complexity |
| 0.7 – 0.9 | Biases towards Sonnet and Opus |
| 1.0 | Maximum quality signal; Opus will be chosen for almost any prompt |

```bash
# Fast and cheap — simple summary
python main.py run "Summarise this paragraph in one sentence" --quality 0.1

# High-quality — complex architecture question
python main.py run "Design a CQRS + event-sourcing system for an e-commerce platform" --quality 0.95
```

### The `--budget` / `cost_budget_usd` cap

When a budget is set, Model Router **ignores** the complexity thresholds and instead picks the highest-capability model whose *estimated* cost fits within the ceiling.

```bash
# Never spend more than half a cent on this call
python main.py run "Review this SQL query for performance issues" --budget 0.005
```

```python
result = anyio.run(
    router.route_and_run,
    TaskRequest(
        prompt="Analyse this 10 000-line codebase for architectural issues",
        cost_budget_usd=0.05,
    ),
)
```

!!! tip "Budget vs quality"
    Setting both `quality_requirement` and `cost_budget_usd` is valid. The budget wins: routing will not exceed the ceiling even if the quality signal suggests Opus.

---

## Querying usage data

Every executed task is persisted to `data/usage.db` (SQLite). You can query it directly.

### Open the database

```bash
sqlite3 data/usage.db
```

### Useful queries

**Total cost and tokens today:**

```sql
SELECT
    ROUND(SUM(cost_usd), 6)              AS today_cost_usd,
    SUM(input_tokens + output_tokens)    AS today_tokens,
    COUNT(*)                             AS calls
FROM api_calls
WHERE timestamp >= strftime('%s', 'now', 'start of day');
```

**Breakdown by model:**

```sql
SELECT
    model,
    COUNT(*)                          AS calls,
    SUM(input_tokens)                 AS total_input,
    SUM(output_tokens)                AS total_output,
    ROUND(SUM(cost_usd), 6)          AS total_cost_usd,
    ROUND(AVG(latency_ms))           AS avg_latency_ms
FROM api_calls
GROUP BY model
ORDER BY total_cost_usd DESC;
```

**Most expensive calls:**

```sql
SELECT
    datetime(timestamp, 'unixepoch', 'localtime') AS time,
    model,
    task_type,
    input_tokens + output_tokens AS tokens,
    ROUND(cost_usd, 6)           AS cost_usd,
    latency_ms
FROM api_calls
ORDER BY cost_usd DESC
LIMIT 20;
```

**Session summary:**

```sql
SELECT
    session_id,
    COUNT(*)                 AS calls,
    ROUND(SUM(cost_usd), 6) AS session_cost,
    MIN(datetime(timestamp, 'unixepoch', 'localtime')) AS started
FROM api_calls
GROUP BY session_id
ORDER BY started DESC
LIMIT 10;
```

### Programmatic access

Use `UsageTracker` for async access in Python:

```python
import anyio
from model_router.tracker import UsageTracker

tracker = UsageTracker()

# Today's totals
totals = anyio.run(tracker.get_live_totals)
print(totals["today_cost_usd"])
print(totals["calls_per_model"])

# Full cost breakdown by model
breakdown = anyio.run(tracker.get_cost_by_model)
for row in breakdown:
    print(row["model"], row["calls"], row["cost"])

# Recent task history
history = anyio.run(tracker.get_task_history, 50)   # last 50 calls
for row in history:
    print(row["model"], row["task_type"], row["cost_usd"])
```

---

## Hot-reloading configuration

You can change routing thresholds and add models while the server is running.

**From the dashboard:**

1. Edit `config/models.yaml`
2. Open [http://localhost:8765](http://localhost:8765)
3. Navigate to **Settings → Reload**

**From Python:**

```python
router.reload_config()
print("Config reloaded — new thresholds are active immediately")
```

**From the CLI (one-liner):**

```bash
python - <<'EOF'
import anyio
from model_router.router import ModelRouter
r = ModelRouter()
r.reload_config()
print("Reloaded")
EOF
```

---

## Result caching

Model Router keeps an in-memory SHA-256-keyed cache of recent results. If you send the same prompt with the same task type within the TTL window (`cache_ttl_seconds`, default 300 s), the cached result is returned immediately at zero cost.

```python
import anyio, time
from model_router import ModelRouter, TaskRequest

router = ModelRouter()
req = TaskRequest(prompt="What is a monad?")

# First call hits the API
r1 = anyio.run(router.route_and_run, req)
print(f"Cost: ${r1.total_cost_usd:.6f}, time: {r1.duration_ms}ms")

# Second call is served from cache (cost = $0.000000)
r2 = anyio.run(router.route_and_run, req)
print(f"Cost: ${r2.total_cost_usd:.6f}, time: {r2.duration_ms}ms")
```

!!! tip "Disabling the cache"
    Set `cache_ttl_seconds: 0` in `config/models.yaml` to disable caching entirely, then call `router.reload_config()`.

---

## See also

- [Configuration](../configuration.md) — full `models.yaml` reference, adding providers
- [Getting Started](getting-started.md) — installation and first run
- [Troubleshooting](troubleshooting.md) — common errors and fixes
- [API Reference](../api/index.md) — complete class and method documentation
