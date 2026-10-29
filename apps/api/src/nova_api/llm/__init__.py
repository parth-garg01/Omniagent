from ..config import Settings
from .interfaces import LLMError, LLMProvider


def _make(name: str, settings: Settings) -> LLMProvider:
    if name == "grok":
        from .providers.grok import GrokProvider

        return GrokProvider(settings.grok_api_key, settings.grok_model, settings.grok_base_url)
    from .providers.fake import FakeProvider

    return FakeProvider()


def build_provider(settings: Settings) -> LLMProvider:
    """Select a provider by configuration; the orchestrator never imports a concrete one."""
    primary = _make(settings.llm_provider, settings)
    if settings.llm_fallback_provider and settings.llm_fallback_provider != settings.llm_provider:
        from ..routing.policy import select_provider
        from .fallback import FallbackProvider

        chain = [primary, _make(settings.llm_fallback_provider, settings)]
        select_provider(chain, needs_tools=False)  # validates the chain is usable
        return FallbackProvider(chain)
    return primary


__all__ = ["LLMError", "LLMProvider", "build_provider"]
