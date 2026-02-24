## Configuration & Runtime Guide

All configuration lives in environment variables plus a small `config.toml`. This file collects the essentials so the README can stay short.

---

## Environment variables

| Scope | Variable | Required | Default | Description |
| --- | --- | --- | --- | --- |
| Runtime | `ENV` | No | `dev` | `dev` loads `.env` + reload; `prod` uses `/app/config.toml`; `test` for tests |
| DB | `POSTGRES_USER` | Yes | `postgres` (Docker) | DB user |
| DB | `POSTGRES_PASSWORD` | Yes | `postgres` (Docker) | DB password |
| DB | `POSTGRES_DB` | Yes | `ainews` (Docker) | DB name |
| DB | `POSTGRES_HOST` | Yes | `db` (Docker) | DB host |
| DB | `POSTGRES_PORT` | No | `5432` | DB port |
| LLM | `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `GEMINI_API_KEY` / `MODEL_API_KEY` | One | — | Pick one provider |
| LLM override | `MODEL_NAME`, `MODEL_PROVIDER`, `MODEL_BASE_URL` | No | — | Override model/provider/base_url from `config.toml` |
| Embedding | `EMBEDDING_API_KEY` | No | — | Enable embeddings (vector search/memory) |
| Embedding | `EMBEDDING_BASE_URL` | No | — | Base URL for embedding API |
| Embedding | `EMBEDDING_MODEL` | No | `text-embedding-3-small` | Embedding model |
| Search | `TAVILY_API_KEY` | No | — | Web search enrichment |
| Threads | `THREAD_POOL_MAX_WORKERS` | No | `4` | Worker threads |
| Threads | `THREAD_POOL_NAME_PREFIX` | No | `FlashNews` | Thread name prefix |
| Frontend | `BACKEND_URL`, `BACKEND_HOST` | No | `http://backend:8000`, `backend` | Nginx templating in Docker |
| Frontend (dev) | `VITE_API_BASE_URL` | No | — | SPA -> backend, e.g. `http://localhost:8000/api` |

---

## `config.toml`

Copy the example and adjust:

```bash
cp config.toml.example config.toml
```

What it controls:
- `[model]`: pick model/provider (openai/deepseek/gemini/other) and optional `base_url` for custom providers.
- `[rate_limit]`: request rate and retry behavior for LLM calls.
- `[context]`: context limits, compression strategy, and tool result caps.

API keys are **not** stored in `config.toml`; always use environment variables.

---

## Local development (reference)

```bash
# 1) Start Postgres (Docker)
cd infra/docker && docker compose up -d db

# 2) Backend (uv)
cd ../..
export POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_DB=ainews POSTGRES_HOST=localhost POSTGRES_PORT=5432
export OPENAI_API_KEY=sk-your-openai-api-key
export ENV=dev
uv sync
cp config.toml.example config.toml
uv run python run-backend.py

# 3) Frontend
cd apps/frontend
npm install
echo 'VITE_API_BASE_URL=http://localhost:8000/api' > .env.local
npm run dev
```

---

## Docker Compose sample `.env`

```bash
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=ainews
POSTGRES_HOST=db
POSTGRES_PORT=5432
ENV=prod

# Choose one provider
OPENAI_API_KEY=sk-your-openai-api-key
# DEEPSEEK_API_KEY=your-deepseek-api-key
# GEMINI_API_KEY=your-gemini-api-key
# MODEL_API_KEY=your-custom-api-key

# Optional extras
TAVILY_API_KEY=your-tavily-api-key
EMBEDDING_API_KEY=sk-your-openai-api-key
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
BACKEND_URL=http://backend:8000
BACKEND_HOST=backend
```
