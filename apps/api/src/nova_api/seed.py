"""Seed synthetic demo data. Idempotent. Run: python -m nova_api.seed"""
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth.security import hash_password
from .config import get_settings
from .models import Document, MockOrder, User
from .rag import service as rag_service

DEMO_PASSWORD = "demo-password-1"  # synthetic, local-only
USERS = [("alice@example.com", "user"), ("bob@example.com", "user"),
         ("admin@example.com", "admin"), ("eval@example.com", "evaluator")]
ORDERS = [("ORD-1001", "alice@example.com", "Wireless Headphones", 8999, "delivered"),
          ("ORD-1002", "alice@example.com", "Phone Case", 1999, "shipped"),
          ("ORD-2001", "bob@example.com", "Desk Lamp", 4500, "delivered")]


def find_docs_dir() -> Path | None:
    for p in Path(__file__).resolve().parents:
        if (p / "data" / "seed" / "sample-documents").is_dir():
            return p / "data" / "seed" / "sample-documents"
    return None


def seed(db: Session) -> None:
    password = get_settings().demo_password or DEMO_PASSWORD
    by_email = {}
    for email, role in USERS:
        u = db.scalar(select(User).where(User.email == email))
        if u is None:
            u = User(email=email, password_hash=hash_password(password), role=role)
            db.add(u)
            db.commit()
        by_email[email] = u
    for oid, email, item, amount, status in ORDERS:
        if db.get(MockOrder, oid) is None:
            db.add(MockOrder(id=oid, user_id=by_email[email].id, item=item,
                             amount_cents=amount, status=status))
    db.commit()
    docs_dir = find_docs_dir()
    if docs_dir:
        for f in sorted(docs_dir.glob("*.md")):
            exists = db.scalar(select(Document).where(Document.filename == f.name,
                                                      Document.access_policy == "shared"))
            if not exists:
                rag_service.ingest(db, by_email["admin@example.com"], f.name, f.read_bytes(), shared=True)


if __name__ == "__main__":
    from . import db as dbm

    dbm.init_db()
    with dbm.new_session() as s:
        seed(s)
    custom = bool(get_settings().demo_password)
    print("Seeded demo users (custom password from NOVA_DEMO_PASSWORD)," if custom
          else f"Seeded demo users (password: {DEMO_PASSWORD}),", "orders and shared documents.")
