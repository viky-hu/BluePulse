"""Bounded automatic collection entry point with durable per-attempt diagnostics."""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .ccgp_source import USER_AGENT
from .db import make_engine
from .live_model import LiveAnalyzer, load_local_credentials, model_listed
from .models import Source
from .model_processing import process_model_batch
from .operations import source_funnel
from .publication import refresh_source_publication
from .source_collection import SOURCES, build_adapter, collect


RETRYABLE = {"timeout", "transport_error", "http_500", "http_502", "http_503", "http_504"}


def run_cycle(session: Session, client_factory: Callable, *, source_slugs: list[str],
              max_items: int = 2, retry_attempts: int = 2, retry_delay: float = 2,
              analyzer=None, model_remaining: int = 0,
              sleeper: Callable[[float], None] = time.sleep) -> dict:
    """Retry only transient fetch failures; every try remains a separate SourceRun."""
    if not 1 <= max_items <= 5 or not 0 <= retry_attempts <= 3 or model_remaining < 0:
        raise ValueError("invalid_cycle_limits")
    report = {"started_at": datetime.now(UTC).isoformat(), "sources": [], "model_used": 0}
    for slug in source_slugs:
        spec = SOURCES[slug]
        attempts = []
        for index in range(retry_attempts + 1):
            requests: list[dict] = []
            with client_factory() as client:
                if isinstance(client, httpx.Client):
                    def on_request(request: httpx.Request) -> None:
                        requests.append({"path": request.url.path, "status": None})

                    def on_response(response: httpx.Response) -> None:
                        requests[-1]["status"] = response.status_code

                    client.event_hooks["request"].append(on_request)
                    client.event_hooks["response"].append(on_response)
                adapter = build_adapter(spec, client, max_items=max_items)
                try:
                    result = collect(session, spec, adapter)
                except Exception as exc:
                    # Policy/configuration failures should remain visible and never be retried.
                    result = {"status": "worker_error", "error_code": type(exc).__name__,
                              "fetch_metrics": {}, "discoveries": {}}
            result["requests"] = requests
            if result["status"] in {"failed", "worker_error"}:
                last_path = requests[-1]["path"] if requests else None
                result["failure_stage"] = ("robots" if last_path == "/robots.txt" else
                                           "detail" if result.get("fetch_metrics", {}).get("detail_attempts") else
                                           "entry" if last_path else "setup")
            attempts.append(result)
            if result["status"] != "failed" or result.get("error_code") not in RETRYABLE:
                break
            if index < retry_attempts:
                sleeper(min(30, retry_delay * (2 ** index)))
        processing = None
        source = session.scalar(select(Source).where(Source.slug == slug))
        if analyzer is not None and source is not None and source.enabled:
            if attempts[-1]["status"] in {"completed", "partial", "no_candidates"}:
                processing = process_model_batch(session, analyzer, source_id=source.id,
                                                 max_calls=model_remaining)
                report["model_used"] += processing["calls_used"]
                model_remaining -= processing["calls_used"]
                if processing["stop_batch"]:
                    model_remaining = 0
        permission_changes = refresh_source_publication(session, source.id) if source is not None else None
        if attempts[-1].get("run_id"):
            attempts[-1] = {**source_funnel(session, attempts[-1]["run_id"]),
                            **{key: attempts[-1][key] for key in ("requests", "failure_stage")
                               if key in attempts[-1]}}
        report["sources"].append({"source": slug, "attempts": attempts,
                                  "processing": processing, "permission_changes": permission_changes})
    report["finished_at"] = datetime.now(UTC).isoformat()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded automatic source collection cycle")
    parser.add_argument("--execute", action="store_true", help="required for network access")
    parser.add_argument("--database-url", required=True, help="already migrated target database")
    parser.add_argument("--source", action="append", choices=sorted(SOURCES))
    parser.add_argument("--max-items", type=int, default=2)
    parser.add_argument("--retry-attempts", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=2)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--interval-seconds", type=int, default=3600)
    parser.add_argument("--allow-paid-model", action="store_true")
    parser.add_argument("--max-model-calls-total", type=int, default=0)
    parser.add_argument("--env", type=Path, default=Path(__file__).resolve().parents[3] / ".env")
    parser.add_argument("--report-dir", type=Path, default=Path("data/source-worker"))
    args = parser.parse_args()
    if not args.execute or not 1 <= args.max_items <= 5 or not 0 <= args.retry_attempts <= 3:
        parser.error("--execute and bounded collection limits are required")
    if not 1 <= args.cycles <= 32 or not 0 <= args.interval_seconds <= 86400 or args.retry_delay < 0:
        parser.error("invalid scheduling limits")
    if not 0 <= args.max_model_calls_total <= 50:
        parser.error("model call cap must be 0-50")
    if bool(args.max_model_calls_total) != args.allow_paid_model:
        parser.error("paid analysis requires both --allow-paid-model and a positive total cap")

    def client_factory():
        return httpx.Client(timeout=httpx.Timeout(35, connect=10), follow_redirects=False,
                            headers={"User-Agent": USER_AGENT})

    analyzer = None
    if args.allow_paid_model:
        base_url, api_key, model = load_local_credentials(args.env)
        with client_factory() as client:
            if not model_listed(client, base_url, api_key, model):
                parser.error("configured model is not listed by the provider")
        # The model client is held only for this bounded process invocation.
        model_client = client_factory()
        analyzer = LiveAnalyzer(model_client, base_url, api_key, model)
    else:
        model_client = None

    engine = make_engine(args.database_url)
    try:
        remaining = args.max_model_calls_total
        for cycle in range(args.cycles):
            with Session(engine) as session:
                report = run_cycle(session, client_factory, source_slugs=args.source or list(SOURCES),
                                   max_items=args.max_items, retry_attempts=args.retry_attempts,
                                   retry_delay=args.retry_delay, analyzer=analyzer,
                                   model_remaining=remaining)
            remaining -= report["model_used"]
            args.report_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            path = args.report_dir / f"cycle-{stamp}.json"
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            print(json.dumps({"report": str(path), "model_used": report["model_used"],
                              "sources": [{"source": item["source"],
                                           "status": item["attempts"][-1]["status"],
                                           "tries": len(item["attempts"])} for item in report["sources"]]},
                             ensure_ascii=False))
            if cycle + 1 < args.cycles:
                time.sleep(args.interval_seconds)
    finally:
        engine.dispose()
        if model_client is not None:
            model_client.close()


if __name__ == "__main__":
    main()
