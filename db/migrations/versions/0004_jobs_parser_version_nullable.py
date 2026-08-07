"""jobs parser_version nullable

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-07 00:00:00.000000

Post-Stage-7 addendum (pre-Stage-9 infrastructure, not part of the
original 10-stage plan - SPECIFICATION.md Section 6.3). Mirrors
migration 0002's exact rationale, applied to `jobs` instead of
`resumes`: services/job_service.py's create_job() persists a Job row
before parse_job_description() has run (Section 15.2 Page 1's
"Analyze Description" is a separate, later step), so `parser_version`
has no real value yet at creation time and must not be forced to a
placeholder string.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.alter_column(
            "parser_version", existing_type=sa.VARCHAR(length=50), nullable=True
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.alter_column(
            "parser_version", existing_type=sa.VARCHAR(length=50), nullable=False
        )
