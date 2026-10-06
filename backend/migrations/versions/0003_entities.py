"""Add curated entity catalog and evidenced article links."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_entities"
down_revision: Union[str, None] = "0002_articles_and_ingestion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("region", sa.String(length=16), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_entities_slug", "entities", ["slug"])
    op.create_index("ix_entities_entity_type", "entities", ["entity_type"])
    op.create_table(
        "article_entities",
        sa.Column("article_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_field", sa.String(length=32), nullable=False),
        sa.Column("matched_alias", sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("article_id", "entity_id"),
    )
    op.create_index("ix_article_entities_entity_id", "article_entities", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_article_entities_entity_id", table_name="article_entities")
    op.drop_table("article_entities")
    op.drop_index("ix_entities_entity_type", table_name="entities")
    op.drop_index("ix_entities_slug", table_name="entities")
    op.drop_table("entities")
