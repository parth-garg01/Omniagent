from ..llm.interfaces import LLMError, LLMProvider


def select_provider(candidates: list[LLMProvider], needs_tools: bool) -> LLMProvider:
    """Deterministic routing on declared capabilities only (no confidence heuristics).

    Candidates are tried in configured order; the first one that can satisfy the task wins.
    """
    for p in candidates:
        if needs_tools and not p.supports_tools:
            continue
        return p
    raise LLMError("unavailable", "No configured provider supports this request")
