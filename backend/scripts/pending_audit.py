"""Read-only inventory of model-pending material before spending API calls."""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.db import create_database_engine
from bluepulse_backend.models import Article, Source


def audit() -> dict[str, object]:
    engine = create_database_engine()
    try:
        by_source: dict[str, Counter[str]] = defaultdict(Counter)
        totals: Counter[str] = Counter()
        with Session(engine) as session:
            rows = session.execute(
                select(Article, Source).join(Source).where(
                    Article.deleted_at.is_(None),
                    Article.processing_status.in_(("pending_model", "model_failed")),
                )
            )
            for article, source in rows:
                totals["pending"] += 1
                bucket = by_source[source.slug]
                bucket["pending"] += 1
                if article.editorial_relevance in {"irrelevant", "uncertain"}:
                    bucket["manual_withheld"] += 1
                    totals["manual_withheld"] += 1
                elif article.editorial_relevance in {"direct", "potential"}:
                    bucket["manual_relevant"] += 1
                    totals["manual_relevant"] += 1
                if article.source_body and len(article.source_body.strip()) >= 100:
                    bucket["body_or_abstract"] += 1
                    totals["body_or_abstract"] += 1
                else:
                    bucket["title_only_or_short"] += 1
                    totals["title_only_or_short"] += 1
                if (source.enabled and source.adapter != "ccgp_html"
                        and article.editorial_relevance not in {"irrelevant", "uncertain"}
                        and article.parse_status != "metadata_only" and article.source_body):
                    bucket["eligible_for_reprocess"] += 1
                    totals["eligible_for_reprocess"] += 1
        return {"totals": dict(totals),
                "sources": {slug: dict(counts) for slug, counts in sorted(by_source.items())}}
    finally:
        engine.dispose()


def main() -> int:
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
