"""Keep confirmed editorial decisions separate from model processing state."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_editorial_override"
down_revision: Union[str, None] = "0004_featured_candidate"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("editorial_relevance", sa.String(length=16), nullable=True))
    op.add_column("articles", sa.Column("editorial_select", sa.String(length=16), nullable=True))
    op.add_column("articles", sa.Column("editorial_reason", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("editorial_case_id", sa.String(length=100), nullable=True))
    op.add_column("articles", sa.Column("editorial_applied_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("articles", "editorial_applied_at")
    op.drop_column("articles", "editorial_case_id")
    op.drop_column("articles", "editorial_reason")
    op.drop_column("articles", "editorial_select")
    op.drop_column("articles", "editorial_relevance")
