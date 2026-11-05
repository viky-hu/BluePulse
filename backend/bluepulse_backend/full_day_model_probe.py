"""At most four paid classification checks against archived, nonpublic samples."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .cli import sync_taxonomy
from .db import make_engine
from .full_day_pilot import BACKEND, DEFAULT_CATEGORIES, DEFAULT_INPUT, _candidate, _read, _sample, _write
from .live_model import LiveAnalyzer, load_local_credentials, model_listed
from .models import AnalysisAttempt, Material
from .pipeline import MockSourceAdapter, canonical_url, process_pending
from .source_collection import SOURCES, collect
from .source_validation import _migrate


DEFAULT_SAMPLE = BACKEND / "config/full-day-model-sample-4.json"
DEFAULT_OUTPUT = BACKEND / "data/full-day-pilot/2026-11-01/model-probe"


def run(input_dir: Path, categories_file: Path, sample_file: Path, output_dir: Path,
        env_file: Path, *, max_model_calls: int, client: httpx.Client) -> dict:
    if not 1 <= max_model_calls <= 4:
        raise ValueError("model_call_cap_must_be_1_to_4")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output_directory_must_be_empty")
    sample_day, all_rows = _sample(input_dir, categories_file)
    sample = _read(sample_file)
    if sample["sample_day"] != sample_day.isoformat() or len(sample["items"]) != 4:
        raise ValueError("model_sample_must_have_four_from_same_day")
    by_key = {(row["source"], row["url"]): row for row in all_rows}
    chosen = []
    seen = set()
    for entry in sample["items"]:
        slug = entry["source"]
        url = canonical_url(entry["url"], [SOURCES[slug].host])
        if url in seen or (slug, url) not in by_key:
            raise ValueError("model_sample_invalid_or_duplicate")
        seen.add(url)
        chosen.append({**by_key[(slug, url)], "case": entry["case"]})
    base_url, api_key, model_id = load_local_credentials(env_file)
    listed = model_listed(client, base_url, api_key, model_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    database = output_dir / "model-probe.db"
    address = f"sqlite:///{database.as_posix()}"
    _migrate(address)
    sync_taxonomy(address)
    engine = make_engine(address)
    results = []
    try:
        with Session(engine) as session:
            for row in chosen:
                collect(session, SOURCES[row["source"]], MockSourceAdapter([
                    _candidate(row["source"], row["item"])]))
            analyzer = LiveAnalyzer(client, base_url, api_key, model_id)
            for index, row in enumerate(chosen):
                material = session.scalar(select(Material).where(Material.canonical_url == row["url"]))
                if material is None:
                    raise ValueError("sample_ingest_missing")
                if listed and index < max_model_calls:
                    process_pending(session, analyzer, max_items=1, material_id=material.id)
                session.refresh(material)
                attempt = session.scalar(select(AnalysisAttempt).where(
                    AnalysisAttempt.material_id == material.id).order_by(AnalysisAttempt.attempt.desc()).limit(1))
                expected_relevant = row["topic_fit"] == "direct" and row["evidence_sufficient"]
                result = {"case": row["case"], "source": row["source"], "url": row["url"],
                          "manual_topic_fit": row["topic_fit"],
                          "manual_evidence_sufficient": row["evidence_sufficient"],
                          "manual_expected_relevant": expected_relevant,
                          "manual_primary_topic": row["primary_topic"] if expected_relevant else None,
                          "attempt_status": attempt.status if attempt else "not_called",
                          "error_code": attempt.error_code if attempt else None,
                          "model_relevant": material.relevant,
                          "model_topics": material.topics,
                          "relevance_match": material.relevant == expected_relevant if attempt and attempt.status == "applied" else None,
                          "primary_topic_in_model": row["primary_topic"] in material.topics
                          if attempt and attempt.status == "applied" and expected_relevant else None,
                          "summary_zh": material.zh_summary,
                          "usage": ((attempt.result or {}).get("provider_meta") or {}) if attempt else {},
                          "public": material.public}
                results.append(result)
                if attempt and attempt.status in {"unknown", "failed"}:
                    break
            call_count = session.scalar(select(func.count()).select_from(AnalysisAttempt))
            public_count = session.scalar(select(func.count()).select_from(Material).where(Material.public.is_(True)))
    finally:
        engine.dispose()
    if call_count > max_model_calls or public_count:
        raise ValueError("model_cap_or_publication_gate_failed")
    report = {"sample_day": sample_day.isoformat(), "database": str(database),
              "model_id": model_id, "model_listed": listed,
              "max_model_calls": max_model_calls, "calls_started": call_count,
              "public": public_count, "items": results,
              "created_at": datetime.now(UTC).isoformat(),
              "notice": "Nonpublic quality probe; model output is not an editorial decision."}
    _write(output_dir / "result.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--categories", type=Path, default=DEFAULT_CATEGORIES)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--env", type=Path, default=BACKEND.parent.parent / ".env")
    parser.add_argument("--max-model-calls", type=int, default=4)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-paid-model", action="store_true")
    args = parser.parse_args()
    if not args.execute or not args.allow_paid_model:
        parser.error("pass --execute --allow-paid-model for the capped probe")
    with httpx.Client(timeout=httpx.Timeout(35, connect=10), follow_redirects=False) as client:
        result = run(args.input_dir, args.categories, args.sample, args.output_dir,
                     args.env, max_model_calls=args.max_model_calls, client=client)
    print(json.dumps({"model_listed": result["model_listed"],
                      "calls_started": result["calls_started"],
                      "max_model_calls": result["max_model_calls"],
                      "public": result["public"], "output_dir": str(args.output_dir)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
