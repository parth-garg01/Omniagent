from ..config import Settings
from .interfaces import LLMError, LLMProvider


def build_provider(settings: Settings) -> LLMProvider:
    """Select a provider by configuration; the orchestrator never imports a concrete one."""
    if settings.llm_provider == "anthropic":
        from .providers.anthropic import AnthropicProvider

        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
    from .providers.fake import FakeProvider

    return FakeProvider()


__all__ = ["LLMError", "LLMProvider", "build_provider"]
