"""Normalized provider contract. The orchestrator only ever sees these types."""
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal, Protocol


class LLMError(Exception):
    """Normalized provider failure. code: timeout|rate_limit|auth|unavailable|bad_request."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMMessage:
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None


@dataclass
class LLMRequest:
    system: str
    messages: list[LLMMessage]
    tools: list[ToolSpec] = field(default_factory=list)
    max_tokens: int = 1024


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCallEvent:
    call: ToolCall


@dataclass
class UsageEvent:
    input_tokens: int = 0
    output_tokens: int = 0


StreamEvent = TextDelta | ToolCallEvent | UsageEvent


class LLMProvider(Protocol):
    name: str
    model: str
    # Capabilities differ between providers; callers consult these, never assume.
    supports_tools: bool

    def stream(self, request: LLMRequest) -> Iterator[StreamEvent]: ...
