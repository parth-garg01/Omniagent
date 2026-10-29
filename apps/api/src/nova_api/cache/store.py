"""Response cache primitives. Disabled by default and NOT wired into the chat path.

Keys bind every input that can change or restrict an answer, so a hit can never cross a
user/permission boundary or survive a model, prompt or index change.
"""
import hashlib
import json
import time
from typing import Protocol

PROMPT_VERSION = "1"


def cache_key(*, user_id: str, role: str, model: str, prompt_version: str, retrieval_version: str,
              message: str) -> str:
    raw = json.dumps([user_id, role, model, prompt_version, retrieval_version, message])
    return hashlib.sha256(raw.encode()).hexdigest()


def retrieval_version(docs: list[tuple[str, str, int]]) -> str:
    """Fingerprint of the readable index state: (document_id, content_hash, version) tuples."""
    return hashlib.sha256(json.dumps(sorted(docs)).encode()).hexdigest()


class Cache(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...

    def clear(self) -> None: ...


class InMemoryCache:
    def __init__(self, ttl_seconds: int = 300, max_entries: int = 256, enabled: bool = False):
        self.enabled, self._ttl, self._max = enabled, ttl_seconds, max_entries
        self._data: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> str | None:
        if not self.enabled:
            return None
        hit = self._data.get(key)
        if hit is None or hit[0] < time.monotonic():
            self._data.pop(key, None)
            return None
        return hit[1]

    def set(self, key: str, value: str) -> None:
        if not self.enabled:
            return
        if len(self._data) >= self._max:
            self._data.pop(next(iter(self._data)))
        self._data[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        self._data.clear()
