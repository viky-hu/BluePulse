"""Record bounded source adapter stage counts.

Revision ID: fa8b4ca774e1
Revises: 7d4cc894292d
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "fa8b4ca774e1"
down_revision: Union[str, None] = "7d4cc894292d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("source_runs", sa.Column("fetch_metrics", sa.JSON(),
                                           server_default="{}", nullable=False))


def downgrade() -> None:
    op.drop_column("source_runs", "fetch_metrics")
