"""Daily, bounded source audit. Writes only to a new local SQLite database."""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from .ccgp_source import USER_AGENT
from .db import make_engine
from .pipeline import MockSourceAdapter, canonical_url
from .source_collection import SOURCES, build_adapter, collect


def _migrate(database_url: str) -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    previous = os.environ.get("BLUEPULSE_DATABASE_URL")
    try:
        os.environ["BLUEPULSE_DATABASE_URL"] = database_url
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("BLUEPULSE_DATABASE_URL", None)
        else:
            os.environ["BLUEPULSE_DATABASE_URL"] = previous


def audit_source(slug: str, session: Session, *, max_items: int = 2,
                 pages_dir: Path | None = None) -> dict:
    spec = SOURCES[slug]
    requests: list[dict] = []
    raw_responses: dict[str, bytes] = {}
    started = time.monotonic()

    def on_request(request: httpx.Request) -> None:
        requests.append({"path": request.url.path, "status": None})

    def on_response(response: httpx.Response) -> None:
        # Never record headers, query parameters, or response bodies.
        requests[-1]["status"] = response.status_code

    with httpx.Client(timeout=httpx.Timeout(35, connect=10), follow_redirects=False,
                      headers={"User-Agent": USER_AGENT},
                      event_hooks={"request": [on_request], "response": [on_response]}) as client:
        adapter = build_adapter(spec, client, max_items=max_items)
        adapter.http.on_body = lambda url, payload: raw_responses.__setitem__(url, payload)
        try:
            candidates = adapter.candidates()
            error = None
        except Exception as exc:
            candidates = []
            error = getattr(exc, "code", type(exc).__name__)

    urls = [canonical_url(item.url, [spec.host]) for item in candidates]
    first = second = None
    if error is None:
        # Reuse the exact fetched candidates: the second pass tests identity without
        # spending another network request or mistaking a changed page for a revision.
        first = collect(session, spec, MockSourceAdapter(candidates))
        second = collect(session, spec, MockSourceAdapter(candidates))
    diagnostics = dict(getattr(adapter, "diagnostics", {}))
    items = [{
        "url": item.url, "title": item.title,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "published_date": item.published_date.isoformat() if item.published_date else None,
        "body_chars": len(item.body or ""), "summary_chars": len(item.summary or ""),
        "body_source_url": item.body_source_url,
        "body": item.body, "summary": item.summary,
    } for item in candidates]
    if pages_dir is not None and candidates:
        pages_dir.mkdir(parents=True, exist_ok=True)
        first_url = candidates[0].url
        request_url = ("https://www.gov.uk/api/content" + first_url.removeprefix("https://www.gov.uk")
                       if spec.kind == "govuk_api" else first_url)
        raw = raw_responses.get(request_url)
        if raw is not None:
            page_file = pages_dir / f"{slug}.{'json' if spec.kind == 'govuk_api' else 'html'}"
            page_file.write_bytes(raw)
            items[0]["raw_page_file"] = str(page_file)
            items[0]["raw_page_bytes"] = len(raw)
    return {
        "source": slug, "host": spec.host, "duration_seconds": round(time.monotonic() - started, 2),
        "error_code": error, "last_request_path": requests[-1]["path"] if requests else None,
        "robots_status": next((row["status"] for row in requests if row["path"] == "/robots.txt"), None),
        "entry_path": next((row["path"] for row in requests if row["path"] != "/robots.txt"), None),
        "entry_status": next((row["status"] for row in requests if row["path"] != "/robots.txt"), None),
        "requests": requests, "diagnostics": diagnostics,
        "discovered_urls": getattr(adapter, "discovered_urls", []),
        "item_diagnostics": getattr(adapter, "item_diagnostics", []),
        "candidate_count": len(candidates), "duplicate_urls_within_source": len(urls) - len(set(urls)),
        "body_status": dict(Counter("full_text" if item.body else "abstract_only" if item.summary
                                    else "metadata_only" for item in candidates)),
        "date_covered": sum(item.published_at is not None or item.published_date is not None
                            for item in candidates),
        "body_at_known_cap": sum(len(item.body or "") in {12000, 100000} for item in candidates),
        "ingest_first": first, "ingest_repeat_same_snapshot": second, "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(SOURCES), action="append",
                        help="repeat for a subset; default is all 15")
    parser.add_argument("--max-items", type=int, default=2)
    parser.add_argument("--quality-sample", action="store_true",
                        help="explicit one-off quality sample of up to five details per source")
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data/source-validation")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    ceiling = 5 if args.quality_sample else 2
    if not args.execute or not 1 <= args.max_items <= ceiling:
        parser.error(f"pass --execute and choose 1-{ceiling} max-items")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y-%m-%dT%H%M%S%z")
    # One dedicated database across days makes revisions and cross-day duplicates observable.
    database = output / "observation.db"
    report_file = output / f"baseline-{stamp}.json"
    review_file = output / f"review-{stamp}.json"
    if report_file.exists() or review_file.exists():
        parser.error("run output already exists")
    _migrate(f"sqlite:///{database.as_posix()}")
    engine = make_engine(f"sqlite:///{database.as_posix()}")
    rows: list[dict] = []
    try:
        with Session(engine) as session:
            for slug in args.source or list(SOURCES):
                row = audit_source(slug, session, max_items=args.max_items,
                                   pages_dir=output / f"pages-{stamp}")
                rows.append(row)
                print(json.dumps({key: row[key] for key in ("source", "error_code", "candidate_count",
                                                              "duration_seconds")}, ensure_ascii=False), flush=True)
    finally:
        engine.dispose()
        report_file.write_text(json.dumps({"run_at": stamp, "max_items": args.max_items,
                                           "database": str(database), "sources": rows},
                                          ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        review_file.write_text(json.dumps({
            "run_at": stamp,
            "items": [{"source": row["source"], "url": item["url"], "page_checked": False,
                       "body_clean": None, "topic_fit": None,
                       "evidence_sufficient": None, "editorial_fit": None,
                       "note": ""} for row in rows for item in row["items"]],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(report_file))


if __name__ == "__main__":
    main()
