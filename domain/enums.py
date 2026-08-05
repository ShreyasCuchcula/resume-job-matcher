"""Shared type-level enums (SPECIFICATION.md Section 5).

Modeled as `Literal` aliases rather than `enum.Enum` so they serialize
as plain strings in pydantic models, JSON, and SQLAlchemy columns
without an extra conversion step.
"""

from __future__ import annotations

from typing import Literal

RequirementType = Literal["skill", "education", "certification", "license"]

EvidenceSection = Literal[
    "skills",
    "experience",
    "project",
    "research",
    "summary",
    "education",
    "certification",
]

RunStatus = Literal["active", "invalidated"]

FileStatus = Literal[
    "accepted",
    "duplicate",
    "unsupported",
    "corrupt",
    "probable_scan",
    "parsed_with_warnings",
    "failed",
]

MissingItemStatus = Literal["not_identified", "unclear", "pending_credential"]

EmploymentSectionType = Literal["employment", "project", "research"]
