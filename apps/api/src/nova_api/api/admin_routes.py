from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.deps import require
from ..config import get_settings
from ..db import get_db
from ..models import User
from ..observability import metrics

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/health")
def admin_health(user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    s = get_settings()
    # Deliberately excludes keys, URLs and any other configuration values.
    return {"status": "ok", "database": "ok", "llm_provider": s.llm_provider,
            "llm_key_configured": bool(s.anthropic_api_key)}


@router.get("/metrics")
def admin_metrics(user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    return metrics.collect(db)
