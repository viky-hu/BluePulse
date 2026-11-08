"""Durable work, paid receipts and revision-bound editorial state."""
from alembic import op
import sqlalchemy as sa

revision = "bp_core"
down_revision = "f6b1c732d900"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("work_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("identity", sa.String(200), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token", sa.String(36)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(100)),
        sa.Column("result", sa.JSON()),
        sa.UniqueConstraint("kind", "identity"))
    op.create_index("ix_work_due", "work_items", ["status", "due_at"])
    op.create_table("paid_receipts",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("subject", sa.String(120), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latest_attempt", sa.Integer(), nullable=False),
        sa.Column("auto_released", sa.Boolean(), nullable=False))
    op.create_index("ix_receipt_subject_step", "paid_receipts", ["subject", "purpose", "status"])
    op.create_table("paid_attempts",
        sa.Column("receipt_key", sa.String(64), sa.ForeignKey("paid_receipts.key"), primary_key=True),
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column("service", sa.String(100), nullable=False),
        sa.Column("run_key", sa.String(120)),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("response", sa.JSON()),
        sa.Column("error", sa.String(100)),
        sa.Column("release_note", sa.Text()),
        sa.Column("billed", sa.Boolean()))
    op.create_index("ix_paid_attempts_budget", "paid_attempts", ["service", "sent_at"])
    op.create_index("ix_paid_attempts_run_key", "paid_attempts", ["run_key"])
    op.create_table("stories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("merged_into_id", sa.String(36), sa.ForeignKey("stories.id")))
    with op.batch_alter_table("fact_groups") as batch:
        batch.add_column(sa.Column("story_id", sa.String(36)))
        batch.add_column(sa.Column("subject", sa.Text()))
        batch.create_foreign_key("fk_fact_groups_story", "stories", ["story_id"], ["id"])
        batch.create_index("ix_fact_groups_story_id", ["story_id"])
    op.add_column("fact_reports", sa.Column("manual", sa.Boolean(), server_default="0", nullable=False))
    op.create_table("story_signals",
        sa.Column("story_id", sa.String(36), sa.ForeignKey("stories.id"), primary_key=True),
        sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("participant_key", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False))
    op.create_index("ix_story_signals_material_id", "story_signals", ["material_id"])
    op.create_index("ix_story_signals_observed_at", "story_signals", ["observed_at"])
    op.create_table("fact_mentions",
        sa.Column("fact_id", sa.String(36), sa.ForeignKey("fact_groups.id"), primary_key=True),
        sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False))
    op.create_index("ix_fact_mentions_material_id", "fact_mentions", ["material_id"])
    for table, columns in _columns().items():
        for column in columns:
            op.add_column(table, column)


def _columns():
    return {
        "sources": [
            sa.Column("tier", sa.String(10)), sa.Column("participant_key", sa.String(120)),
            sa.Column("owner_entity", sa.String(120)), sa.Column("publisher_role", sa.String(20)),
            sa.Column("participation_mode", sa.String(20), nullable=False, server_default="editorial"),
            sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="60"),
            sa.Column("media_allowed", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("syndicate_full_text_allowed", sa.Boolean(), nullable=False, server_default="0"),
        ],
        "materials": [
            sa.Column("source_media", sa.JSON()), sa.Column("editorial_revision", sa.Integer()),
            sa.Column("editorial_scope", sa.String(16)), sa.Column("editorial_data", sa.JSON()),
            sa.Column("judged_at", sa.DateTime(timezone=True)), sa.Column("translation_revision", sa.Integer()),
            sa.Column("grouping_value", sa.Boolean()), sa.Column("selected_at", sa.DateTime(timezone=True)),
            sa.Column("visible_after", sa.DateTime(timezone=True)),
            sa.Column("standalone", sa.Boolean(), nullable=False, server_default="0"),
        ],
        "material_revisions": [sa.Column("source_media", sa.JSON())],
    }


def downgrade():
    for table, columns in _columns().items():
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.drop_column(column.name)
    op.drop_table("fact_mentions")
    op.drop_table("story_signals")
    op.drop_column("fact_reports", "manual")
    with op.batch_alter_table("fact_groups") as batch:
        batch.drop_index("ix_fact_groups_story_id")
        batch.drop_constraint("fk_fact_groups_story", type_="foreignkey")
        batch.drop_column("story_id")
        batch.drop_column("subject")
    for table in ("stories", "paid_attempts", "paid_receipts", "work_items"):
        op.drop_table(table)
