# Configuration Guide

Distill uses environment variables and a `config.toml` file for configuration.

---

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |
| `POSTGRES_DB` | Database name |
| `POSTGRES_HOST` | Database host |
| `POSTGRES_PORT` | Database port (default: `5432`) |
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `GEMINI_API_KEY` / `MODEL_API_KEY` | LLM provider API key (at least one required) |

### Optional

| Variable | Description |
|----------|-------------|
| `ENV` | Runtime mode: `dev` (loads `.env`, enables reload), `prod` (uses `/app/config.toml`), `test`. Default: `dev` |
| `EMBEDDING_API_KEY` | API key for embedding service (required when using `[embedding]` section) |
| `TAVILY_API_KEY` | API key for Tavily web search (enables agent web search) |
| `THREAD_POOL_MAX_WORKERS` | Maximum worker threads (default: `4`) |
| `THREAD_POOL_NAME_PREFIX` | Thread name prefix (default: `Distill`) |
| `BACKEND_URL` | Backend URL for Nginx templating (default: `http://backend:8000`) |
| `BACKEND_HOST` | Backend host for Nginx templating (default: `backend`) |
| `VITE_API_BASE_URL` | SPA to backend URL for dev mode (e.g., `http://localhost:8000/api`) |
| `LOG_LEVEL` | Logging level (default: `INFO`, or `DEBUG` in dev mode) |

---

## config.toml

Copy the example to get started:

```bash
cp config.toml.example config.toml
```

**Important:** API keys are **not** stored in `config.toml`. Always use environment variables for API keys.

### `[model]` (Required)

```toml
[model]
model = "gpt-4o"           # Model name
provider = "openai"         # Provider: openai, deepseek, gemini, other
# base_url = "..."          # Only required for provider="other"
```

**Auto-determined Base URLs:**
- `openai`: `https://api.openai.com/v1`
- `deepseek`: `https://api.deepseek.com`
- `gemini`: Uses Google SDK (no base URL)
- `other`: Must provide `base_url`

### `[lightweight_model]` (Optional)

Lightweight model for auxiliary tasks (e.g., batch audit). Uses `MODEL_API_KEY` when provider is `other`.

```toml
[lightweight_model]
model = "gemini-2.5-flash-lite"
provider = "other"
base_url = "https://your-custom-api.com/v1"
```

### `[embedding]` (Optional)

Enables semantic search and memory. Requires `EMBEDDING_API_KEY` environment variable.

```toml
[embedding]
model = "text-embedding-3-small"
provider = "other"
base_url = "https://api.openai.com/v1"
```

### `[rate_limit]` (Optional)

Controls LLM API rate limiting and retry behavior.

```toml
[rate_limit]
# Rate limiting
requests_per_minute = 60.0   # Default: 60
burst_size = 10               # Default: 10
enable_rate_limit = true      # Default: true

# Retry settings
max_retries = 3               # Default: 3
base_delay = 1.0              # Default: 1.0 (seconds)
max_delay = 60.0              # Default: 60.0 (seconds)
enable_retry = true           # Default: true
```

### `[context]` (Optional)

Controls context window management.

```toml
[context]
max_tokens = 128000                  # Default: 128000
compress_threshold = 0.8             # Default: 0.8
```

### `[agent_limits]` (Optional)

Controls Plan-Solve Agent circuit breakers to prevent runaway loops.

```toml
[agent_limits]
# Research phase limits
max_iterations = 10          # Default: 10 - Max research loop iterations
max_tool_calls = 50          # Default: 50 - Max total tool calls
max_curations = 8            # Default: 8 - Max curation cycles

# Review phase limits
max_plan_reviews = 3         # Default: 3 - Max plan review cycles

# Writing phase limits
max_refines = 3              # Default: 3 - Max draft refinement cycles

# Layer 1 control
enable_hard_limits = true    # Default: true - Enable state-level hard limits
```
