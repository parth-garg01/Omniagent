from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..auth.deps import require
from ..config import get_settings
from ..db import get_db
from ..models import EvaluationRun, User
from ..observability import metrics

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/health")
def admin_health(user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    s = get_settings()
    # Deliberately excludes keys, URLs and any other configuration values.
    return {"status": "ok", "database": "ok", "llm_provider": s.llm_provider,
            "llm_key_configured": bool(s.grok_api_key)}


@router.get("/metrics")
def admin_metrics(user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    return metrics.collect(db)


class EvalRequest(BaseModel):
    dataset: str = Field(pattern="^(rag|tools)$")


def _run_out(r: EvaluationRun) -> dict:
    return {"id": r.id, "dataset_name": r.dataset_name, "status": r.status,
            "metrics": r.metrics, "created_at": r.created_at}


@router.post("/evaluations", status_code=201)
def start_evaluation(body: EvalRequest, user: User = Depends(require("admin")),
                     db: Session = Depends(get_db)):
    from ..evaluation.runner import run_and_store

    return _run_out(run_and_store(db, body.dataset))


@router.get("/evaluations")
def list_evaluations(user: User = Depends(require("eval:read")), db: Session = Depends(get_db)):
    runs = db.scalars(select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(50)).all()
    return [_run_out(r) for r in runs]


@router.get("/evaluations/{run_id}")
def get_evaluation(run_id: str, user: User = Depends(require("eval:read")),
                   db: Session = Depends(get_db)):
    run = db.get(EvaluationRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return _run_out(run)
