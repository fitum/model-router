# Troubleshooting

This page lists the most common problems encountered when installing or using Model Router, along with step-by-step fixes.

---

## Installation problems

### `ModuleNotFoundError: No module named 'model_router'`

**Cause:** Python cannot find the project package — most often because the virtual environment is not activated, or `pip install` was run in the wrong environment.

**Fix:**

1. Make sure you are in the project root (the directory that contains `main.py`):

    ```bash
    ls main.py          # should print "main.py"
    ```

2. Activate the virtual environment:

    === "macOS / Linux"
        ```bash
        source .venv/bin/activate
        ```

    === "Windows"
        ```bat
        .venv\Scripts\activate
        ```

3. Re-run the install:

    ```bash
    pip install -r requirements.txt
    ```

4. Run from the project root (not from inside `model_router/`):

    ```bash
    python main.py --help
    ```

---

### `pip install` fails with dependency errors

**Cause:** An outdated pip or a conflicting package version.

**Fix:**

1. Upgrade pip first:

    ```bash
    python -m pip install --upgrade pip
    ```

2. Retry the install:

    ```bash
    pip install -r requirements.txt
    ```

If a specific package still fails, install it individually to see the full error:

```bash
pip install claude-agent-sdk
pip install "pydantic>=2.0"
```

---

### Python version is older than 3.11

**Symptom:** Syntax errors on startup, or pip rejects the package.

**Fix:** Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/) and create a fresh virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate    # macOS / Linux
pip install -r requirements.txt
```

!!! tip "Managing multiple Python versions"
    Tools like [pyenv](https://github.com/pyenv/pyenv) (macOS/Linux) or [py launcher](https://docs.python.org/3/using/windows.html#python-launcher-for-windows) (Windows) make it easy to switch between Python versions without affecting your system installation.

---

## API key problems

### `AuthenticationError` / `401 Unauthorized`

**Cause:** `ANTHROPIC_API_KEY` is not set, is set incorrectly, or the key has been revoked.

**Fix:**

1. Verify the variable is exported in the current shell:

    === "macOS / Linux"
        ```bash
        echo $ANTHROPIC_API_KEY
        ```

    === "Windows (PowerShell)"
        ```powershell
        echo $env:ANTHROPIC_API_KEY
        ```

    The output should start with `sk-ant-`. If it is blank, set it:

    ```bash
    export ANTHROPIC_API_KEY="sk-ant-..."
    ```

2. Check that your key is active in the [Anthropic Console](https://console.anthropic.com).

3. If you set the key in a new terminal tab, re-activate the virtual environment — environment variables are not inherited across some shell configurations.

---

### Key is set but still getting auth errors

**Cause:** The key may have leading/trailing spaces, or a shell alias is overriding `python`.

**Fix:**

```bash
# Unset and re-set to remove accidental whitespace
unset ANTHROPIC_API_KEY
export ANTHROPIC_API_KEY="sk-ant-..."

# Confirm the key value looks right
python -c "import os; k = os.getenv('ANTHROPIC_API_KEY',''); print(repr(k[:15]))"
```

---

## Routing and execution problems

### Every prompt routes to Opus regardless of content

**Cause:** `quality_requirement` defaults to `0.5`; prompts with architecture or code keywords score high enough to hit the `opus_threshold` (0.72). Or the threshold has been lowered in `config/models.yaml`.

**Fix — lower the quality requirement for simple tasks:**

```bash
python main.py run "What year was Python created?" --quality 0.1
```

**Fix — raise the Opus threshold so fewer tasks reach it:**

```yaml
# config/models.yaml
routing:
  opus_threshold: 0.82    # was 0.72
