## FlashAiNews

AI‑powered news briefings from your RSS sources. It crawls feeds (and the web when needed) and uses LLMs to produce concise, topic‑grouped summaries.

---

## What it does (LLM-first)
- **Planning + summarization**: LLM plans focus topics per group and writes concise briefs and per-article highlights.
- **Reasoned context**: Keeps topic reasoning alongside summaries so readers see the “why”, not just the “what”.
- **Retrieval for relevance**: Optional semantic memory (embeddings) to reduce duplicates and add historic context.
- **Self-enrichment**: Optional web search + content fetch when feeds are sparse to improve summary quality.

### Architecture (logical)
```
RSS/OPML -> Crawler -> PostgreSQL
                    \-> Agent (LLM + tools + embeddings)
Frontend (React/Vite) <-> Backend API (FastAPI) <-> External LLM APIs
```

---

## Quick start (Docker, recommended)

```bash
git clone https://github.com/your-org/FlashAiNews.git
cd FlashAiNews

cat <<'ENV' > .env
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
ENV

cp config.toml.example config.toml
cd infra/docker
docker compose up --build -d
```

Configuration details (env vars, `config.toml`, local dev) are documented in [`docs/CONFIG.md`](docs/CONFIG.md).

---

## License

[MIT License](LICENSE)
