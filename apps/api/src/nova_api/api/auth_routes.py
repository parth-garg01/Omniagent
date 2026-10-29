from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..auth.deps import COOKIE, CSRF_COOKIE, current_user
from ..auth.security import create_session, hash_password, throttle, verify_password
from ..config import get_settings
from ..db import get_db
from ..models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Verified against when the email is unknown so timing does not reveal account existence.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    # No password-policy length check here: policy applies when setting a password, not when
    # verifying one (and seeded demo passwords may be shorter than the registration minimum).
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str
    role: str


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: Credentials, db: Session = Depends(get_db)):
    if not get_settings().allow_registration:
        raise HTTPException(403, "Registration is disabled")
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    # Self-registration always yields the least-privileged role; role is never client-supplied.
    user = User(email=email, password_hash=hash_password(body.password), role="user")
    db.add(user)
    db.commit()
    audit(db, user.id, "register", "user", user.id, "ok")
    return user


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    key = f"{email}|{request.client.host if request.client else '-'}"
    if throttle.blocked(key):
        raise HTTPException(429, "Too many attempts, try again later")
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok or not user.is_active:
        throttle.record_failure(key)
        audit(db, user.id if user else None, "login", "user", None, "denied")
        raise HTTPException(401, "Invalid credentials")
    throttle.reset(key)
    raw, csrf = create_session(db, user)
    s = get_settings()
    age = s.session_ttl_hours * 3600
    response.set_cookie(COOKIE, raw, httponly=True, samesite="lax", secure=s.cookie_secure, max_age=age)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, samesite="lax", secure=s.cookie_secure, max_age=age)
    audit(db, user.id, "login", "user", user.id, "ok")
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    from datetime import UTC, datetime

    sess = request.state.session
    sess.revoked_at = datetime.now(UTC)
    db.add(sess)
    db.commit()
    response.delete_cookie(COOKIE)
    response.delete_cookie(CSRF_COOKIE)
    audit(db, user.id, "logout", "session", sess.id, "ok")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
