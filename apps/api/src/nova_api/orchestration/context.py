from sqlalchemy import select
from sqlalchemy.orm import Session

from ..llm.interfaces import LLMMessage
from ..models import Message

MAX_CONTEXT_CHARS = 12000


def build_history(db: Session, conversation_id: str, max_messages: int) -> list[LLMMessage]:
    """Most recent complete user/assistant turns, bounded by count and characters.

    Scoped to a single conversation id; callers verify ownership before calling.
    """
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.role.in_(("user", "assistant")))
        .order_by(Message.sequence_number.desc())
        .limit(max_messages * 2)
    ).all()
    kept: list[Message] = []
    total = 0
    for m in rows:  # newest first
        if m.role == "assistant" and (m.status != "complete" or not m.content):
            continue
        if len(kept) >= max_messages or total + len(m.content) > MAX_CONTEXT_CHARS:
            break
        kept.append(m)
        total += len(m.content)
    kept.reverse()
    while kept and kept[0].role != "user":  # providers expect the first turn to be the user's
        kept.pop(0)
    return [LLMMessage(m.role, m.content) for m in kept]
