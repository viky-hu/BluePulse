"""Persist listing progress, source clocks and the detail gate."""
from alembic import op
import sqlalchemy as sa

revision = "bp_collection"
down_revision = "bp_embeddings"
branch_labels = None
depends_on = None


def columns():
    return {
        "sources": [
            sa.Column("collection_initialized_at", sa.DateTime(timezone=True)),
            sa.Column("next_fetch_at", sa.DateTime(timezone=True)),
            sa.Column("collection_cursor", sa.JSON()),
            sa.Column("collection_failures", sa.Integer(), nullable=False, server_default="0"),
        ],
        "materials": [
            sa.Column("collection_state", sa.String(20)),
            sa.Column("listing_hash", sa.String(64)),
            sa.Column("backfill_reason", sa.String(30)),
        ],
    }


def upgrade():
    for table, additions in columns().items():
        for column in additions:
            op.add_column(table, column)
    # The new scheduler can offer each existing source a bounded first import.
    # Explicit manual/diagnostic batches and pending editorial work remain resumable.
    op.execute("""UPDATE work_items SET status = 'done', error = 'collection_schedule_upgraded',
        token = NULL, expires_at = NULL
        WHERE kind = 'collect' AND status IN ('pending','running')
        AND json_extract(payload, '$.run_key') IS NULL""")


def downgrade():
    for table, additions in columns().items():
        with op.batch_alter_table(table) as batch:
            for column in additions:
                batch.drop_column(column.name)
