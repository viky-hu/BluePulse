"""Persist conservative fact groups and dormant auto-publication jobs.

Revision ID: f6b1c732d900
Revises: e31c8a41d2f0
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6b1c732d900"
down_revision: Union[str, None] = "e31c8a41d2f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fact_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("identity_key", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("anchor_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "fact_reports",
        sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id"), primary_key=True),
        sa.Column("fact_id", sa.String(36), sa.ForeignKey("fact_groups.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("relation", sa.String(20), nullable=False),
        sa.Column("grouped_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fact_reports_fact_id", "fact_reports", ["fact_id"])
    op.create_table(
        "auto_publication_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source_slugs", sa.JSON(), nullable=False),
        sa.Column("max_items", sa.Integer(), nullable=False),
        sa.Column("max_model_calls", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("report", sa.JSON()),
    )
    op.create_index("ix_auto_publication_jobs_status", "auto_publication_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_auto_publication_jobs_status", table_name="auto_publication_jobs")
    op.drop_table("auto_publication_jobs")
    op.drop_index("ix_fact_reports_fact_id", table_name="fact_reports")
    op.drop_table("fact_reports")
    op.drop_table("fact_groups")
