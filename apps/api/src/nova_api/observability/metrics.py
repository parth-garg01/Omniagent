from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Message, ToolExecution


def collect(db: Session) -> dict:
    assistants = db.scalars(select(Message).where(Message.role == "assistant")).all()
    lat = sorted(m.token_usage["latency_ms"] for m in assistants
                 if m.token_usage and "latency_ms" in m.token_usage)

    def pct(p: float) -> int | None:
        return lat[min(len(lat) - 1, int(p * len(lat)))] if lat else None

    total = len(assistants)
    errors = sum(1 for m in assistants if m.status == "error")
    tokens_in = sum((m.token_usage or {}).get("input_tokens", 0) for m in assistants)
    tokens_out = sum((m.token_usage or {}).get("output_tokens", 0) for m in assistants)
    tools = dict(db.execute(select(ToolExecution.status, func.count()).group_by(ToolExecution.status)).all())
    cited = sum(1 for m in assistants if m.citations)
    return {
        "responses": total, "error_rate": round(errors / total, 4) if total else 0.0,
        "latency_ms": {"p50": pct(0.5), "p95": pct(0.95)},
        "tokens": {"input": tokens_in, "output": tokens_out},
        "tool_executions": tools, "responses_with_citations": cited,
        # No pricing table is configured, so cost is reported as unknown rather than guessed.
        "estimated_cost_usd": None,
    }
