# Configuration

All runtime configuration lives in **`config/models.yaml`**. The file has three top-level sections: `models`, `routing`, and `token_estimation`.

Changes can be applied without restarting the server — click **Reload** in the dashboard Settings page or call `router.reload_config()` programmatically.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | **Yes** | API key used by `claude-agent-sdk` to authenticate with Anthropic |

No other environment variables are used by default. Provider keys for future integrations (e.g. `OPENAI_API_KEY`) would be consumed by the respective provider implementation.

---

## `models` Section

Each entry defines one model available for routing.

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Internal identifier used in routing logic (e.g. `claude-opus-4-6`) |
| `display_name` | `string` | Human-readable name shown in the dashboard |
| `provider` | `string` | Provider key — must match a registered `BaseProvider` (e.g. `claude`) |
| `model_string` | `string` | Exact string passed to the provider SDK |
| `context_tokens` | `integer` | Maximum context window in tokens |
| `cost_input_per_1k` | `float` | USD cost per 1 000 input tokens |
| `cost_output_per_1k` | `float` | USD cost per 1 000 output tokens |
| `capability_rank` | `integer` | 1 (weakest) to 10 (strongest); used for budget-based selection |
| `max_output_tokens` | `integer` | Maximum tokens the model will generate per response |
| `strengths` | `list[string]` | Informational tags shown in the dashboard |

### Built-in models

| ID | Display name | Capability rank | Input $/1k | Output $/1k |
|---|---|---|---|---|
| `claude-opus-4-6` | Claude Opus 4.6 | 10 | $0.015 | $0.075 |
| `claude-sonnet-4-6` | Claude Sonnet 4.6 | 7 | $0.003 | $0.015 |
| `claude-haiku-4-5` | Claude Haiku 4.5 | 3 | $0.00025 | $0.00125 |

---

## `routing` Section

Controls model-selection thresholds and pipeline behaviour.

| Key | Type | Default | Description |
|---|---|---|---|
| `opus_threshold` | `float` | `0.72` | Complexity score ≥ this value routes to Opus |
| `sonnet_threshold` | `float` | `0.38` | Complexity score ≥ this value routes to Sonnet; below routes to Haiku |
| `decompose_threshold` | `float` | `0.75` | Decompose when `estimated_tokens > context_tokens × this value` |
| `compress_threshold` | `int` | `6000` | Compress the prompt when estimated tokens exceed this value |
| `cache_ttl_seconds` | `int` | `300` | In-memory result cache TTL in seconds |

### Routing decision logic

```
score = 0.35×token_score + 0.30×keyword_complexity + 0.20×quality_req
        + 0.10×architecture_signal + 0.05×multifile_signal

if cost_budget set:
    pick highest-capability model whose estimated cost ≤ budget
elif score >= opus_threshold:
    → claude-opus-4-6
elif score >= sonnet_threshold:
    → claude-sonnet-4-6
else:
    → claude-haiku-4-5
```

---

## `token_estimation` Section

Parameters used to estimate token counts from character counts before making an API call.

| Key | Type | Default | Description |
|---|---|---|---|
| `prose_chars_per_token` | `float` | `3.8` | Characters per token for prose/natural-language content |
| `code_chars_per_token` | `float` | `2.5` | Characters per token for code (code is denser) |
| `overhead_factor` | `float` | `1.2` | Multiplier to account for system prompt and response preamble overhead |

---

## Complete `config/models.yaml` Example

```yaml
models:
  - id: claude-opus-4-6
    display_name: "Claude Opus 4.6"
    provider: claude
    model_string: "claude-opus-4-6"
    context_tokens: 200000
    cost_input_per_1k: 0.015
    cost_output_per_1k: 0.075
    capability_rank: 10
    max_output_tokens: 32000
    strengths: [reasoning, architecture, coding, review, complex-analysis]

  - id: claude-sonnet-4-6
    display_name: "Claude Sonnet 4.6"
    provider: claude
    model_string: "claude-sonnet-4-6"
    context_tokens: 200000
    cost_input_per_1k: 0.003
    cost_output_per_1k: 0.015
    capability_rank: 7
    max_output_tokens: 16000
    strengths: [coding, docs, review, chat, summarization]

  - id: claude-haiku-4-5
    display_name: "Claude Haiku 4.5"
    provider: claude
    model_string: "claude-haiku-4-5"
    context_tokens: 200000
    cost_input_per_1k: 0.00025
    cost_output_per_1k: 0.00125
    capability_rank: 3
    max_output_tokens: 8000
    strengths: [chat, summarization, simple-coding, classification]

routing:
  opus_threshold: 0.72
  sonnet_threshold: 0.38
  decompose_threshold: 0.75
  compress_threshold: 6000
  cache_ttl_seconds: 300

token_estimation:
  prose_chars_per_token: 3.8
  code_chars_per_token: 2.5
  overhead_factor: 1.2
```

---

## Adding a New Provider

1. Add one or more model entries to `config/models.yaml` with your provider's name:

   ```yaml
   - id: gpt-4o
     display_name: "GPT-4o"
     provider: openai
     model_string: "gpt-4o"
     context_tokens: 128000
     cost_input_per_1k: 0.005
     cost_output_per_1k: 0.015
     capability_rank: 9
     max_output_tokens: 16384
     strengths: [coding, reasoning, vision]
   ```

2. Create `model_router/providers/openai.py` and subclass `BaseProvider`:

   ```python
   from model_router.providers.base import BaseProvider
   from model_router.models import ExecutionRecord, TaskRequest

   class OpenAIProvider(BaseProvider):
       provider_name = "openai"

       def supports_model(self, model_id: str) -> bool:
           return model_id.startswith("gpt-")

       async def execute(self, request, model_string, fallback_model_string=None):
           # call openai SDK here
           ...
           return result_text, record
   ```

3. Register in `model_router/router.py`:

   ```python
   from model_router.providers.openai import OpenAIProvider

   self._providers["openai"] = OpenAIProvider()
   ```

4. Reload the config (dashboard → Settings → Reload, or `router.reload_config()`).

---

## CLI Options

| Subcommand | Flag | Default | Description |
|---|---|---|---|
| `serve` | `--host` | `127.0.0.1` | Bind address for the dashboard |
| `serve` | `--port` | `8765` | Port for the dashboard |
| `run` / `preview` | `prompt` | *(stdin)* | Prompt text (positional or piped via stdin) |
| `run` / `preview` | `--task-type` | *(auto)* | One of `coding`, `review`, `docs`, `reasoning`, `chat` |
| `run` / `preview` | `--quality` | `0.5` | Quality requirement 0.0–1.0 |
| `run` / `preview` | `--budget` | *(none)* | Hard cost ceiling in USD |
