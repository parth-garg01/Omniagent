import pytest

from nova_api.llm.fallback import FallbackProvider
from nova_api.llm.interfaces import LLMError, LLMMessage, LLMRequest, TextDelta

REQ = LLMRequest("s", [LLMMessage("user", "hi")])


class Fails:
    name = model = "fails"
    supports_tools = True

    def __init__(self, code, after_output=False):
        self.code, self.after = code, after_output

    def stream(self, req):
        if self.after:
            yield TextDelta("partial")
        raise LLMError(self.code, "x")


class Works:
    name = model = "works"
    supports_tools = True

    def stream(self, req):
        yield TextDelta("ok")


def collect(p):
    return "".join(e.text for e in p.stream(REQ) if isinstance(e, TextDelta))


def test_falls_back_on_retryable_error():
    assert collect(FallbackProvider([Fails("unavailable"), Works()])) == "ok"


def test_no_fallback_on_auth_error():
    with pytest.raises(LLMError) as e:
        collect(FallbackProvider([Fails("auth"), Works()]))
    assert e.value.code == "auth"


def test_no_fallback_after_partial_output():
    with pytest.raises(LLMError):
        collect(FallbackProvider([Fails("timeout", after_output=True), Works()]))


def test_all_fail_raises_last():
    with pytest.raises(LLMError) as e:
        collect(FallbackProvider([Fails("timeout"), Fails("rate_limit")]))
    assert e.value.code == "rate_limit"


def test_build_provider_wraps_when_fallback_configured():
    from nova_api.config import Settings
    from nova_api.llm import build_provider

    assert build_provider(Settings(llm_provider="fake")).name == "fake"
    p = build_provider(Settings(llm_provider="grok", grok_api_key="k",
                                llm_fallback_provider="fake"))
    assert p.name == "grok+fake"


def test_unknown_fallback_name_rejected():
    from nova_api.config import Settings

    with pytest.raises(ValueError):
        Settings(llm_fallback_provider="nope")
