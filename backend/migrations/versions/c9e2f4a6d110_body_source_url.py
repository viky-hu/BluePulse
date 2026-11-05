"""Keep the exact text source URL for attachment-derived bodies.

Revision ID: c9e2f4a6d110
Revises: b2f7e61c904a
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9e2f4a6d110"
down_revision: Union[str, None] = "b2f7e61c904a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("materials", sa.Column("body_source_url", sa.Text(), nullable=True))
    op.add_column("material_revisions", sa.Column("body_source_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("material_revisions", "body_source_url")
    op.drop_column("materials", "body_source_url")
