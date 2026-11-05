"""Track calibrated source threshold and dual-score completion.

Revision ID: e31c8a41d2f0
Revises: c9e2f4a6d110
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e31c8a41d2f0"
down_revision: Union[str, None] = "c9e2f4a6d110"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("selection_threshold", sa.Integer(), nullable=True))
    op.add_column("materials", sa.Column("selection_status", sa.String(length=32),
                                         server_default="pending", nullable=False))
    # Historical one-pass candidate decisions remain in AnalysisAttempt receipts,
    # but cannot qualify a material under the new two-receipt selection gate.
    op.execute("UPDATE materials SET featured_candidate = 0, importance_score = 0")
    # Backfill cross-source identity only after all columns used by the current
    # Material ORM exist. c9e2f4a6d110 may run against an older populated DB.
    from sqlalchemy.orm import Session
    from bluepulse_backend.material_identity import reconcile_title
    from bluepulse_backend.models import Material

    with Session(op.get_bind()) as session:
        keys = session.scalars(sa.select(Material.title_key).where(
            Material.title_key.is_not(None)).distinct()).all()
        for key in sorted(keys):
            reconcile_title(session, key)
        session.flush()


def downgrade() -> None:
    op.drop_column("materials", "selection_status")
    op.drop_column("sources", "selection_threshold")
