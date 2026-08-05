"""resumes parsed_json and parser_version nullable

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-04 22:58:59.883193

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table so this also works on SQLite, which has no
    # ALTER COLUMN and requires a table rebuild for a nullability change;
    # on Postgres this compiles straight to a plain ALTER COLUMN.
    with op.batch_alter_table("resumes") as batch_op:
        batch_op.alter_column(
            "parsed_json", existing_type=sa.JSON(), nullable=True
        )
        batch_op.alter_column(
            "parser_version", existing_type=sa.VARCHAR(length=50), nullable=True
        )


def downgrade() -> None:
    with op.batch_alter_table("resumes") as batch_op:
        batch_op.alter_column(
            "parser_version", existing_type=sa.VARCHAR(length=50), nullable=False
        )
        batch_op.alter_column(
            "parsed_json", existing_type=sa.JSON(), nullable=False
        )
