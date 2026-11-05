"""Run a disposable, entirely offline source-to-HTTP smoke check."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from .api import create_app
from .db import Base, make_engine
from .models import Source, Topic
from .operations import source_funnel
from .pipeline import AnalysisResult, Candidate, MockAnalyzer, MockSourceAdapter, ingest, process_pending


def main() -> None:
    scratch = Path(__file__).resolve().parents[1] / ".tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=scratch) as directory:
        url = f"sqlite:///{(Path(directory) / 'mock.db').as_posix()}"
        engine = make_engine(url)
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            source = Source(slug="mock-official", name="Mock Official", region="foreign",
                            country_code="GB", language="en", source_type="official",
                            topics=["policing"], allowed_hosts=["example.test"], excerpt_allowed=True,
                            min_body_status="abstract_only")
            session.add_all([source, Topic(slug="policing", name_zh="警务应用", name_en="Policing")])
            session.commit()
            item = Candidate(url="https://example.test/one", title="Mock source title",
                             summary="Source abstract only", language="en",
                             published_at=datetime.now(UTC) - timedelta(hours=1))
            run = ingest(session, source, MockSourceAdapter([item]))
            analysis = MockAnalyzer({"https://example.test/one": AnalysisResult(
                relevant=True, title_zh="离线演示材料", summary_zh="仅用于检查链路和接口。",
                topics=("policing",), importance_score=60,
            )})
            processing = process_pending(session, analysis)
            funnel = source_funnel(session, run.id)
        app = create_app(url)
        with TestClient(app) as client:
            listing = client.get("/api/v1/articles?period=all")
            taxonomy = client.get("/api/v1/taxonomy")
            health = client.get("/api/v1/health/ready")
        report = {"mock_only": True, "source_run": funnel, "processing": processing,
                  "api": {"articles_status": listing.status_code,
                          "article_count": len(listing.json().get("items", [])),
                          "taxonomy_status": taxonomy.status_code,
                          "health_status": health.status_code}}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        app.state.engine.dispose()
        engine.dispose()


if __name__ == "__main__":
    main()
