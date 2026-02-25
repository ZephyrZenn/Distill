# Distill

<div align="center">

  <!-- Distill Icon -->
  <img src="apps/frontend/public/favicon.svg" alt="Distill Logo" width="120" height="120">

  **AI-Powered News Briefings from Your RSS Sources**

  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
  [![React](https://img.shields.io/badge/React-18+-cyan.svg)](https://react.dev)

  [Features](#-features) • [Quick Start](#-quick-start) • [Configuration](#-configuration)

</div>

---

## ✨ Features

Distill transforms your RSS feeds into intelligent, AI-powered briefings. Unlike traditional feed readers, it doesn't just aggregate content—it **understands, organizes, and synthesizes** information.

- **Reasoned Context** – See not just what happened, but *why* it matters. LLMs provide topic reasoning alongside summaries.
- **Smart Grouping** – Articles are automatically clustered by topic and grouped by feed source for coherent narratives.
- **Agentic Research** – Built on LangGraph, our Plan-Solve Agent conducts multi-stage research with web search and memory retrieval.
- **Semantic Memory** – Optional vector embeddings reduce duplicates and add historic context to new briefings.
- **Self-Enrichment** – When feeds are sparse, automatically fetches full content and performs web searches for comprehensive coverage.
- **OPML Support** – Import your existing feed subscriptions from any RSS reader.

## 🏗️ Architecture

Distill combines a modern tech stack with agentic AI workflows:

- **Backend** – FastAPI serving REST APIs
- **Frontend** – React + Vite SPA with TailwindCSS
- **Agent Modes** – Two summarization workflows:
  - **Legacy Workflow** – Two-phase planner + executor
  - **PS Agent** – LangGraph-based research and structured writing
- **Crawler** – RSS feed parser with web content fetching

For detailed architecture, components, and database schema, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

For the planned monorepo subpackage migration of `distill_workflow_lib`, see [`docs/DISTILL_WORKFLOW_LIB_PACKAGING_PLAN.md`](docs/DISTILL_WORKFLOW_LIB_PACKAGING_PLAN.md).

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- An API key for an LLM provider (OpenAI, DeepSeek, Gemini, or any OpenAI-compatible API)
- (Optional) Tavily API key for web search

### Docker Deployment (Recommended)

```bash
# Clone the repository
git clone https://github.com/ZephyrZenn/Distill.git
cd distill

# Create environment file
cat <<'ENV' > .env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=changeme
POSTGRES_DB=distill
POSTGRES_HOST=db
POSTGRES_PORT=5432
ENV=prod

# Choose one LLM provider
OPENAI_API_KEY=sk-your-openai-api-key
# DEEPSEEK_API_KEY=your-deepseek-api-key
# GEMINI_API_KEY=your-gemini-api-key
# MODEL_API_KEY=your-custom-api-key  # For OpenAI-compatible APIs

# Optional: Web search and embeddings
TAVILY_API_KEY=your-tavily-api-key
EMBEDDING_API_KEY=sk-your-embedding-api-key
ENV

# Copy settings template
cp config.toml.example config.toml

# Start all services
cd infra/docker
docker compose up --build -d
```

The application will be available at `http://localhost:5173`.

Before running in production, open `config.toml` and adjust your model/provider, rate limits, and agent limits to match your environment (see [`docs/CONFIG.md`](docs/CONFIG.md) for all options).

## 🧠 Agent Modes

Distill provides two agent modes for different use cases:

### PS Agent Mode

A LangGraph-based agentic research workflow with multi-stage processing:

**Research Phase:** `bootstrap → research → tooling → curation → plan_review` (loops)
- Web search, database queries, and memory retrieval
- Self-assessment of information completeness

**Structure Phase:** `structure → writing → reviewing → refining` (loops)
- Organizes research into coherent sections
- Self-critiques and improves draft quality

Includes multi-layer circuit breakers to prevent runaway loops and control costs.

### Legacy Workflow Mode

A simpler two-phase workflow:
- **Planner** – Plans focus topics per group
- **Executor** – Executes summarization with available tools

### Local Development

**Backend (Python):**
```bash
# Create virtual environment and install dependencies with uv
uv venv
uv sync

# Start backend (auto-reload)
uv run python run-backend.py
```

**Frontend (Node.js):**
```bash
cd apps/frontend
npm install
npm run dev
```

## ⚙️ Configuration

### Minimum Setup

Create a `.env` file with your database and LLM provider:

```bash
# Database (required)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=changeme
POSTGRES_DB=distill
POSTGRES_HOST=db
POSTGRES_PORT=5432
ENV=prod

# Choose one LLM provider (required)
OPENAI_API_KEY=sk-your-key
# DEEPSEEK_API_KEY=your-key
# GEMINI_API_KEY=your-key
# MODEL_API_KEY=your-custom-api-key  # For OpenAI-compatible APIs

# Optional: for web search and embeddings
TAVILY_API_KEY=your-key
EMBEDDING_API_KEY=sk-your-key
```

Copy `config.toml.example` to `config.toml` to customize model settings, rate limits, and agent behavior.  
All model / provider / base_url options are read **only** from `config.toml` (environment variables are used for API keys and runtime mode, not for overriding model config).

### LLM Provider Support

Distill supports multiple LLM providers:

- **OpenAI** – GPT models (set `provider = "openai"` in config.toml)
- **DeepSeek** – DeepSeek models (set `provider = "deepseek"`)
- **Gemini** – Google Gemini models (set `provider = "gemini"`)
- **OpenAI-compatible APIs** – Any API with OpenAI-compatible interface (set `provider = "other"` and provide `base_url`)

For custom OpenAI-compatible APIs, configure in `config.toml`:

```toml
[model]
provider = "other"
model = "your-model-name"
base_url = "https://your-api-endpoint.com/v1"
```

Then set `MODEL_API_KEY` in your environment.

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `POSTGRES_*` | Database connection | Yes |
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `GEMINI_API_KEY` / `MODEL_API_KEY` | LLM provider API key | At least one |
| `TAVILY_API_KEY` | Web search | Optional |
| `EMBEDDING_API_KEY` | Vector embeddings | Optional |

For full configuration reference, see [`docs/CONFIG.md`](docs/CONFIG.md).



## 📄 License

This project is licensed under the [MIT License](LICENSE).

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com), [React](https://react.dev), and [LangGraph](https://github.com/langchain-ai/langgraph)
- Inspired by the need for intelligent information synthesis in an age of information overload
