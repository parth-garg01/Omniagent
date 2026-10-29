"""Deterministic evaluation runners. Each returns a metrics dict; nothing here calls a network."""
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..db import Base, make_engine
from ..llm import build_provider
from ..llm.interfaces import LLMMessage, LLMRequest, ToolCallEvent
from ..models import EvaluationRun, User
from ..rag import service as rag_service
from ..tools.mock_tools import build_registry

DATASET_VERSION = "v1"
TOP_K = 5


def _repo_root() -> Path:
    for p in Path(__file__).resolve().parents:
        if (p / "evals" / "datasets").is_dir():
            return p
    raise FileNotFoundError("evals/datasets not found")


def load_dataset(name: str) -> list[dict]:
    path = _repo_root() / "evals" / "datasets" / f"{name}_{DATASET_VERSION}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _isolated_session() -> Session:
    """Private in-memory DB so evaluations never touch (or depend on) live data."""
    from .. import models  # noqa: F401
    from ..seed import seed

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(engine, expire_on_commit=False)()
    seed(s)
    return s


def run_rag() -> dict:
    data = load_dataset("rag")
    s = _isolated_session()
    user = s.query(User).filter_by(email="alice@example.com").one()
    answerable = [d for d in data if "expect_file" in d]
    abstain = [d for d in data if d.get("expect_abstain")]
    failures = []
    hits = 0
    for d in answerable:
        files = [src.filename for src in rag_service.retrieve(s, user, d["question"], TOP_K)]
        if d["expect_file"] in files:
            hits += 1
        else:
            failures.append({"id": d["id"], "got": files})
    abstained = 0
    for d in abstain:
        if not rag_service.retrieve(s, user, d["question"], TOP_K):
            abstained += 1
        else:
            failures.append({"id": d["id"], "got": "sources returned"})
    return {"dataset": f"rag_{DATASET_VERSION}", "recall_at_5": round(hits / len(answerable), 4),
            "abstention_rate": round(abstained / len(abstain), 4) if abstain else None,
            "cases": len(data), "failures": failures,
            "config": {"chunk_size": get_settings().chunk_size,
                       "min_score": get_settings().retrieval_min_score}}


def run_tools() -> dict:
    data = load_dataset("tools")
    provider = build_provider(get_settings())
    s = _isolated_session()
    user = s.query(User).filter_by(email="alice@example.com").one()
    specs = build_registry().specs(user)
    correct_tool = correct_args = 0
    failures = []
    for d in data:
        calls = [e.call for e in provider.stream(LLMRequest("", [LLMMessage("user", d["message"])], specs))
                 if isinstance(e, ToolCallEvent)]
        got = calls[0] if calls else None
        tool_ok = (got.name if got else None) == d["expect_tool"]
        args_ok = tool_ok and all((got.arguments if got else {}).get(k) == v
                                  for k, v in d["expect_args"].items())
        correct_tool += tool_ok
        correct_args += args_ok
        if not (tool_ok and args_ok):
            failures.append({"id": d["id"], "got": got.name if got else None})
    n = len(data)
    return {"dataset": f"tools_{DATASET_VERSION}", "tool_selection_accuracy": round(correct_tool / n, 4),
            "argument_accuracy": round(correct_args / n, 4), "cases": n, "failures": failures,
            "config": {"provider": provider.name, "model": provider.model}}


RUNNERS = {"rag": run_rag, "tools": run_tools}


def run_and_store(db: Session, dataset: str) -> EvaluationRun:
    metrics = RUNNERS[dataset]()
    run = EvaluationRun(dataset_name=metrics["dataset"], metrics=metrics, status="complete")
    db.add(run)
    db.commit()
    return run


if __name__ == "__main__":
    out = {name: fn() for name, fn in RUNNERS.items()}
    out["generated_at"] = datetime.now(UTC).isoformat()
    print(json.dumps(out, indent=2))
