# API Reference

This page documents every public class, method, and data structure exported by the `model_router` package.

```python
from model_router import (
    ModelRouter,
    TaskRequest,
    TaskType,
    RoutedResult,
    RoutingDecision,
    TaskFeatures,
    ExecutionRecord,
)
```

---

## `ModelRouter`

**Module:** `model_router.router`

Central orchestrator. Routes any `TaskRequest` to the best model, executes it, tracks usage, and returns a `RoutedResult`.

### Constructor

```python
ModelRouter(
    config_path: Path | None = None,
    tracker: UsageTracker | None = None,
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `config_path` | `Path \| None` | `config/models.yaml` | Path to the YAML configuration file |
| `tracker` | `UsageTracker \| None` | new `UsageTracker()` | Inject a custom tracker (useful for testing) |

### `route_task`

```python
async def route_task(request: TaskRequest) -> RoutingDecision
```

Analyse the request and return a `RoutingDecision` **without** executing any API call. Use this to preview which model would be selected.

```python
decision = await router.route_task(TaskRequest(
    prompt="Design a distributed caching layer",
    quality_requirement=0.8,
))
print(decision.selected_model)   # "claude-opus-4-6"
print(decision.complexity_score) # 0.7821
print(decision.reasoning)        # human-readable explanation
```

### `route_and_run`

```python
async def route_and_run(request: TaskRequest) -> RoutedResult
```

Full pipeline: compress → score → decompose? → execute → track → return.

Returns a `RoutedResult` with the generated content and full cost/token accounting.

```python
result = await router.route_and_run(TaskRequest(
    prompt="Write a Python function to parse ISO 8601 dates",
    task_type=TaskType.CODING,
    quality_requirement=0.5,
    cost_budget_usd=0.01,
))
print(result.result)                 # generated text
print(result.decision.selected_model)
print(f"${result.total_cost_usd:.6f}")
```

> **Alias:** `execute` is an alias for `route_and_run` available in older call sites.

### `reload_config`

```python
def reload_config() -> None
```

Hot-reload `models.yaml` without restarting the process. Picks up changes to model definitions and routing thresholds immediately.

### Properties

| Property | Type | Description |
|---|---|---|
| `session_id` | `str` | UUID identifying the current router session |
| `registry` | `ModelRegistry` | Access to the loaded model configuration |

---

## `TaskRequest`

**Module:** `model_router.models`

Input to `ModelRouter`. All fields except `prompt` are optional.

```python
@dataclass
class TaskRequest:
    prompt: str
    task_type: TaskType | None = None
    quality_requirement: float = 0.5
    cost_budget_usd: float | None = None
    cwd: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    system_prompt: str | None = None
    max_turns: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
```

| Field | Type | Default | Description |
|---|---|---|---|
| `prompt` | `str` | *required* | The task description or user message |
| `task_type` | `TaskType \| None` | `None` | Explicit task type; auto-detected from keywords if omitted |
| `quality_requirement` | `float` | `0.5` | 0.0 = cheapest/fastest, 1.0 = highest quality |
| `cost_budget_usd` | `float \| None` | `None` | Hard cost ceiling in USD; overrides threshold routing |
| `cwd` | `str \| None` | `None` | Working directory passed to `claude-agent-sdk` |
| `allowed_tools` | `list[str]` | `[]` | Tool names permitted for this task (disables caching when non-empty) |
| `system_prompt` | `str \| None` | `None` | Override system prompt for the SDK call |
| `max_turns` | `int \| None` | `None` | Maximum agentic turns; defaults to 30 inside the provider |
| `metadata` | `dict` | `{}` | Arbitrary caller metadata, not used by the router |
| `request_id` | `str` | auto UUID | Unique request identifier |

---

## `TaskType`

**Module:** `model_router.models`

```python
class TaskType(str, Enum):
    CODING    = "coding"
    REVIEW    = "review"
    DOCS      = "docs"
    REASONING = "reasoning"
    CHAT      = "chat"
```

Auto-detection uses keyword pattern matching. Provide an explicit value to override detection.

---

## `RoutedResult`

**Module:** `model_router.models`

Return value from `route_and_run`.

```python
@dataclass
class RoutedResult:
    decision: RoutingDecision
    result: str | None
    records: list[ExecutionRecord]
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    duration_ms: int
    combined: bool = False
