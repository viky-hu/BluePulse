"""Preserve publication dates without inventing a time of day.

Revision ID: a61d8b7c2e42
Revises: fa8b4ca774e1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a61d8b7c2e42"
down_revision: Union[str, None] = "fa8b4ca774e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("materials", sa.Column("published_date", sa.Date(), nullable=True))
    op.add_column("material_revisions", sa.Column("published_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("material_revisions", "published_date")
    op.drop_column("materials", "published_date")
