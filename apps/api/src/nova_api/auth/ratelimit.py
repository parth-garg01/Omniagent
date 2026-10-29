import time
from collections import defaultdict, deque

from fastapi import HTTPException

from ..config import get_settings


class RateLimiter:
    """In-process sliding window. Single-instance only; use a shared store when scaling out."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window: int) -> None:
        now = time.monotonic()
        q = self._hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "Rate limit exceeded, slow down",
                                headers={"Retry-After": str(max(1, int(window - (now - q[0]))))})
        q.append(now)

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter()


def limit_messages(user_id: str) -> None:
    s = get_settings()
    limiter.check(f"msg:{user_id}", s.rate_limit_messages, s.rate_limit_window_seconds)


def limit_uploads(user_id: str) -> None:
    s = get_settings()
    limiter.check(f"upload:{user_id}", s.rate_limit_uploads, s.rate_limit_window_seconds)
