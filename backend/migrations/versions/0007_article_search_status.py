"""Index article text on SQLite and persist translation outcomes."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_article_search_status"
down_revision: Union[str, None] = "0006_ingestion_lease"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("translation_status", sa.String(length=32), nullable=True))
    if op.get_bind().dialect.name != "sqlite":
        return
    # Trigrams match Chinese substrings without requiring a third-party segmenter.
    op.execute("""
        CREATE VIRTUAL TABLE article_search USING fts5(
            source_title, zh_title, source_body, zh_body, zh_summary,
            content='articles', content_rowid='rowid', tokenize='trigram'
        )
    """)
    op.execute("""
        CREATE TRIGGER article_search_insert AFTER INSERT ON articles BEGIN
            INSERT INTO article_search(rowid, source_title, zh_title, source_body, zh_body, zh_summary)
            VALUES (new.rowid, new.source_title, new.zh_title, new.source_body, new.zh_body, new.zh_summary);
        END
    """)
    op.execute("""
        CREATE TRIGGER article_search_delete AFTER DELETE ON articles BEGIN
            INSERT INTO article_search(article_search, rowid, source_title, zh_title, source_body, zh_body, zh_summary)
            VALUES ('delete', old.rowid, old.source_title, old.zh_title, old.source_body, old.zh_body, old.zh_summary);
        END
    """)
    op.execute("""
        CREATE TRIGGER article_search_update AFTER UPDATE ON articles BEGIN
            INSERT INTO article_search(article_search, rowid, source_title, zh_title, source_body, zh_body, zh_summary)
            VALUES ('delete', old.rowid, old.source_title, old.zh_title, old.source_body, old.zh_body, old.zh_summary);
            INSERT INTO article_search(rowid, source_title, zh_title, source_body, zh_body, zh_summary)
            VALUES (new.rowid, new.source_title, new.zh_title, new.source_body, new.zh_body, new.zh_summary);
        END
    """)
    op.execute("INSERT INTO article_search(article_search) VALUES ('rebuild')")


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER article_search_update")
        op.execute("DROP TRIGGER article_search_delete")
        op.execute("DROP TRIGGER article_search_insert")
        op.execute("DROP TABLE article_search")
    op.drop_column("articles", "translation_status")
