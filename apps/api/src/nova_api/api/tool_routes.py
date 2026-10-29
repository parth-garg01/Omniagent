from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth.deps import require
from ..db import get_db
from ..models import Conversation, ToolExecution, User
from ..orchestration.engine import add_message

router = APIRouter(prefix="/api/v1", tags=["tools"])


def _note(db: Session, ex: ToolExecution, text: str) -> None:
    conv = db.get(Conversation, ex.conversation_id)
    if conv:
        add_message(db, conv, "assistant", text)
        conv.updated_at = datetime.now(UTC)
        db.commit()


def _out(ex: ToolExecution) -> dict:
    return {"id": ex.id, "tool_name": ex.tool_name, "status": ex.status,
            "result_summary": ex.result_summary}


@router.get("/tools")
def list_tools(request: Request, user: User = Depends(require("chat"))):
    return [t.describe() for t in request.app.state.tools.available(user)]


@router.post("/tool-executions/{execution_id}/confirm")
def confirm(execution_id: str, request: Request, user: User = Depends(require("tool:write")),
            db: Session = Depends(get_db)):
    try:
        ex = request.app.state.tools.confirm(db, user, execution_id)
    except (LookupError, PermissionError) as e:
        raise HTTPException(404, "Execution not found") from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    # The reported outcome is the tool's real status, never the model's claim.
    if ex.status == "succeeded":
        _note(db, ex, f"Confirmed. {ex.result_summary}")
    else:
        _note(db, ex, f"The confirmed action failed: {ex.result_summary}")
    return _out(ex)


@router.post("/tool-executions/{execution_id}/cancel")
def cancel(execution_id: str, request: Request, user: User = Depends(require("tool:write")),
           db: Session = Depends(get_db)):
    try:
        ex = request.app.state.tools.cancel(db, user, execution_id)
    except LookupError as e:
        raise HTTPException(404, "Execution not found") from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    _note(db, ex, f"Cancelled. No action was taken for {ex.tool_name}.")
    return _out(ex)
