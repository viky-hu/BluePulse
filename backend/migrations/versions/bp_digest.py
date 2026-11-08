"""Bind story digests to their currently public report evidence."""
from alembic import op
import sqlalchemy as sa

revision = "bp_digest"
down_revision = "bp_editions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("story_digests",
        sa.Column("story_id", sa.String(36), sa.ForeignKey("stories.id"), primary_key=True),
        sa.Column("input_hash", sa.String(64), primary_key=True),
        sa.Column("digest", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("story_digests")
