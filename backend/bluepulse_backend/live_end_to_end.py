"""One bounded 15-source network run into a fresh isolated, nonpublic database."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .api import create_app
from .cli import sync_taxonomy
from .db import make_engine
from .live_model import LiveAnalyzer, load_local_credentials, model_listed
from .models import AnalysisAttempt, Material, Source
from .pipeline import process_pending
from .source_collection import SOURCES, ensure_source
from .source_validation import _migrate, audit_source


BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = BACKEND / "data/live-end-to-end"
MODEL_PRIORITY = ("htx-news", "nist-public-safety", "ccgp-policing-tech", "govuk")


def run(output_dir: Path, *, max_items: int = 2, max_model_calls: int = 4,
        allow_paid_model: bool = False, env: Path = BACKEND.parent.parent / ".env") -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output_directory_must_be_empty")
    if not 1 <= max_items <= 2 or not 0 <= max_model_calls <= 4:
        raise ValueError("bounded_limits_required")
    output_dir.mkdir(parents=True, exist_ok=True)
    database = output_dir / "live-test.db"
    address = f"sqlite:///{database.as_posix()}"
    _migrate(address)
    sync_taxonomy(address)
    engine = make_engine(address)
    source_results: list[dict] = []
    model_preflight = None
    model_results: list[dict] = []
    try:
        with Session(engine) as session:
            for spec in SOURCES.values():
                ensure_source(session, spec)
            for slug in SOURCES:
                source_results.append(audit_source(slug, session, max_items=max_items))
            if allow_paid_model and max_model_calls:
                base_url, api_key, model_id = load_local_credentials(env)
                with httpx.Client(timeout=httpx.Timeout(35, connect=10), follow_redirects=False) as client:
                    model_preflight = model_listed(client, base_url, api_key, model_id)
                    if model_preflight:
                        analyzer = LiveAnalyzer(client, base_url, api_key, model_id)
                        order = list(MODEL_PRIORITY) + [slug for slug in SOURCES if slug not in MODEL_PRIORITY]
                        for slug in order:
                            if len(model_results) >= max_model_calls:
                                break
                            source = session.scalar(select(Source).where(Source.slug == slug))
                            pending = session.scalar(select(Material).where(
                                Material.source_id == source.id, Material.state == "analysis_pending"
                            ).order_by(Material.published_sort_at.desc(), Material.id).limit(1))
                            if pending is None:
                                continue
                            outcome = process_pending(session, analyzer, max_items=1, material_id=pending.id)
                            attempt = session.scalar(select(AnalysisAttempt).where(
                                AnalysisAttempt.material_id == pending.id,
                                AnalysisAttempt.revision == pending.revision,
                            ).order_by(AnalysisAttempt.attempt.desc()).limit(1))
                            model_results.append({
                                "source": slug, "url": pending.source_url, "material_id": pending.id,
                                "outcome": outcome, "attempt_status": attempt.status if attempt else None,
                                "error_code": attempt.error_code if attempt else None,
                                "relevant": pending.relevant, "topics": pending.topics,
                                "public": pending.public,
                            })
                            if outcome["unknown"] or outcome["failed"]:
                                break
            counts = {
                "sources": session.scalar(select(func.count()).select_from(Source)),
                "materials": session.scalar(select(func.count()).select_from(Material)),
                "unique_url_mirrors": session.scalar(select(func.count()).select_from(Material)
                                                     .where(Material.duplicate_of_id.is_not(None))),
                "analysis_attempts": session.scalar(select(func.count()).select_from(AnalysisAttempt)),
                "public": session.scalar(select(func.count()).select_from(Material)
                                         .where(Material.public.is_(True))),
            }
            if counts["sources"] != 15 or counts["public"] != 0 or counts["analysis_attempts"] > max_model_calls:
                raise ValueError("live_test_gate_failed")
    finally:
        engine.dispose()

    app = create_app(address)
    with TestClient(app) as client:
        taxonomy = client.get("/api/v1/taxonomy")
        sources = client.get("/api/v1/sources")
        article_list = client.get("/api/v1/articles", params={"period": "all"})
        timeline = client.get("/api/v1/site/timeline")
    app.state.engine.dispose()
    if (taxonomy.status_code != 200 or len(taxonomy.json()["items"]) != 7 or
            sources.status_code != 200 or len(sources.json()["items"]) != 15 or
            article_list.status_code != 200 or article_list.json()["items"] or
            timeline.status_code != 200 or timeline.json()["cards"]):
        raise ValueError("nonpublic_frontend_contract_failed")
    report = {
        "run_at": datetime.now(UTC).isoformat(), "database": str(database),
        "max_items_per_source": max_items, "max_model_calls": max_model_calls,
        "allow_paid_model": allow_paid_model, "model_preflight": model_preflight,
        "counts": counts,
        "sources": [{key: value for key, value in row.items() if key != "items"}
                    for row in source_results],
        "source_retries": [],
        "model_results": model_results,
        "api": {"taxonomy": 7, "sources": 15, "articles": 0, "timeline_cards": 0},
        "production_writes": 0, "notice": "Isolated live test; all real-source permissions remain closed.",
    }
    (output_dir / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    (output_dir / "source-items.json").write_text(
        json.dumps(source_results, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return report


def retry_source(output_dir: Path, slug: str) -> dict:
    """Retry one previously failed entry with the same bounded adapter and database."""
    if slug not in SOURCES:
        raise ValueError("unknown_source")
    report_file = output_dir / "result.json"
    report = json.loads(report_file.read_text(encoding="utf-8"))
    initial = next((row for row in report["sources"] if row["source"] == slug), None)
    if initial is None or initial["error_code"] is None:
        raise ValueError("source_did_not_fail")
    if any(row["source"] == slug and row["error_code"] is None
           for row in report.get("source_retries", [])):
        raise ValueError("source_retry_already_succeeded")
    report.setdefault("source_retries", [])
    orphan_files = sorted(output_dir.glob(f"source-retry-{slug}-*.json"))
    orphan = orphan_files[-1] if orphan_files and not report["source_retries"] else None
    engine = make_engine(f"sqlite:///{(output_dir / 'live-test.db').as_posix()}")
    try:
        with Session(engine) as session:
            outcome = (json.loads(orphan.read_text(encoding="utf-8")) if orphan else
                       audit_source(slug, session, max_items=report["max_items_per_source"]))
            counts = {"sources": session.scalar(select(func.count()).select_from(Source)),
                      "materials": session.scalar(select(func.count()).select_from(Material)),
                      "unique_url_mirrors": session.scalar(select(func.count()).select_from(Material)
                                                         .where(Material.duplicate_of_id.is_not(None))),
                      "analysis_attempts": session.scalar(select(func.count()).select_from(AnalysisAttempt)),
                      "public": session.scalar(select(func.count()).select_from(Material)
                                               .where(Material.public.is_(True)))}
        if counts["public"] or counts["analysis_attempts"] > report["max_model_calls"]:
            raise ValueError("live_test_gate_failed")
    finally:
        engine.dispose()
    if orphan is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        (output_dir / f"source-retry-{slug}-{stamp}.json").write_text(
            json.dumps(outcome, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    report["source_retries"].append({key: value for key, value in outcome.items() if key != "items"})
    report["counts"] = counts
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"source": slug, "error_code": outcome["error_code"],
            "candidate_count": outcome["candidate_count"], "counts": counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-items", type=int, default=2)
    parser.add_argument("--max-model-calls", type=int, default=4)
    parser.add_argument("--env", type=Path, default=BACKEND.parent.parent / ".env")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-paid-model", action="store_true")
    parser.add_argument("--retry-source", choices=sorted(SOURCES))
    args = parser.parse_args()
    if not args.execute:
        parser.error("pass --execute for bounded network access")
    if args.retry_source:
        print(json.dumps(retry_source(args.output_dir, args.retry_source), ensure_ascii=False))
        return
    report = run(args.output_dir, max_items=args.max_items, max_model_calls=args.max_model_calls,
                 allow_paid_model=args.allow_paid_model, env=args.env)
    print(json.dumps({"counts": report["counts"], "model_preflight": report["model_preflight"],
                      "source_errors": {row["source"]: row["error_code"] for row in report["sources"]
                                        if row["error_code"]}, "output_dir": str(args.output_dir)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
