# CLAUDE.md

Behavioral guidelines and project documentation for the Distill codebase. Read this before making changes.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

---

## Project Overview

Distill (repository directory: `Distill`, package name: `distill`) is an AI-powered news briefing system. It aggregates RSS feeds, uses LLMs to generate concise topic-grouped summaries, and provides intelligent news curation via legacy and Plan-Solve agent workflows.

**Architecture:**
```
RSS/OPML → Crawler → PostgreSQL (pgvector)
                    → Agent (LLM + tools + embeddings)

Frontend (React/Vite) ↔ Backend API (FastAPI) ↔ External LLM APIs
```

## Tech Stack

**Backend:** FastAPI, PostgreSQL + pgvector, Python 3.10+, LangGraph, APScheduler

**Frontend:** React 18.3 + TypeScript, Vite, TailwindCSS, TanStack Query, React Router, Headless UI, lucide-react, i18next/react-i18next (en/zh)

**AI/ML:** OpenAI / DeepSeek / Gemini APIs, Tavily (web search), pgvector (embeddings)

## Repository Structure

```
apps/
  backend/          FastAPI service
    main.py           Entry point (lifespan, CORS, middleware)
    router/           API endpoints: brief, feed, group, schedule, memory, setting
    services/         Business logic: brief_service, feed_service, group_service, ...
    models/           Pydantic request/response models
    config/           Thread pool setup
    middleware.py     Request logging
    exception.py      Custom exception handlers
    crons.py          Cron job definitions
  frontend/         React SPA
    src/pages/        SummaryPage, SourcesPage, GroupsPage, SchedulesPage,
                      SettingsPage, SettingsAdvancedPage, MemoryPage, InstantLabPage
    src/components/   Layout, Modal, DateFilter, ConfirmDialog, ToastContainer, ui/
    src/context/      ThemeContext, ToastContext, ConfirmDialogContext
    src/hooks/        useApiQuery, useApiMutation, useTaskPolling
    src/api/          Axios client, React Query key definitions
    src/i18n/         i18next setup with en.json, zh.json locales
    src/styles/       Split CSS bundles for app, layout, forms, cards, content, etc.
    src/types/        TypeScript API type definitions

agent/
  __init__.py         Agent singleton (SummarizeAgenticWorkflow)
  workflow/           Legacy planner/executor summarization flow
  tools/              db_tool, search_tool, filter_tool, memory_tool, writing_tool
  ps_agent/           Plan & Solve Agent (LangGraph workflow)
    graph.py            Workflow definition + routers
    state.py            PSAgentState (TypedDict)
    models.py           Pydantic models (StructurePlan, SectionUnit, etc.)
    config/thresholds.py  Configurable limits
    nodes/planner/      bootstrap, researcher, structure
    nodes/solver/       tool_executor, writer, refiner
    nodes/evaluator/    material_curation, plan_reviewer, summary_reviewer, audit_analyzer, batch_audit
    prompts/            Prompt templates (bootstrap, research, structure, writing, review, full/snippet audit, audit_analysis)
    audit/              Result parsing, batch processing
    utils/              content_fetcher

core/
  llm_client.py       Multi-provider LLM client (OpenAI, DeepSeek, Gemini, custom)
  rate_limiter.py     Token-bucket rate limiter
  embedding.py        Embedding service
  parsers.py          Content parsing utilities
  constants.py        App-wide constants
  config/             TOML + env config loading (loader.py, defaults.py, utils.py)
  crawler/            RSS feed parsing (feedparser), content extraction (trafilatura)
  db/pool.py          PostgreSQL connection pooling (async + sync)
  models/             Data models: feed.py, llm.py, search.py, config.py
  prompt/             Prompt context management

infra/
  docker/             backend.Dockerfile, frontend.Dockerfile, docker-compose.yml
  sql/schema.sql      PostgreSQL schema (feeds, feed_items, feed_brief, schedules, etc.)

test/                 Python unittest files (test_ps_agent, test_crawler, test_service, ...)
config.toml           Main configuration
pyproject.toml        Python dependencies (uv-managed)
run-backend.py        Dev server entry point
```

## Development Commands

```bash
# Backend
uv sync                                              # Install dependencies
uv run python run-backend.py                          # Dev server (auto-reload, port 8000)

# Frontend
cd apps/frontend && npm install && npm run dev        # Dev server
cd apps/frontend && npm run build                     # Production build
cd apps/frontend && npm run lint                      # ESLint

# Testing
uv run python -m unittest discover -s test -p "test*.py"
uv run python -m unittest test.test_ps_agent          # Specific test

# Docker
cd infra/docker && docker compose up --build -d       # Full stack (backend:8000 + frontend:80 + PostgreSQL:5432)
```

### Environment Variables

```bash
POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_DB=distill POSTGRES_HOST=localhost POSTGRES_PORT=5432
OPENAI_API_KEY=sk-...          # or DEEPSEEK_API_KEY / GEMINI_API_KEY / MODEL_API_KEY
TAVILY_API_KEY=...             # optional; enables web search
EMBEDDING_API_KEY=...          # optional; required when [embedding] is configured
ENV=dev                        # dev | prod | test
```

