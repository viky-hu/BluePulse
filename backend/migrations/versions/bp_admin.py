"""Persist admin sessions, audit, settings, rate limits and private feedback."""

from alembic import op
import sqlalchemy as sa

revision = "bp_admin"
down_revision = "bp_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("binding", sa.String(64), nullable=False),
        sa.Column("csrf", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"])
    op.create_table(
        "admin_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("subject", sa.String(120)),
        sa.Column("reason", sa.Text()),
        sa.Column("changes", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("action", "subject", "created_at"):
        op.create_index(f"ix_admin_audit_{column}", "admin_audit", [column])
    op.create_table(
        "admin_rate_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_rate_events_created_at", "admin_rate_events", ["created_at"])
    op.create_index("ix_admin_rate_events_scope_created", "admin_rate_events", ["scope", "created_at"])
    op.create_table(
        "admin_content_overrides",
        sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id"), primary_key=True),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "admin_model_settings",
        sa.Column("capability", sa.String(32), primary_key=True),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "admin_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_evaluations_created_at", "admin_evaluations", ["created_at"])
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content", sa.Text()),
        sa.Column("email", sa.String(200)),
        sa.Column("page_url", sa.String(500)),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("erased_at", sa.DateTime(timezone=True)),
    )
    for column in ("source_hash", "status", "created_at"):
        op.create_index(f"ix_feedback_{column}", "feedback", [column])
    op.create_table(
        "feedback_screenshots",
        sa.Column("feedback_id", sa.Integer(), sa.ForeignKey("feedback.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("mime", sa.String(16), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
    )
    op.create_table(
        "feedback_bans",
        sa.Column("source_hash", sa.String(64), primary_key=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for name in ("feedback_bans", "feedback_screenshots", "feedback", "admin_evaluations",
                 "admin_model_settings", "admin_content_overrides", "admin_rate_events", "admin_audit",
                 "admin_sessions"):
        op.drop_table(name)