```

Then reload: `router.reload_config()` or dashboard → Settings → Reload.

---

### Task is unexpectedly decomposed into subtasks

**Cause:** The estimated token count exceeds `decompose_threshold × context_window`. This happens with very long prompts.

**Fix:**

- Shorten the prompt.
- Or raise `decompose_threshold` in `config/models.yaml` (max 1.0 disables decomposition):

    ```yaml
    routing:
      decompose_threshold: 1.0    # never decompose
    ```

---

### `ValueError: No provider registered for '...'`

**Cause:** A model entry in `config/models.yaml` references a provider key (e.g. `openai`) that has not been registered in `model_router/router.py`.

**Fix:**

1. Check your `models.yaml` for any model with an unrecognised `provider:` field.
2. Either remove or comment out that model entry, or follow the [Adding a Provider](../configuration.md#adding-a-new-provider) instructions to implement and register the provider.

---

### `result.result` is `None`

**Cause:** The provider's `execute()` call returned no content — most often due to an API error that was silently caught, or a `max_turns` limit that was reached before any output was produced.

**Fix:**

1. Check `result.records` for any record where `success == False` or `error` is set:

    ```python
    for rec in result.records:
        if not rec.success:
            print(rec.error)
    ```

2. Increase `max_turns` in `TaskRequest` if you are using tool-using agents.
3. Retry with a shorter prompt (token limits may be exceeded for very large inputs).

---

## Dashboard problems

### Dashboard won't start: `Address already in use`

**Cause:** Port 8765 is already taken — either by another Model Router instance or another application.

**Fix:**

```bash
# Use a different port
python main.py serve --port 9001
```

Or find and kill the process using port 8765:

=== "macOS / Linux"
    ```bash
    lsof -ti:8765 | xargs kill
    ```

=== "Windows (PowerShell)"
    ```powershell
    Get-Process -Id (Get-NetTCPConnection -LocalPort 8765).OwningProcess | Stop-Process
    ```

---

### Dashboard loads but shows no data

**Cause:** The dashboard was opened in the browser *before* any `run` commands were executed in the same or a previous session.

**Fix:** Run at least one task and refresh the dashboard:

```bash
python main.py run "Hello" --quality 0.1
```

If data still does not appear, check that `data/usage.db` exists and is not empty:

```bash
sqlite3 data/usage.db "SELECT COUNT(*) FROM api_calls;"
```

---

### SSE live stats are not updating

**Cause:** The browser or a proxy is buffering the server-sent events stream.

**Fix:**

1. Try opening the dashboard in a different browser.
2. If you are behind a reverse proxy (nginx, Caddy), add these headers:

    ```nginx
    proxy_set_header Cache-Control no-cache;
    proxy_buffering off;
    proxy_read_timeout 86400s;
    ```

---

## Configuration problems

### Config changes are not taking effect

**Cause:** `models.yaml` was edited but the reload was not triggered.

**Fix — programmatic:**

```python
router.reload_config()
```

**Fix — dashboard:**

Navigate to **Settings → Reload** and confirm the success message.

**Fix — restart:**

Stop the server (`Ctrl+C`) and start it again:

```bash
python main.py serve
```

---

### `yaml.scanner.ScannerError` on startup

**Cause:** Invalid YAML syntax in `config/models.yaml` — typically a missing colon, wrong indentation, or an unquoted special character.

**Fix:**

1. Validate the file with a YAML linter:

    ```bash
    python -c "import yaml; yaml.safe_load(open('config/models.yaml'))"
    ```

2. Fix the reported line.

3. Common pitfalls in YAML:

    ```yaml
    # Wrong — unquoted colon in value
    display_name: Claude: Opus 4.6

    # Right
    display_name: "Claude: Opus 4.6"
    ```

---

## Performance and cost problems

### Costs are higher than expected

**Tip 1 — lower the default quality:**

```bash
python main.py run "..." --quality 0.3
```

**Tip 2 — set a hard budget ceiling:**

```bash
python main.py run "..." --budget 0.005
```

**Tip 3 — enable prompt compression** by lowering `compress_threshold`:

```yaml
routing:
  compress_threshold: 2000   # compress any prompt over ~2 000 tokens
```

**Tip 4 — check the cache TTL.** If similar prompts are repeated within 5 minutes they should be served from cache at zero cost. Verify `cache_ttl_seconds` is not set to `0`.

---

### Response latency is very high

**Cause:** Large prompts, many subtasks, or slow network.

**Tips:**

- Use `--quality 0.1` to route to Haiku, which is 3–5× faster than Opus.
- Check `decision.decomposed` — decomposed tasks run subtasks sequentially. If decomposition is not needed, raise `decompose_threshold` to prevent it.
- Use `preview` first to estimate token count and confirm you are not accidentally sending a huge prompt.

---

## Still stuck?

1. Run `python main.py --help` to confirm the CLI is installed correctly.
2. Check `data/usage.db` for failed records:

    ```sql
    SELECT * FROM api_calls WHERE success = 0 ORDER BY timestamp DESC LIMIT 10;
    ```

3. Review the [Configuration reference](../configuration.md) to confirm `models.yaml` is valid.
4. Open an issue and include the output of:

    ```bash
    python main.py preview "test"
    python --version
    pip show claude-agent-sdk pydantic starlette
    ```
