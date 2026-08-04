"""Declarative base and portable column types (SPECIFICATION.md
Section 3.3 / 6): UUIDs as CHAR(36) on SQLite / native UUID on
Postgres, JSON as JSON on SQLite / JSONB on Postgres. One model file
targets both engines; only `DATABASE_URL` changes.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CHAR, JSON, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class GUID(TypeDecorator):
    """Platform-independent UUID: native UUID on Postgres, CHAR(36) on
    everything else (SQLite in dev/test)."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value if isinstance(value, uuid.UUID) else uuid.UUID(str(value)))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def portable_json():
    """JSON on SQLite, JSONB on Postgres, via the same column definition."""
    return JSON().with_variant(JSONB(), "postgresql")
