"""Track high-confidence same-copy links and sort by trustworthy source date.

Revision ID: b2f7e61c904a
Revises: a61d8b7c2e42
"""
from __future__ import annotations

from datetime import UTC
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2f7e61c904a"
down_revision: Union[str, None] = "a61d8b7c2e42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("materials") as batch:
        batch.add_column(sa.Column("title_key", sa.String(64), nullable=True))
        batch.add_column(sa.Column("published_sort_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("duplicate_of_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("duplicate_reason", sa.String(60), nullable=True))
        batch.create_index("ix_materials_title_key", ["title_key"])
        batch.create_index("ix_materials_duplicate_of_id", ["duplicate_of_id"])
        batch.create_foreign_key("fk_materials_duplicate_of_id", "materials", ["duplicate_of_id"], ["id"])

    # Existing materials gain date-only ordering and duplicate links without a refetch.
    from bluepulse_backend.material_identity import publication_clock, title_key

    connection = op.get_bind()
    # Reflect the schema at this revision: importing the latest ORM model would
    # query columns introduced by later revisions before those columns exist.
    materials = sa.Table("materials", sa.MetaData(), autoload_with=connection)
    for material in connection.execute(sa.select(materials)).mappings():
        seen = material["first_seen_at"]
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=UTC)
        exact = material["published_at"]
        if exact is not None and exact.tzinfo is None:
            exact = exact.replace(tzinfo=UTC)
        timeline, sort_at, safe_exact = publication_clock(
            exact, material["published_date"], seen)
        connection.execute(materials.update().where(materials.c.id == material["id"]).values(
            title_key=title_key(material["source_title"]), timeline_kind=timeline,
            published_sort_at=sort_at, published_at=safe_exact,
        ))


def downgrade() -> None:
    with op.batch_alter_table("materials") as batch:
        batch.drop_constraint("fk_materials_duplicate_of_id", type_="foreignkey")
        batch.drop_index("ix_materials_duplicate_of_id")
        batch.drop_index("ix_materials_title_key")
        batch.drop_column("duplicate_reason")
        batch.drop_column("duplicate_of_id")
        batch.drop_column("published_sort_at")
        batch.drop_column("title_key")
