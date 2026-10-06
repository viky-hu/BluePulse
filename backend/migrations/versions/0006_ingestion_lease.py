"""Add a global ingestion lease and request idempotency keys."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_ingestion_lease"
down_revision: Union[str, None] = "0005_editorial_override"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ingestion_runs", sa.Column("source_slug", sa.String(length=100), nullable=True))
    op.add_column("ingestion_runs", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.create_index("uq_ingestion_runs_idempotency_key", "ingestion_runs", ["idempotency_key"], unique=True)
    op.create_table(
        "ingestion_lease",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_token", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("INSERT INTO ingestion_lease (id) VALUES (1)")


def downgrade() -> None:
    op.drop_table("ingestion_lease")
    op.drop_index("uq_ingestion_runs_idempotency_key", table_name="ingestion_runs")
    op.drop_column("ingestion_runs", "idempotency_key")
    op.drop_column("ingestion_runs", "source_slug")
