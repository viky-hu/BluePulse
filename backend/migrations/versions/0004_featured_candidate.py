"""Separate public relevance from homepage selection."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_featured_candidate"
down_revision: Union[str, None] = "0003_entities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("featured_candidate", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("articles", sa.Column("featured_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("articles", "featured_reason")
    op.drop_column("articles", "featured_candidate")
