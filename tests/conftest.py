"""Shared pytest fixtures (SPECIFICATION.md Section 4:
`tests/conftest.py # fixtures: profiles, taxonomies, in-memory DB`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from db import models  # noqa: F401  (import registers every table on Base.metadata)
from db.base import Base

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_RESUMES_DIR = REPO_ROOT / "sample_data" / "synthetic_resumes"


@pytest.fixture
def db_session():
    """A fresh, isolated in-memory SQLite DB with the full schema
    applied, torn down after each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def sample_resumes_dir() -> Path:
    return SAMPLE_RESUMES_DIR


@pytest.fixture
def upload_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    return directory
