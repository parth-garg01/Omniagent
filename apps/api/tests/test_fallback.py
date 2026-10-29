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
