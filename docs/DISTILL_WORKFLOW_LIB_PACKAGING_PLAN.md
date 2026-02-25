# distill_workflow_lib Packaging Boundary Migration Plan

## Goal

Introduce a **separate library package boundary** for `distill_workflow_lib` inside this monorepo, with its own `pyproject.toml`, while keeping migration risk low and allowing incremental adoption by backend/agent code.

This plan focuses on structure, dependency split, and rollout steps (not large refactors in this PR).

## Non-goals for this phase

- No full code move in one shot
- No behavior changes to planner/executor runtime
- No external publishing pipeline implementation yet

## Recommended target structure (monorepo subpackage)

```text
Distill/
├── apps/
├── agent/
├── core/
├── distill_workflow_lib/                # current import path kept for now
├── packages/
│   └── distill-workflow-lib/
│       ├── pyproject.toml               # independent package metadata
│       ├── README.md
│       └── src/
│           └── distill_workflow_lib/
│               ├── __init__.py
│               ├── api.py
│               ├── workflow.py
│               ├── planner.py
│               ├── executor.py
│               ├── providers.py
│               └── types.py             # optional extracted shared typing contracts
├── pyproject.toml                        # app/backend meta package
└── uv.lock
```

## Dependency split

### `packages/distill-workflow-lib` (new library boundary)

Keep this package focused on workflow orchestration contracts and runtime wiring:

- **Required**
  - `pydantic` (if library models keep using it)
  - `typing-extensions` (if needed)
- **Optional extras**
  - `llm`: provider clients (`openai`, `google-genai`, etc.) only if directly imported by library
  - `db`: `psycopg`, `pgvector` only for DB-backed provider adapters

Design principle: **default install should be as lean as possible**. DB/LLM integrations should be extras where practical.

### Root app package (`Distill/pyproject.toml`)

Keep backend/web/runtime dependencies here:

- FastAPI/uvicorn, scheduler, crawler libs, frontend tooling, service-only deps
- Depend on workflow lib via local path in dev:
  - `distill-workflow-lib @ file://.../packages/distill-workflow-lib`
  - or workspace dependency support when enabled

## Import and ownership boundaries

Target ownership:

- `distill_workflow_lib`: engine contracts + planner/executor/workflow API
- `agent/`: agent-specific integrations, runtime composition, DB provider adapters
- `apps/backend/`: API/service layer only; no workflow provider definitions

Rule of thumb: if code is generic workflow engine logic, it belongs in the package; if code touches app runtime infra, keep it outside.

## Release and install strategy (skill repo friendly)

Recommended staged approach:

1. **Monorepo local package first**
   - Introduce `packages/distill-workflow-lib/pyproject.toml`
   - Install via local path/workspace in `uv`
2. **Internal versioning discipline**
   - Start semver tags for library (`distill-workflow-lib`)
   - Keep changelog entries scoped to package changes
3. **Optional external publish later**
   - Publish to private/public index only after import boundaries stabilize
   - Skill repos can pin versions (`distill-workflow-lib>=0.x,<0.y`) instead of vendoring code

For downstream skill repos, prefer installing package artifact rather than copying workflow source files.

## Transition steps

### Phase 0 (this PR)

- Remove backend compatibility shim for workflow DB providers (`apps/backend/adapters/workflow_db_provider.py`)
- Document migration plan and boundaries
- Add guard test to prevent shim reintroduction

### Phase 1

- Add `packages/distill-workflow-lib/pyproject.toml` + `src/` skeleton
- Mirror current library code into `src/distill_workflow_lib` without logic changes
- Keep root-level imports working via compatibility period

### Phase 2

- Move imports in app/agent code to package-installed `distill_workflow_lib`
- Reduce root `pyproject.toml` dependency surface; keep only app/runtime deps
- Add CI job to run library tests in isolated environment (`cd packages/distill-workflow-lib && pytest`)

### Phase 3

- Remove legacy duplicate path once all imports point to package boundary
- Enforce boundary checks (no backend -> provider shim, no app-only deps inside package core)
- Cut first stable package release used by external skill repos

## Suggested guardrails

- Add static import checks in tests for forbidden cross-layer imports
- Keep provider interfaces in lib, DB-backed concrete implementations outside or behind optional extras
- Require changelog entry for any cross-boundary move

## Open decisions to finalize before Phase 1

- Whether DB-backed provider implementations remain in `agent/` permanently or move into package `db` extra
- Exact workspace/install mechanism (`uv` workspace vs path dependency)
- Versioning cadence with main app releases
