from collections.abc import Iterator

from .interfaces import LLMError, LLMProvider, LLMRequest

RETRYABLE = {"timeout", "rate_limit", "unavailable"}


class FallbackProvider:
    """Tries providers in order. Falls back only on retryable errors raised BEFORE any output,
    so a partially streamed answer is never silently replaced or duplicated."""

    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise ValueError("at least one provider required")
        self._providers = providers
        self.name = "+".join(p.name for p in providers)
        self.model = providers[0].model
        self.supports_tools = all(p.supports_tools for p in providers)

    def stream(self, request: LLMRequest) -> Iterator:
        last: LLMError | None = None
        for p in self._providers:
            started = False
            try:
                for ev in p.stream(request):
                    started = True
                    yield ev
                return
            except LLMError as e:
                if started or e.code not in RETRYABLE:
                    raise
                last = e
        assert last is not None
        raise last