```

| Field | Type | Description |
|---|---|---|
| `decision` | `RoutingDecision` | The model-selection decision |
| `result` | `str \| None` | Generated text; `None` on total failure |
| `records` | `list[ExecutionRecord]` | One record per API call (multiple for decomposed tasks) |
| `total_cost_usd` | `float` | Total cost across all subtasks |
| `total_input_tokens` | `int` | Total input tokens consumed |
| `total_output_tokens` | `int` | Total output tokens generated |
| `duration_ms` | `int` | Wall-clock milliseconds from request to return |
| `combined` | `bool` | `True` when subtask results were merged |

---

## `RoutingDecision`

**Module:** `model_router.models`

The scorer's verdict — which model to use and why.

```python
@dataclass
class RoutingDecision:
    selected_model: str
    selected_model_string: str
    fallback_model: str | None
    fallback_model_string: str | None
    complexity_score: float
    estimated_tokens: int
    task_type: TaskType
    decomposed: bool
    subtask_count: int
    reasoning: str
```

| Field | Type | Description |
|---|---|---|
| `selected_model` | `str` | Model ID from `models.yaml` (e.g. `claude-opus-4-6`) |
| `selected_model_string` | `str` | Exact SDK model string |
| `fallback_model` | `str \| None` | One-tier-down fallback model ID |
| `fallback_model_string` | `str \| None` | Fallback SDK string |
| `complexity_score` | `float` | Composite score 0.0–1.0 |
| `estimated_tokens` | `int` | Pre-call token estimate |
| `task_type` | `TaskType` | Detected or supplied task type |
| `decomposed` | `bool` | `True` if the task will be split into subtasks |
| `subtask_count` | `int` | Number of subtasks (0 if not decomposed) |
| `reasoning` | `str` | Human-readable explanation of the decision |

---

## `TaskFeatures`

**Module:** `model_router.models`

Intermediate feature vector produced by `ComplexityScorer.extract_features()`. Useful for debugging or custom scoring.

```python
@dataclass
class TaskFeatures:
    char_count: int
    estimated_tokens: int
    keyword_complexity: float
    task_type: TaskType
    has_code: bool
    has_multifile: bool
    has_architecture: bool
    quality_requirement: float
    cost_budget_usd: float | None
```

---

## `ExecutionRecord`

**Module:** `model_router.models`

One row in `data/usage.db`. Returned inside `RoutedResult.records`.

```python
@dataclass
class ExecutionRecord:
    record_id: str
    session_id: str
    model: str
    task_type: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    timestamp: float
    complexity_score: float
    decomposed: bool
    subtask_index: int   # -1 if not decomposed
    success: bool
    error: str | None
```

---

## `ComplexityScorer`

**Module:** `model_router.scorer`

Analyses a `TaskRequest` and selects a model. Used internally by `ModelRouter` but can be instantiated independently.

```python
scorer = ComplexityScorer(registry)
```

### `extract_features`

```python
def extract_features(request: TaskRequest) -> TaskFeatures
```

Extract the five scoring signals from a request.

### `composite_score`

```python
def composite_score(features: TaskFeatures) -> float
```

Compute the weighted composite complexity score (0.0–1.0).

### `select_model`

```python
def select_model(features: TaskFeatures) -> str
```

Return the model ID best suited to the task, respecting any cost budget.

### `build_routing_decision`

```python
def build_routing_decision(request: TaskRequest) -> tuple[TaskFeatures, RoutingDecision]
```

Convenience method that calls `extract_features`, `composite_score`, `select_model`, and assembles a full `RoutingDecision`.

---

## `TaskDecomposer`

**Module:** `model_router.decomposer`

Splits large tasks into subtasks. Used internally by `ModelRouter`.

### `should_decompose`

```python
def should_decompose(features: TaskFeatures, model: ModelCapabilities) -> bool
```

Returns `True` when estimated tokens exceed `decompose_threshold × context_tokens`.

### `estimate_subtask_count`

```python
def estimate_subtask_count(features: TaskFeatures, model: ModelCapabilities) -> int
```

Returns an integer between 2 and 8.

### `decompose`

```python
def decompose(request: TaskRequest, features: TaskFeatures) -> list[Subtask]
```

Choose a decomposition strategy based on task type and return a list of `Subtask` objects.

### `combine`

```python
def combine(subtask_results: list[str], strategy: str = "sequential") -> str
```

Merge subtask outputs. The `sequential` strategy concatenates results under `## Part N` headers.

---

## `TokenOptimizer`

**Module:** `model_router.optimizer`

Reduces costs through prompt compression and result caching.

### `compress_prompt`

```python
def compress_prompt(prompt: str, target_tokens: int) -> str
```

Apply up to three compression passes to bring the prompt under `target_tokens`. Returns the original string if no compression is needed.

### `trim_context`

```python
def trim_context(
    messages: list[dict],
    max_tokens: int,
    chars_per_token: float = 4.0,
) -> list[dict]
```

Sliding-window trim of a message history list. Always preserves the system message, first user message, and the last three exchanges.

### `build_cache_key`

```python
def build_cache_key(prompt: str, model: str) -> str
```

