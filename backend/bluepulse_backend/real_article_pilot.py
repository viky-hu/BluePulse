"""Bounded GOV.UK real-article flow in two isolated, local-only databases."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from shutil import copy2

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .api import create_app
from .cli import sync_taxonomy
from .db import make_engine
from .live_model import LiveAnalyzer, load_local_credentials, model_listed
from .models import AnalysisAttempt, Material, Source
from .pipeline import apply_saved_analysis, process_pending
from .source_validation import _migrate, audit_source


BACKEND = Path(__file__).resolve().parents[1]
TARGET_URL = "https://www.gov.uk/government/publications/live-facial-recognition-deployment-records"
DEFAULT_ENV = BACKEND.parent.parent / ".env"


def _api_check(address: str, material_id: str, *, visible: bool, topic: str | None = None) -> dict:
    app = create_app(address)
    with TestClient(app) as client:
        listing = client.get("/api/v1/articles", params={"period": "all", **({"topic": topic} if topic else {})})
        detail = client.get(f"/api/v1/articles/{material_id}")
        timeline = client.get("/api/v1/site/timeline")
    app.state.engine.dispose()
    items = listing.json().get("items", []) if listing.status_code == 200 else []
    if (listing.status_code != 200 or detail.status_code != (200 if visible else 404)
            or (material_id in {item["id"] for item in items}) != visible
            or timeline.status_code != 200):
        raise ValueError("api_visibility_check_failed")
    return {"list_status": listing.status_code, "list_count": len(items),
            "detail_status": detail.status_code, "timeline_cards": len(timeline.json()["cards"]),
            "detail": ({key: detail.json().get(key) for key in (
                "id", "title", "summary", "topics", "url", "body_source_url", "body_status")}
                       if visible else None)}


def run(output_dir: Path, *, env: Path = DEFAULT_ENV) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output_directory_must_be_empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    hidden_db = output_dir / "hidden.db"
    hidden_url = f"sqlite:///{hidden_db.as_posix()}"
    _migrate(hidden_url)
    sync_taxonomy(hidden_url)
    engine = make_engine(hidden_url)
    try:
        with Session(engine) as session:
            audit = audit_source("govuk", session, max_items=2)
            (output_dir / "source-audit.json").write_text(
                json.dumps(audit, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
            if audit["error_code"] is not None:
                raise ValueError(f"source_failed:{audit['error_code']}")
            material = session.scalar(select(Material).where(Material.source_url == TARGET_URL))
            item = next((row for row in audit["item_diagnostics"] if row["url"] == TARGET_URL), None)
            if (material is None or item is None or material.body_status != "full_text"
                    or not material.body_source_url or item["csv_matches_html"] is not True):
                raise ValueError("target_attachment_evidence_incomplete")
            if len(material.source_body.splitlines()) != 19:
                raise ValueError("target_table_shape_changed")
            base_url, api_key, model_id = load_local_credentials(env)
            with httpx.Client(timeout=httpx.Timeout(35, connect=10), follow_redirects=False) as client:
                if not model_listed(client, base_url, api_key, model_id):
                    raise ValueError("model_preflight_failed")
                analyzer = LiveAnalyzer(client, base_url, api_key, model_id)
                processed = process_pending(session, analyzer, max_items=1, material_id=material.id)
            session.refresh(material)
            attempt = session.scalar(select(AnalysisAttempt).where(
                AnalysisAttempt.material_id == material.id).order_by(AnalysisAttempt.attempt.desc()).limit(1))
            if processed != {"applied": 1, "failed": 0, "unknown": 0} or attempt is None:
                raise ValueError("model_analysis_incomplete")
            material_id = material.id
            model_result = {"attempt_status": attempt.status, "relevant": material.relevant,
                            "topics": material.topics, "title_zh": material.zh_title,
                            "summary_zh": material.zh_summary, "importance_score": material.importance_score,
                            "public": material.public}
            if session.scalar(select(func.count()).select_from(Material).where(Material.public.is_(True))):
                raise ValueError("hidden_database_became_public")
    finally:
        engine.dispose()
    hidden_api = _api_check(hidden_url, material_id, visible=False)

    # This copy is served only on localhost for browser verification. The real-source
    # permission in the original isolated database, and the formal database, stay closed.
    display_db = output_dir / "localhost-display.db"
    copy2(hidden_db, display_db)
    display_url = f"sqlite:///{display_db.as_posix()}"
    display_engine = make_engine(display_url)
    try:
        with Session(display_engine) as session:
            material = session.get(Material, material_id)
            source = session.get(Source, material.source_id)
            source.excerpt_allowed = True
            source.full_text_allowed = False
            session.commit()
            if not apply_saved_analysis(session, material, attempt.input_version):
                raise ValueError("saved_model_result_not_reapplied")
            session.refresh(material)
            if material.public is not True or material.duplicate_of_id is not None:
                raise ValueError("local_display_gate_not_met")
            topic = material.topics[0] if material.topics else None
    finally:
        display_engine.dispose()
    display_api = _api_check(display_url, material_id, visible=True, topic=topic)
    report = {"target_url": TARGET_URL, "body_source_url": item["body_source_url"],
              "body_chars": len(next(row["body"] for row in audit["items"] if row["url"] == TARGET_URL)),
              "table_lines": 19, "csv_rows": item["csv_rows"],
              "csv_matches_html": item["csv_matches_html"],
              "source_audit": {key: audit[key] for key in (
                  "error_code", "robots_status", "entry_status", "candidate_count", "body_status",
                  "date_covered", "duration_seconds")},
              "first_ingest": audit["ingest_first"]["discoveries"],
              "same_snapshot_replay": audit["ingest_repeat_same_snapshot"]["discoveries"],
              "model_calls": 1, "model": model_result,
              "hidden_api": hidden_api, "localhost_display_api": display_api,
              "hidden_database": str(hidden_db), "display_database": str(display_db),
              "formal_database_writes": 0, "external_publication": False}
    (output_dir / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-paid-model", action="store_true")
    args = parser.parse_args()
    if not args.execute or not args.allow_paid_model:
        parser.error("pass --execute --allow-paid-model; this pilot makes at most one model call")
    report = run(args.output_dir, env=args.env)
    print(json.dumps({"model_calls": report["model_calls"], "model": report["model"],
                      "hidden_api": report["hidden_api"],
                      "localhost_display_api": report["localhost_display_api"],
                      "output_dir": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
