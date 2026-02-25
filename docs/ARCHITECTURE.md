# Agent Architecture

This document describes the agent architecture for AI-powered news summarization.

## Overview

The system implements two agent workflows for transforming RSS feeds into intelligent briefings:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   RSS/OPML  │────▶│   Crawler   │────▶│  PostgreSQL │
└─────────────┘     └─────────────┘     └─────────────┘
                                                 │
                                                 ▼
                                    ┌───────────────────────┐
                                    │       Agent Modes     │
                                    │                       │
                                    │  ┌───────────────────┐│
                                    │  │  Legacy Workflow  ││
                                    │  │  (Planner+Executor)││
                                    │  └───────────────────┘│
                                    │                       │
                                    │  ┌───────────────────┐│
                                    │  │   PS Agent        ││
                                    │  │  (LangGraph)      ││
                                    │  └───────────────────┘│
                                    └───────────────────────┘
                                                 │
                              ┌──────────────────┴──────────────────┐
                              ▼                                     ▼
                        ┌─────────────┐                      ┌─────────────┐
                        │  LLM APIs   │                      │ Web Search  │
                        │(OpenAI/Deep │                      │  (Tavily)   │
                        │ Seek/Gemini)│                      └─────────────┘
                        └─────────────┘
```

## Agent Modes

### PS Agent (Recommended)

A LangGraph-based agentic workflow with multi-stage research and structured writing.

#### Research Phase

The PS Agent uses a **two-level loop** for research: an inner loop (research → tooling → curation) and an outer loop where `plan_review` decides whether to patch, replan, or proceed to writing.

**Inner loop (research → tooling → curation)**

```
bootstrap ──▶ research ──▶ tooling ──▶ curation
                 ▲                      │
                 └───────────┬──────────┘
                             ▼
                    (continue research
                      or go to plan_review)
```

**Outer loop (plan_review routing)**

```
curation ──▶ plan_review ──▶ research    # PATCH_MODE: fill gaps in current plan
                        └─▶ bootstrap   # REPLAN_MODE: discard plan and restart
                        └─▶ structure   # READY_TO_WRITE: proceed to writing
```

**Stage roles**

| Stage | Description |
|-------|-------------|
| `bootstrap` | Build initial focus, dimensions, and filter keywords from today’s RSS and history |
| `research` | Plan query strategy; decide which tools to call and which queries to run |
| `tooling` | Execute tool calls: `search_feeds`, `search_web`, `search_memory` |
| `curation` | Evaluate new material, merge and dedupe, decide if material is sufficient |
| `plan_review` | Global review of research progress: ready to write? Need to patch or replan? |

**Circuit breakers (configurable in `config.toml [agent_limits]`):**
- `max_iterations` – Max research loop iterations
- `max_tool_calls` – Max total tool calls
- `max_curations` – Max curation cycles
- `max_plan_reviews` – Max plan review cycles

#### Structure & Writing Phase

When `plan_review` sets READY_TO_WRITE, the agent enters structure and writing:

```
structure ──▶ writing ──▶ reviewing ──▶ finalize
                          ▲
                          │
                     refining
                          │
                          └──────────┘
```

- **structure** – Turn research material into a section outline and writing guides
- **writing** – Produce the first full draft from the outline
- **reviewing** – Self-critique the draft; decide whether to finish or refine
- **refining** – Revise the draft from review feedback, then return to reviewing
- **finalize** – Assemble the best sections into the final report and set `final_report`

**Circuit breakers:** `max_refines` limits how many refinement cycles are allowed.

#### Multi-Layer Protection

Two layers prevent runaway loops:

- **Layer 1:** State-level counters (e.g. iteration, tool_call_count) enforced at each transition; limits come from `config.toml [agent_limits]`.
- **Layer 2:** Router-level checks – `curation_router`, `plan_review_router`, `summary_review_router` – decide whether to continue, replan, or proceed.

### Legacy Workflow

A simpler two-phase workflow:

```
Planner → Executor
```

- **Planner** – Plans focus topics per group using the LLM.
- **Executor** – Runs summarization with available tools (search, memory, writing, etc.).

This workflow is faster but less capable than the PS Agent.

## Agent Tools

Both modes rely on a shared set of low-level tools:

| Tool | Description |
|------|-------------|
| `db_tool` | Query feeds, articles, and groups from PostgreSQL |
| `memory_tool` | Semantic search and memory storage via embeddings |
| `search_tool` | Web search (Tavily) and HTML content fetching |
| `writing_tool` | Article writing and review (mainly legacy workflow) |
| `filter_tool` | Keyword extraction and scoring with LLM (legacy workflow) |

In the PS Agent, the LLM sees **function-calling tools** `search_feeds`, `search_web`, and `search_memory` (implemented under `agent/ps_agent/tools/`).

## State Management

The PS Agent keeps a typed state across nodes (e.g. `run_id`, `focus`, `messages`, `research_items`, `plan`, `sections`, `final_report`, and counters for iterations, tool calls, curations, plan reviews, refines). Full definition: `agent/ps_agent/state.py`.

## Configuration

Research and writing limits are set in `config.toml` under `[agent_limits]` (e.g. `max_iterations`, `max_tool_calls`, `max_curations`, `max_plan_reviews`, `max_refines`, `enable_hard_limits`). See `docs/CONFIG.md` for the full list.

## Workflow Library Packaging Roadmap

A concrete monorepo subpackage migration plan for introducing a separate package boundary for `distill_workflow_lib` is documented in [`docs/DISTILL_WORKFLOW_LIB_PACKAGING_PLAN.md`](./DISTILL_WORKFLOW_LIB_PACKAGING_PLAN.md).

## Directory Structure

```
agent/
├── ps_agent/                  # LangGraph Plan-Solve Agent
│   ├── graph.py               # StateGraph (nodes + edges)
│   ├── state.py               # PSAgentState and initial state
│   ├── models.py              # Typed models (sections, diagnoses, etc.)
│   ├── prompts/               # System and user prompts per phase
│   ├── nodes/                 # planner / solver / evaluator nodes
│   │   ├── planner/           # bootstrap, researcher, structure
│   │   ├── solver/            # writer, refiner, tool_executor
│   │   └── evaluator/         # material_curation, plan_reviewer, summary_reviewer, batch_audit
│   ├── tools/                 # search_feeds / search_web / search_memory schemas and handlers
│   ├── config/                # Thresholds and tuning
│   ├── audit/                 # Audit parsing and batch audit pipeline
│   └── utils/                 # Content fetch helpers
├── workflow/                  # Legacy Planner + Executor
│   ├── planner.py
│   └── executor.py
└── tools/                     # Shared low-level tools
    ├── db_tool.py
    ├── memory_tool.py
    ├── search_tool.py
    ├── writing_tool.py
    └── filter_tool.py
```

