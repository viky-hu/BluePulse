from __future__ import annotations

import unittest
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bluepulse_backend.ingestion.llm import ModelAnalysisError, _parse_analysis
from bluepulse_backend.ingestion.pipeline import refresh_featured
from bluepulse_backend.models import Article, Base, Source


class FeaturedSelectionTests(unittest.TestCase):
    def test_selection_is_independent_of_relevance_and_score(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        now = datetime.now(UTC)
        with Session(engine) as session, session.begin():
            source = Source(slug="test", name="Test", base_url="https://example.org", adapter="rss")
            session.add(source)
            session.flush()
            for index, (score, selected) in enumerate(((95, False), (62, True))):
                session.add(Article(
                    source_id=source.id, source_url=f"https://example.org/{index}",
                    canonical_url=f"https://example.org/{index}", source_title=f"Case {index}",
                    importance_score=score, featured_candidate=selected,
                    featured_reason="有具体警务科技应用" if selected else None,
                    processing_status="processed", parse_status="summary_only", published_at=now,
                ))
            session.flush()
            edition = refresh_featured(session, now)
            session.flush()
            self.assertEqual([slot.article.source_title for slot in edition.slots], ["Case 1"])
        engine.dispose()

    def test_featured_candidate_requires_reason_and_relevance(self) -> None:
        base = ('{"relevant":true,"relevance":0.8,"short_title":"技术应用",'
                '"summary":"具体警务技术应用。","topics":["policing"],"importance_score":70,')
        with self.assertRaisesRegex(ModelAnalysisError, "推荐理由"):
            _parse_analysis(base + '"featured_candidate":true,"featured_reason":""}')
        result = _parse_analysis(base + '"featured_candidate":true,"featured_reason":"具体应用于接处警。"}')
        self.assertTrue(result.featured_candidate)
        self.assertEqual(result.featured_reason, "具体应用于接处警。")
        legacy = _parse_analysis(base.rstrip(",") + "}")
        self.assertFalse(legacy.featured_candidate)


if __name__ == "__main__":
    unittest.main()
