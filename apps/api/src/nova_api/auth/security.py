import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AuthSession, User

_hasher = PasswordHasher()  # Argon2id by default

# Permissions per role. Default-deny: anything absent is refused.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "user": {"chat", "docs:own", "tool:read", "tool:write"},
    "admin": {"chat", "docs:own", "docs:all", "tool:read", "tool:write", "admin", "eval:read"},
    "evaluator": {"eval:read"},
}


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def hash_password(pw: str) -> str:
    return _hasher.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, pw)
    except (VerificationError, InvalidHashError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> tuple[str, str]:
    """Returns (raw_token, csrf_token). Only the token hash is stored."""
    raw = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    expires = datetime.now(UTC) + timedelta(hours=get_settings().session_ttl_hours)
    db.add(AuthSession(user_id=user.id, hashed_token=hash_token(raw), csrf_token=csrf, expires_at=expires))
    db.commit()
    return raw, csrf


def lookup_session(db: Session, raw: str) -> AuthSession | None:
    s = db.scalar(select(AuthSession).where(AuthSession.hashed_token == hash_token(raw)))
    if s is None or s.revoked_at is not None:
        return None
    exp = s.expires_at if s.expires_at.tzinfo else s.expires_at.replace(tzinfo=UTC)
    if exp <= datetime.now(UTC):
        return None
    return s


class LoginThrottle:
    """In-memory sliding window keyed by email+ip. Single-process demo limiter."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        s = get_settings()
        q = self._hits[key]
        while q and q[0] < time.monotonic() - s.login_window_seconds:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= get_settings().login_max_attempts

    def record_failure(self, key: str) -> None:
        self._prune(key).append(time.monotonic())

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)


throttle = LoginThrottle()
