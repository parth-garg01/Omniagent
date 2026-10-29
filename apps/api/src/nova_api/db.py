from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url or url == "sqlite://":
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True)


_engine = None
_factory = None


def init_db(url: str | None = None) -> None:
    """(Re)bind the global engine; creates tables. Alembic is the production path."""
    global _engine, _factory
    from . import models  # noqa: F401  (register tables)

    _engine = make_engine(url or get_settings().database_url)
    _factory = sessionmaker(_engine, expire_on_commit=False)
    Base.metadata.create_all(_engine)


def get_db() -> Iterator[Session]:
    if _factory is None:
        init_db()
    db = _factory()
    try:
        yield db
    finally:
        db.close()
