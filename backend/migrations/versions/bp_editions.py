"""Persist hourly story heat, hot rankings, and independently frozen daily issues."""

from alembic import op
import sqlalchemy as sa


revision = "bp_editions"
down_revision = "bp_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hot_rankings",
        sa.Column("computed_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("rule_version", sa.String(48), nullable=False),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
    )
    op.create_table(
        "story_heat_hourly",
        sa.Column("story_id", sa.String(36), sa.ForeignKey("stories.id"), primary_key=True),
        sa.Column("hour", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("heat", sa.Float(), nullable=False),
        sa.Column("participants", sa.Integer(), nullable=False),
        sa.Column("cohort", sa.Integer(), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_story_heat_hourly_hour", "story_heat_hourly", ["hour"])
    op.create_table(
        "daily_issues",
        sa.Column("key", sa.String(10), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
    )
    op.create_table(
        "daily_issue_revisions",
        sa.Column("issue_key", sa.String(10), sa.ForeignKey("daily_issues.key"), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("daily_issue_revisions")
    op.drop_table("daily_issues")
    op.drop_index("ix_story_heat_hourly_hour", table_name="story_heat_hourly")
    op.drop_table("story_heat_hourly")
    op.drop_table("hot_rankings")
