"""Bounded real classification check, at most one new model call per source per run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from .ccgp_source import USER_AGENT
from .db import make_engine
from .live_model import LiveAnalyzer, load_local_credentials, model_listed
from .model_processing import process_model_batch
from .models import Material, Source
from .source_collection import SOURCES


def classify_once_per_source(session: Session, analyzer, *, max_calls: int) -> dict:
    if not 0 <= max_calls <= 50:
        raise ValueError("model call cap must be 0-50")
    rows = []
    remaining = max_calls
    for slug in SOURCES:
        source = session.scalar(select(Source).where(Source.slug == slug))
        if source is None:
            rows.append({"source": slug, "status": "source_missing"})
            continue
        result = process_model_batch(session, analyzer, source_id=source.id,
                                     max_calls=min(remaining, 1), include_selection=False)
        remaining -= result["calls_used"]
        counts = session.execute(select(
            func.count(Material.id),
            func.sum(Material.relevant.is_not(None).cast(Integer)),
            func.sum(Material.public.is_(True).cast(Integer)),
        ).where(Material.source_id == source.id)).one()
        rows.append({"source": slug, "processing": result,
                     "materials": counts[0], "classified": counts[1] or 0,
                     "public": counts[2] or 0})
        if result["stop_batch"]:
            break
    return {"max_calls": max_calls, "calls_used": max_calls - remaining, "sources": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify saved real articles without selection scoring")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--database-url", required=True, help="already migrated target database")
    parser.add_argument("--allow-paid-model", action="store_true")
    parser.add_argument("--max-model-calls-total", type=int, default=0)
    parser.add_argument("--env", type=Path, default=Path(__file__).resolve().parents[3] / ".env")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.execute or not args.allow_paid_model or not 1 <= args.max_model_calls_total <= 50:
        parser.error("--execute, --allow-paid-model, and a 1-50 call cap are required")
    base_url, api_key, model = load_local_credentials(args.env)
    with httpx.Client(timeout=httpx.Timeout(35, connect=10), follow_redirects=False,
                      headers={"User-Agent": USER_AGENT}) as client:
        if not model_listed(client, base_url, api_key, model):
            parser.error("configured model is not listed by the provider")
        analyzer = LiveAnalyzer(client, base_url, api_key, model)
        engine = make_engine(args.database_url)
        try:
            with Session(engine) as session:
                report = classify_once_per_source(session, analyzer,
                                                  max_calls=args.max_model_calls_total)
        finally:
            engine.dispose()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(args.report), "calls_used": report["calls_used"],
                      "sources": [{"source": row["source"],
                                   "classified": row.get("classified"),
                                   "public": row.get("public")}
                                  for row in report["sources"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
