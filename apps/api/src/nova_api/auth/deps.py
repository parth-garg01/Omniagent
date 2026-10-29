import hmac

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from .security import has_permission, lookup_session

COOKIE = "nova_session"
CSRF_COOKIE = "nova_csrf"
SAFE = {"GET", "HEAD", "OPTIONS"}


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    raw = request.cookies.get(COOKIE)
    sess = lookup_session(db, raw) if raw else None
    if sess is None:
        raise HTTPException(401, "Not authenticated")
    if request.method not in SAFE:
        sent = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(sent, sess.csrf_token):
            raise HTTPException(403, "CSRF token missing or invalid")
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "Not authenticated")
    request.state.session = sess
    return user


def require(permission: str):
    def dep(user: User = Depends(current_user)) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(403, "Forbidden")
        return user

    return dep
