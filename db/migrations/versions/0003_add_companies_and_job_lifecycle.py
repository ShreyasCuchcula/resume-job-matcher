"""add companies table and job lifecycle fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-07 00:00:00.000000

Post-Stage-7 addendum (pre-Stage-9 infrastructure, not part of the
original 10-stage plan - documented as a deviation in
SPECIFICATION.md Section 6.3 rather than silently added). Adds a
`companies` table and three lifecycle columns on `jobs`
(`company_id`, `status`, `expires_at`). `company_id` is nullable at
the DB layer (existing/pre-migration job rows have none, and the
recruiter backfills them later per the confirmation-page note); the
application layer (services/job_service.py) is what requires a
`company_id` on every *new* job creation.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import db.base

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", db.base.GUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("industry", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_companies_name"),
    )

    # batch_alter_table so this also works on SQLite, which cannot add
    # a foreign-key/check constraint to an existing table without a
    # rebuild; on Postgres it compiles to plain ALTER TABLE statements
    # (same pattern already established by migration 0002).
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("company_id", db.base.GUID(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="open",
            )
        )
        batch_op.add_column(
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_jobs_status", "status IN ('open', 'closed', 'archived')"
        )
        batch_op.create_foreign_key(
            "fk_jobs_company_id_companies",
            "companies",
            ["company_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_jobs_company_id", ["company_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_index("ix_jobs_company_id")
        batch_op.drop_constraint("fk_jobs_company_id_companies", type_="foreignkey")
        batch_op.drop_constraint("ck_jobs_status", type_="check")
        batch_op.drop_column("expires_at")
        batch_op.drop_column("status")
        batch_op.drop_column("company_id")

    op.drop_table("companies")
