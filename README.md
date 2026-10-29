# Nova (Omniagent): company-agnostic AI chatbot, demo

A locally runnable demo of the Nova PRD: streaming chat, RAG with citations, permission-controlled mock tools, local auth, evaluation and observability. **Everything is mock/local. No real company integrations or external actions exist.**

## Quick start (no Docker, offline)
```bash
make setup                 # venv + API deps
make seed                  # synthetic users, orders, shared docs (SQLite ./nova.db)
make run                   # API on :8000
make web-install && cd apps/web && npm run dev   # UI on :5173 (proxies /api)
```
Seeded accounts (password `demo-password-1`): `alice@example.com`, `bob@example.com` (users), `admin@example.com`, `eval@example.com` (read-only evaluator).

Try: *"Where is ORD-1002?"*, *"Refund ORD-1001"* (asks for confirmation), *"What is the refund policy?"* (cited), *"Open a ticket about my broken screen"*.

## Docker Compose (Postgres + API + web)
```bash
cp .env.example .env
make up      # UI http://localhost:5173, API http://localhost:8000/docs
```
Compose has not been run by the author of this README on this machine; treat it as untested until you verify it.

## Providers
Default is the deterministic **fake** provider (rule-based, not a language model). To use Grok (xAI) set `NOVA_LLM_PROVIDER=grok` and `NOVA_GROK_API_KEY` in `.env` (optionally `NOVA_GROK_MODEL`, default `grok-4` is an assumption). The adapter speaks the OpenAI-compatible chat API, so `NOVA_GROK_BASE_URL` also works for other compatible endpoints. It has been run live (streaming, tool calls, RAG, confirmation flow) against **Groq** (`https://api.groq.com/openai/v1`, model `openai/gpt-oss-120b`, key format `gsk_...`), not against xAI itself (`xai-...` keys). See `docs/extending.md`.

## Tests
```bash
make test && make lint     # API: pytest + ruff (offline, no API key)
make web-test && make web-build
make eval                  # RAG recall@5, abstention and tool-selection report
```

## Layout
`apps/api/src/nova_api/` auth · orchestration · llm · rag · tools · mcp · routing · cache · observability · evaluation. `apps/web/` React UI. `evals/` datasets. `data/seed/` sample documents. See `docs/adr-0001-architecture.md` and `SECURITY.md`.

## Limitations (honest status)
- Embeddings are a lexical hashing stand-in stored as JSON, scored in Python; **pgvector is not used yet**.
- No Alembic migrations; tables are created at startup.
- Ingestion is synchronous; login throttling and cancel state are in-process.
- Response cache exists but is disabled and not wired into chat. Model routing is limited to an optional fallback provider.
- MCP is an adapter boundary with an in-process test stand-in; no transport.
- No performance benchmarks have been run.
