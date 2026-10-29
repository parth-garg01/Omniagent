# ADR 0001: Modular monolith for the Nova demo

**Status:** accepted. **Context:** the repository started empty, so there was no existing code to preserve.

## Decisions
- FastAPI modular monolith under `apps/api/src/nova_api`; modules map to the PRD (auth, orchestration, llm, rag, tools, mcp, routing, cache, observability, evaluation).
- SQLAlchemy 2 models. SQLite by default (zero setup, used in tests); PostgreSQL via Docker Compose.
- **Embeddings are stored as JSON and scored in Python**, not pgvector, to keep one code path across SQLite and Postgres. The `Embedder` interface and `document_chunks.embedding` column are the swap points for pgvector.
- Tables are created with `create_all` at startup. **Alembic migrations are not implemented yet.**
- The fake LLM and hashing embedder are deterministic stand-ins so everything runs offline. They are not models.
- Ingestion is synchronous (demo scale). Rate limiting is in-process and single-instance.

## Consequences
The demo is runnable and testable with no external services. Production hardening (migrations, pgvector, background ingestion, distributed rate limits) is listed in the README under Limitations.
