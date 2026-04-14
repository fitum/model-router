# Getting Started

By the end of this guide you will have Model Router installed, configured, and running your first routed task — both from the command line and from Python code. The whole process takes about five minutes.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | **≥ 3.11** | Check with `python --version` |
| pip | latest recommended | Comes with Python |
| Anthropic API key | — | [Create one at console.anthropic.com](https://console.anthropic.com) |

!!! tip "Use a virtual environment"
    Model Router installs several dependencies. A virtual environment keeps them isolated from your system Python.

---

## 1 — Clone and install

1. Clone the repository and enter the project directory:

    ```bash
    git clone <repo-url>
    cd model-router
    ```

2. *(Recommended)* Create and activate a virtual environment:

    === "macOS / Linux"
        ```bash
        python -m venv .venv
        source .venv/bin/activate
        ```

    === "Windows"
        ```bat
        python -m venv .venv
        .venv\Scripts\activate
        ```

3. Install all dependencies from the lock file:

    ```bash
    pip install -r requirements.txt
    ```

    **Expected outcome** — pip installs `claude-agent-sdk`, `pydantic`, `PyYAML`, `starlette`, `uvicorn`, `sse-starlette`, `httpx`, and `anyio` without errors.

4. Verify the CLI is available:

    ```bash
    python main.py --help
    ```

    You should see the `serve`, `run`, and `preview` subcommands listed.

---

## 2 — Set your API key

Model Router calls the Claude API through the `claude-agent-sdk`. The SDK reads the key from an environment variable.

=== "macOS / Linux"
    ```bash
    export ANTHROPIC_API_KEY="sk-ant-..."
    ```
    Add this line to your `~/.zshrc` or `~/.bashrc` to make it permanent.

=== "Windows (PowerShell)"
    ```powershell
    $env:ANTHROPIC_API_KEY = "sk-ant-..."
    ```

=== "Windows (Command Prompt)"
    ```bat
    set ANTHROPIC_API_KEY=sk-ant-...
    ```

!!! warning "Keep your key secret"
    Never commit your API key to version control. If you use a `.env` file, add it to `.gitignore`.

---

## 3 — Preview your first routing decision

The `preview` subcommand scores a prompt and shows which model would be chosen — **without making an API call or spending any money**. It is the fastest way to understand how the router thinks.

```bash
python main.py preview "Refactor this microservice to use async database queries"
```

**Expected output:**

```json
{
  "selected_model": "claude-opus-4-6",
  "selected_model_string": "claude-opus-4-6",
  "complexity_score": 0.7821,
  "task_type": "coding",
  "estimated_tokens": 840,
  "decomposed": false,
  "subtask_count": 0,
  "reasoning": "Complexity score: 0.78. Task type: coding. Estimated tokens: 840. Architecture/design signals detected. Code content detected. Selected: Opus 4.6 (highest capability)."
}
```

The five-signal scoring formula is:

```
score = 0.35 × token_score
      + 0.30 × keyword_complexity
      + 0.20 × quality_requirement
      + 0.10 × architecture_signal
      + 0.05 × multifile_signal
```

| Score range | Model selected |
|---|---|
| ≥ 0.72 | Claude Opus 4.6 — highest capability |
| 0.38 – 0.72 | Claude Sonnet 4.6 — balanced speed and quality |
| < 0.38 | Claude Haiku 4.5 — fastest and cheapest |

Try a simpler prompt and notice the model changes:

```bash
python main.py preview "What is the capital of France?"
```

---

## 4 — Run your first task

The `run` subcommand executes the routed task and prints the result.

```bash
python main.py run "Explain the difference between TCP and UDP in one paragraph" --quality 0.3
```

**Expected output:**

```
Model  : claude-haiku-4-5
Tokens : 312
Cost   : $0.00008
Latency: 843ms

TCP (Transmission Control Protocol) guarantees delivery by establishing a
connection, ordering packets, and retransmitting lost data — at the cost of
extra overhead. UDP (User Datagram Protocol) sends packets without a
handshake, making it faster but unreliable, which suits real-time applications
like video calls or gaming where occasional packet loss is acceptable.
```

Every call is automatically recorded to `data/usage.db` (SQLite). You can query it at any time without touching the running server.

### Useful flags

| Flag | Description | Example |
|---|---|---|
| `--quality 0.0–1.0` | 0 = cheapest/fastest, 1 = best quality | `--quality 0.9` |
| `--task-type` | Skip auto-detection | `--task-type coding` |
| `--budget` | Hard USD ceiling; selects the best model that fits | `--budget 0.01` |

**Force a specific task type:**

```bash
python main.py run --task-type coding \
  "Write a Python dataclass for a paginated API response"
```

**Cap spend at one cent:**

```bash
python main.py run --budget 0.01 \
  "Summarise the main ideas of the CAP theorem"
```

**Pipe a long prompt from a file:**

```bash
cat my_prompt.txt | python main.py run --task-type review
```

---

## 5 — Use the Python API

Import `ModelRouter` directly when you want to embed routing in your own application.

```python
import anyio
from model_router import ModelRouter, TaskRequest, TaskType

# Instantiate once; reuse across requests
router = ModelRouter()

result = anyio.run(
    router.route_and_run,
    TaskRequest(
        prompt="Write unit tests for a binary search implementation",
        task_type=TaskType.CODING,   # optional — auto-detected if omitted
        quality_requirement=0.6,     # 0.0 (cheap) → 1.0 (best)
    ),
)

print(result.result)                                          # generated text
print(f"Model  : {result.decision.selected_model}")          # e.g. claude-sonnet-4-6
print(f"Tokens : {result.total_input_tokens + result.total_output_tokens}")
print(f"Cost   : ${result.total_cost_usd:.6f}")
print(f"Time   : {result.duration_ms}ms")
```

**Preview without executing (Python):**

```python
import anyio
from model_router import ModelRouter, TaskRequest

router = ModelRouter()
decision = anyio.run(
    router.route_task,
    TaskRequest(prompt="Design a distributed event-sourcing system"),
)

print(decision.selected_model)    # e.g. claude-opus-4-6
print(decision.complexity_score)  # e.g. 0.85
print(decision.reasoning)
```

!!! tip "Inside an async application"
    If you are already in an `async` context (FastAPI, Starlette, etc.), call `await router.route_and_run(request)` directly — no need for `anyio.run()`.

---

## 6 — Launch the live dashboard

The dashboard gives you real-time cost and usage data, plus an interactive Route Preview tool.

```bash
python main.py serve
```

Open [http://localhost:8765](http://localhost:8765) in your browser.

<div class="screenshot-placeholder">
  📷 Screenshot: Dashboard homepage showing stat cards (Today's Cost, Tokens, Calls, Session Cost) and a model usage bar chart
</div>

**Custom host and port:**

```bash
python main.py serve --host 0.0.0.0 --port 9000
```

!!! warning "Remote access"
    Binding to `0.0.0.0` exposes the dashboard on all network interfaces. Only do this on trusted networks or behind a reverse proxy.

### Route Preview tool

Navigate to **Tools → Route Preview** in the sidebar. Paste any prompt, adjust the quality slider, and click **Analyse Task** to see the routing decision and full reasoning — no API call is made.

<div class="screenshot-placeholder">
  📷 Screenshot: Route Preview page with a prompt entered in the left panel and the routing decision JSON displayed in the right panel
</div>

---

## 7 — Understand the default configuration

All routing thresholds live in **`config/models.yaml`**. No changes are needed to get started, but it is worth knowing what the defaults are:

```yaml
routing:
  opus_threshold: 0.72      # complexity >= this -> Opus
  sonnet_threshold: 0.38    # complexity >= this -> Sonnet, else Haiku
  compress_threshold: 6000  # compress prompt when estimated tokens exceed this
  cache_ttl_seconds: 300    # in-memory result cache TTL (5 minutes)
```

Changes to `models.yaml` take effect immediately without restarting the server — click **Settings → Reload** in the dashboard or call `router.reload_config()` in Python.

---

## Next steps

| Guide | What you will learn |
|---|---|
| [Usage](usage.md) | All CLI flags, Python API patterns, querying usage data, hot-reloading config |
| [Configuration](../configuration.md) | Every option in `models.yaml`, routing thresholds, token estimation, adding providers |
| [Troubleshooting](troubleshooting.md) | Common errors and how to fix them |
| [Architecture](../architecture.md) | How the scoring, decomposition, and caching pipeline works internally |
| [API Reference](../api/index.md) | Every public class, method, and data structure |
