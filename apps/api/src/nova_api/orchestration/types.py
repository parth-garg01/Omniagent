from dataclasses import dataclass, field
from typing import Protocol

from ..llm.interfaces import ToolCall, ToolSpec


@dataclass
class Source:
    document_id: str
    filename: str
    chunk_index: int
    content: str
    score: float
    meta: dict = field(default_factory=dict)


@dataclass
class ToolOutcome:
    status: str  # succeeded | failed | denied | pending_confirmation
    content: str  # JSON string handed back to the model (untrusted by the orchestrator)
    summary: str
    execution_id: str | None = None


class Retriever(Protocol):
    def __call__(self, db, user, query: str) -> list[Source]: ...


class ToolRunner(Protocol):
    def specs(self, user) -> list[ToolSpec]: ...

    def execute(self, db, user, conversation_id: str, message_id: str | None,
                call: ToolCall) -> ToolOutcome: ...
