import pytest

from nova_api.llm.interfaces import LLMError
from nova_api.routing.policy import select_provider


class P:
    def __init__(self, name, tools):
        self.name, self.model, self.supports_tools = name, name, tools


def test_first_capable_provider_wins():
    a, b = P("a", False), P("b", True)
    assert select_provider([a, b], needs_tools=False) is a
    assert select_provider([a, b], needs_tools=True) is b


def test_no_capable_provider_raises():
    with pytest.raises(LLMError):
        select_provider([P("a", False)], needs_tools=True)
