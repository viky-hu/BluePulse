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
    # Complete the identity backfill after the current ORM schema is available.
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
    op.drop_column("material_revisions", "body_source_url")
    op.drop_column("materials", "body_source_url")
