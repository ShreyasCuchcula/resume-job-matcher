"""Engine and session factory built from `config/settings.py` (Section
3.3): one `DATABASE_URL` env var switches between SQLite (dev/test)
and PostgreSQL (production) with no code changes.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import get_app_config


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = get_app_config().settings.database_url
    connect_args = (
        {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    return create_engine(database_url, connect_args=connect_args, future=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(), autoflush=False, expire_on_commit=False, future=True
    )


def get_session() -> Session:
    """One session per call; caller is responsible for closing it
    (typically via a `with get_session() as session:` block)."""
    return get_sessionmaker()()
