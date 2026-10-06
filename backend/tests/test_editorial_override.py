from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from bluepulse_backend.api import create_app, get_session
from bluepulse_backend.ingestion.pipeline import refresh_featured
from bluepulse_backend.models import Article, Base, Source
from scripts.apply_selection_gold import apply_confirmed_gold


class EditorialOverrideTests(unittest.TestCase):
    def test_confirmed_labels_control_publication_and_survive_model_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_url = f"sqlite:///{(Path(temp_dir) / 'test.db').as_posix()}"
            engine = create_engine(db_url)
            Base.metadata.create_all(engine)
            now = datetime.now(UTC)
            with Session(engine) as session, session.begin():
                source = Source(slug="test", name="Test", base_url="https://example.org",
                                adapter="rss", source_type="media", enabled=True)
                session.add(source)
                session.flush()
                hidden = Article(source_id=source.id, source_url="https://example.org/armor",
                                 canonical_url="https://example.org/armor", source_title="Routine armor",
                                 processing_status="processed", parse_status="summary_only", featured_candidate=True,
                                 featured_reason="incorrect model suggestion", published_at=now)
                selected = Article(source_id=source.id, source_url="https://example.org/drone",
                                   canonical_url="https://example.org/drone", source_title="Police drone",
                                   processing_status="processed", parse_status="summary_only", featured_candidate=False,
                                   published_at=now)
                session.add_all((hidden, selected))
                session.flush()
                hidden_id, selected_id = hidden.id, selected.id
            gold_path = Path(temp_dir) / "gold.jsonl"
            cases = [
                {"case_id": str(hidden_id), "article_id": str(hidden_id), "split": "development",
                 "review_status": "confirmed", "gold": {
                     "relevance": "irrelevant", "select": "reject", "primary_topic": None,
                     "content_kind": None, "evidence_level": "announcement",
                     "reason": "普通防弹衣，不属于警务科技应用。"}},
                {"case_id": str(selected_id), "article_id": str(selected_id), "split": "development",
                 "review_status": "confirmed", "gold": {
                     "relevance": "direct", "select": "select", "primary_topic": "policing",
                     "content_kind": "deployment", "evidence_level": "announcement",
                     "reason": "警用无人机有具体应用场景。"}},
            ]
            gold_path.write_text("\n".join(json.dumps(case, ensure_ascii=False) for case in cases),
                                 encoding="utf-8")
            with Session(engine) as session:
                preview = apply_confirmed_gold(session, gold_path)
                self.assertEqual(preview["counts"]["changed"], 2)
                self.assertIsNone(session.get(Article, hidden_id).editorial_relevance)
                applied = apply_confirmed_gold(session, gold_path, apply=True)
                session.commit()
                self.assertEqual(applied["counts"]["withheld_by_human"], 1)
                self.assertEqual(applied["counts"]["human_featured_candidate"], 1)
            with Session(engine) as session:
                self.assertEqual(apply_confirmed_gold(session, gold_path, apply=True)["counts"]["changed"], 0)
                rows = list(session.scalars(select(Article)))
                self.assertEqual({row.editorial_case_id for row in rows},
                                 {str(hidden_id), str(selected_id)})
                session.get(Article, selected_id).featured_candidate = False
                session.get(Article, hidden_id).featured_candidate = True
                refresh_featured(session)
                session.commit()

            def session_override():
                with Session(engine) as session:
                    yield session

            app = create_app()
            app.dependency_overrides[get_session] = session_override
            with TestClient(app) as client:
                listing = client.get("/api/v1/articles?period=all")
                self.assertEqual([item["id"] for item in listing.json()["items"]], [str(selected_id)])
                self.assertEqual(client.get(f"/api/v1/articles/{hidden_id}").status_code, 404)
                featured = client.get("/api/v1/home/featured").json()["items"]
                self.assertEqual([item["article"]["id"] for item in featured], [str(selected_id)])
                self.assertEqual(featured[0]["featured_reason"], "警用无人机有具体应用场景。")
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
