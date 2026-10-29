import contextvars
import json
import logging
import re
import time
from contextlib import contextmanager

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

_SECRET_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|password|secret|token|authorization)(\"?\s*[:=]\s*\"?)([^\s\",}]+)"),
     r"\1\2[REDACTED]"),
    (re.compile(r"sk-[A-Za-z0-9_-]{8,}"), "[REDACTED]"),
]


def redact(text: str) -> str:
    for pat, repl in _SECRET_PATTERNS:
        text = pat.sub(repl, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
                   "logger": record.name, "msg": redact(record.getMessage()),
                   "request_id": request_id_var.get()}
        extra = getattr(record, "fields", None)
        if extra:
            payload.update({k: redact(str(v)) if isinstance(v, str) else v for k, v in extra.items()})
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload)


def configure_logging() -> None:
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    root.handlers = [h]
    root.setLevel(logging.INFO)


@contextmanager
def span(name: str, **fields):
    """Lightweight trace span: logs duration + attributes (never payloads) under the request id."""
    log = logging.getLogger("nova.trace")
    t0 = time.monotonic()
    outcome = "ok"
    try:
        yield
    except Exception:
        outcome = "error"
        raise
    finally:
        log.info("span", extra={"fields": {"span": name, "outcome": outcome,
                                           "duration_ms": int((time.monotonic() - t0) * 1000), **fields}})
