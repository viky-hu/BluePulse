"""Cache provider vectors by effective configuration and exact text."""
from alembic import op
import sqlalchemy as sa

revision = "bp_embeddings"
down_revision = "bp_digest"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("embedding_vectors",
        sa.Column("config_hash", sa.String(64), primary_key=True),
        sa.Column("text_hash", sa.String(64), primary_key=True),
        sa.Column("vector", sa.JSON(), nullable=False))


def downgrade():
    op.drop_table("embedding_vectors")