Return a SHA-256 hex string keyed on the normalised prompt and model name.

### `get_cached` / `set_cached`

```python
def get_cached(key: str) -> str | None
def set_cached(key: str, result: str, ttl_seconds: int | None = None) -> None
```

Read from / write to the in-memory TTL cache.

### `clear_expired`

```python
def clear_expired() -> int
```

Remove all expired entries and return the count of entries removed.

### Properties

| Property | Type | Description |
|---|---|---|
| `cache_size` | `int` | Number of live (non-expired) entries in the cache |

---

## `ModelRegistry`

**Module:** `model_router.registry`

Loads and queries `config/models.yaml`.

### `get`

```python
def get(model_id: str) -> ModelCapabilities
```

Raises `KeyError` if the model ID is not found.

### `all_models`

```python
def all_models() -> list[ModelCapabilities]
```

Return all models sorted by `capability_rank` descending.

### `models_by_provider`

```python
def models_by_provider(provider: str) -> list[ModelCapabilities]
```

### `models_within_budget`

```python
def models_within_budget(budget_usd: float, estimated_tokens: int) -> list[ModelCapabilities]
```

Return models whose estimated cost (input + output/2) stays under `budget_usd`.

### `estimate_cost`

```python
def estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float
```

Return estimated cost in USD.

### `reload`

```python
def reload() -> None
```

Re-read `models.yaml` from disk. Thread-safe for single-process use.

---

## `UsageTracker`

**Module:** `model_router.tracker`

Persists execution records to SQLite and answers analytics queries.

### Constructor

```python
UsageTracker(db_path: Path = Path("data/usage.db"))
```

### `record`

```python
async def record(rec: ExecutionRecord) -> None
```

Write one record. Uses `asyncio.to_thread` so it never blocks the event loop.

### `get_live_totals`

```python
async def get_live_totals() -> dict
```

Returns today's aggregated stats and per-model call counts:

```python
{
    "today_cost_usd": 0.0042,
    "today_tokens": 15200,
    "today_calls": 12,
    "session_cost_usd": 0.0011,
    "session_tokens": 4100,
    "calls_per_model": {
        "claude-sonnet-4-6": {"calls": 8, "cost": 0.0008},
        ...
    }
}
```

### `get_cost_by_model`

```python
async def get_cost_by_model(since_ts: float | None = None) -> list[dict]
```

Aggregate stats grouped by model since the given Unix timestamp (or all time).

### `get_task_history`

```python
async def get_task_history(limit: int = 100, offset: int = 0) -> list[dict]
```

Return paginated raw records ordered by timestamp descending.

### `get_session_stats`

```python
async def get_session_stats() -> dict
```

Return summary stats for the current session only.

---

## `BaseProvider`

**Module:** `model_router.providers.base`

Abstract base class for all AI provider adapters.

```python
class BaseProvider(ABC):
    provider_name: str = ""

    @abstractmethod
    async def execute(
        self,
        request: TaskRequest,
        model_string: str,
        fallback_model_string: str | None = None,
    ) -> tuple[str | None, ExecutionRecord]: ...

    @abstractmethod
    def supports_model(self, model_id: str) -> bool: ...
```

Implement both methods and register your provider in `ModelRouter.__init__`:

```python
self._providers["myprovider"] = MyProvider()
```

---

## REST API

The dashboard server exposes these endpoints on `http://localhost:8765` (default).

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Health check; returns version and uptime |
| `GET` | `/api/stats/live` | SSE stream; emits live totals every 2 seconds |
| `GET` | `/api/stats/session` | Session-scoped aggregate stats |
| `GET` | `/api/stats/cost-by-model` | Cost and call count grouped by model (`?since=<unix_ts>`) |
| `GET` | `/api/history` | Paginated task history (`?limit=&offset=`) |
| `GET` | `/api/models` | List all registered models |
| `POST` | `/api/models/reload` | Hot-reload `config/models.yaml` |
| `POST` | `/api/route` | Preview routing decision for a prompt (no execution) |

### `POST /api/route` — request body

```json
{
  "prompt": "Refactor the auth module to use JWT",
  "task_type": "coding",
  "quality_requirement": 0.7,
  "cost_budget_usd": null
}
```

### `POST /api/route` — response

```json
{
  "selected_model": "claude-sonnet-4-6",
  "selected_model_string": "claude-sonnet-4-6",
  "complexity_score": 0.4812,
  "estimated_tokens": 320,
  "task_type": "coding",
  "decomposed": false,
  "subtask_count": 0,
  "reasoning": "Complexity score: 0.48. Task type: coding. Estimated tokens: 320. Code content detected. Selected: Sonnet 4.6 (balanced)."
}
```
