import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import current_user
from ..auth.ratelimit import limit_messages
from ..config import get_settings
from ..db import get_db
from ..llm import build_provider
from ..llm.interfaces import LLMError
from ..models import Conversation, Message, User
from ..orchestration import engine

router = APIRouter(prefix="/api/v1", tags=["chat"])


def owned_conversation(db: Session, conversation_id: str, user: User) -> Conversation:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:  # 404 for both: do not reveal existence
        raise HTTPException(404, "Conversation not found")
    return conv


class ConversationOut(BaseModel):
    id: str
    title: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    status: str
    sequence_number: int
    citations: list | None = None
    feedback: str | None = None

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationPatch(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class SendMessage(BaseModel):
    content: str = Field(min_length=1)
    client_message_id: str | None = Field(default=None, max_length=64)
    stream: bool = True


class Feedback(BaseModel):
    value: str = Field(pattern="^(up|down)$")


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(user: User = Depends(current_user), db: Session = Depends(get_db)):
    conv = Conversation(user_id=user.id)
    db.add(conv)
    db.commit()
    return conv


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Conversation).where(Conversation.user_id == user.id)
                      .order_by(Conversation.updated_at.desc())).all()


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    conv = owned_conversation(db, conversation_id, user)
    msgs = db.scalars(select(Message).where(Message.conversation_id == conv.id)
                      .order_by(Message.sequence_number)).all()
    return {"id": conv.id, "title": conv.title, "updated_at": conv.updated_at, "messages": msgs}


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def rename_conversation(conversation_id: str, body: ConversationPatch,
                        user: User = Depends(current_user), db: Session = Depends(get_db)):
    conv = owned_conversation(db, conversation_id, user)
    conv.title = body.title
    db.commit()
    return conv


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    from ..models import ToolExecution

    conv = owned_conversation(db, conversation_id, user)
    for model in (Message, ToolExecution):
        for row in db.scalars(select(model).where(model.conversation_id == conv.id)):
            db.delete(row)
    db.delete(conv)
    db.commit()


def _sse(ev: dict) -> str:
    return f"event: {ev['event']}\ndata: {json.dumps(ev['data'])}\n\n"


@router.post("/conversations/{conversation_id}/messages")
def send_message(conversation_id: str, body: SendMessage, request: Request,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_settings()
    conv = owned_conversation(db, conversation_id, user)
    limit_messages(user.id)
    if len(body.content) > s.max_message_chars:
        raise HTTPException(413, f"Message exceeds {s.max_message_chars} characters")
    try:
        provider = build_provider(s)
    except LLMError as e:
        raise HTTPException(503, e.message) from e
    conv.updated_at = datetime.now(UTC)
    db.commit()
    events = engine.run_turn(user.id, conv.id, body.content, body.client_message_id, provider,
                             retriever=request.app.state.retriever,
                             tools=request.app.state.tools)
    if body.stream:
        return StreamingResponse((_sse(e) for e in events), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    last = None
    for e in events:
        if e["event"] in ("done", "error"):
            last = e if last is None or e["event"] == "done" else last
    if last is None:
        raise HTTPException(500, "No response")
    if last["event"] == "error":
        raise HTTPException(502, last["data"]["message"])
    return last["data"]


@router.post("/conversations/{conversation_id}/cancel", status_code=202)
def cancel(conversation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conv = owned_conversation(db, conversation_id, user)
    engine.request_cancel(conv.id)
    return {"status": "cancelling"}


@router.post("/messages/{message_id}/feedback", status_code=204)
def feedback(message_id: str, body: Feedback, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    msg = db.get(Message, message_id)
    if msg is None:
        raise HTTPException(404, "Message not found")
    owned_conversation(db, msg.conversation_id, user)
    msg.feedback = body.value
    db.commit()