## Configuration (`config.toml`)

| Section | Purpose |
|---|---|
| `[model]` | Primary LLM: model name, provider, base_url |
| `[lightweight_model]` | Lightweight model for audit tasks |
| `[embedding]` | Embedding model config |
| `[rate_limit]` | Rate limiting: requests_per_minute, burst_size, retries, backoff |
| `[context]` | Context window: max_tokens, compress_threshold |
| `[agent_limits]` | Agent loop limits: max_iterations, max_tool_calls, max_curations, max_plan_reviews, max_refines |

## Agent Workflow

The core agent is a LangGraph `StateGraph` with three phases:

### Research Phase (inner loop)
`bootstrap → research → tooling → curation → (research | plan_review)`

- **bootstrap** — Initializes research context, extracts focus dimensions and negative keywords
- **research** (planner) — Plans tool calls for missing information
- **tooling** (solver) — Executes web search/fetch tools
- **curation** (evaluator) — Deduplicates and curates collected materials
- **plan_review** (evaluator) — Global review of research completeness

### Structure Phase
`plan_review → structure`

- **structure** (planner) — Creates the outline with writing guides for the final report

### Writing Phase (loop)
`structure → writing → reviewing → (refining → reviewing)* → finalize`

- **writing** (solver) — Generates draft sections from the outline
- **reviewing** (evaluator) — Reviews draft quality
- **refining** (solver) — Refines draft based on review feedback
- **finalize** — Assembles final report, handles best-effort fallback

### Routing

| Router | Decides | Targets |
|---|---|---|
| `curation_router` | After curation | `research` (continue) or `plan_review` (ready) |
| `plan_review_router` | After plan review | `research` (continue), `bootstrap` (replan), or `structure` (write) |
| `summary_review_router` | After draft review | `refining` (iterate) or `finalize` (done) |

### State Model (`PSAgentState`)

Key fields in the TypedDict:

- `focus`, `current_date` — User intent and date context
- `ui_language` — Optional UI language (`"zh"` or `"en"`) for progress messages
- `execution_mode` — `"NORMAL"` | `"PATCH_MODE"` | `"REPLAN_MODE"` | `"READY_TO_WRITE"`
- `messages` — Conversation history (annotated with `add`)
- `research_items`, `discarded_items` — Curated research materials
- `audit_analysis`, `audit_stage`, `audit_batch_size`, `audit_memo` — Two-stage material audit state
- `ready_for_review`, `ready_for_write` — Routing flags for plan review and writing
- `patch_diagnosis`, `replan_diagnosis` — Plan review diagnostics
- `plan` — `StructurePlan` with writing guides
- `sections` — List of `SectionUnit` (draft sections)
- `final_report` — Assembled output
- `status` — Current phase: bootstrapping, research, curating, tooling, structuring, writing, reviewing, refining, completed, failed
- Loop counters: `iteration`, `tool_call_count`, `curation_count`, `plan_review_count`, `refine_count`
- Hard limits: `max_iterations`, `max_tool_calls`, `max_curations`, `max_plan_reviews`, `max_refines`

### Two-Layer Limit System

**Layer 1 (hard limits):** State-level counters checked in routers. Exceeding a limit forces graceful degradation to the next phase.

**Layer 2 (circuit breakers):** Router-level checks that prevent infinite loops even when hard limits are disabled (`enable_hard_limits=false`).

## Database Schema

PostgreSQL with pgvector (1536-dim embeddings). Key tables:

| Table | Purpose |
|---|---|
| `feeds` | RSS feed sources |
| `feed_items` | Articles with title/summary embeddings |
| `feed_item_contents` | Full article content |
| `feed_groups` / `feed_group_items` | Feed grouping |
| `feed_brief` | Generated briefs with JSONB for `ext_info` and `expandable_topics` |
| `summary_memories` | Persistent context memories with vector search |
| `excluded_feed_item_ids` | Article exclusions per focus (with focus embeddings) |
| `schedules` | Automated brief generation schedules |

## Backend Patterns

```python
# Agent node: receive state, return dict of updates
def my_node(state: PSAgentState) -> dict:
    return {"key": value, "messages": [...]}

# LLM client: multi-provider via config
from core.llm_client import LLMClient
client = LLMClient()
response = client.complete(messages=[...])

# Async DB access
async with get_db_connection() as conn:
    result = await conn.fetch(...)
```

## Frontend Patterns

- **Data fetching:** TanStack Query with `useApiQuery` / `useApiMutation` hooks
- **State:** React Context for theme, toast, and confirm dialog; language state is managed by i18next/react-i18next
- **i18n:** i18next with `en.json` and `zh.json`, browser language detection, and localStorage key `language`
- **Styling:** TailwindCSS with `clsx` + `tailwind-merge`, plus modular CSS files under `apps/frontend/src/styles/`
- **API client:** Axios with `/api` base path, backend served at `root_path="/api"`
