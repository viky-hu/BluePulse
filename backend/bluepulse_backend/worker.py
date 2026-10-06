from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, time as datetime_time, timedelta
from zoneinfo import ZoneInfo

from bluepulse_backend.ingestion.pipeline import (
    backfill_entities,
    reprocess_pending,
    run_ingestion,
    sync_reference_data,
    translate_pending,
)
from bluepulse_backend.ingestion.operations import (
    get_source_status, recover_interrupted, retry_failed_sources,
)
from bluepulse_backend.ingestion.lease import IngestionBusy

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _seconds_until_next_run(now: datetime | None = None) -> float:
    current = now.astimezone(SHANGHAI) if now else datetime.now(SHANGHAI)
    next_run = datetime.combine(current.date(), datetime_time(hour=6), tzinfo=SHANGHAI)
    if next_run <= current:
        next_run += timedelta(days=1)
    return (next_run - current).total_seconds()


def _print_result(result: object) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(prog="bluepulse-worker")
    parser.add_argument(
        "command",
        choices=("sync-config", "ingest-once", "source-status", "retry-failed", "recover-interrupted", "reprocess-pending", "translate-pending", "backfill-entities", "schedule"),
        help="同步配置、采集一次、分析或翻译历史文章，或启动每日 06:00 调度",
    )
    parser.add_argument("--source", help="只采集或分析指定的来源 slug")
    parser.add_argument("--limit", type=int, default=10, help="重处理历史文章的最大数量（1-30）")
    parser.add_argument("--editorial-only", action="store_true", help="仅重处理人工确认相关的待处理文章")
    parser.add_argument("--apply", action="store_true", help="执行 retry-failed 或 recover-interrupted；不加时只预览")
    parser.add_argument("--include-partial", action="store_true", help="retry-failed 也包含最近部分成功的来源")
    parser.add_argument("--idempotency-key", help="ingest-once 的重复提交键；同一键只执行一次")
    args = parser.parse_args()

    if args.command == "sync-config":
        _print_result(sync_reference_data())
        return 0
    if args.command == "ingest-once":
        try:
            result = run_ingestion(source_slug=args.source,
                                   idempotency_key=args.idempotency_key)
            _print_result(result)
            return 2 if result["status"] == "stale" else 0
        except IngestionBusy as exc:
            _print_result({"status": "busy", "active_run_id": str(exc.run_id)})
            return 2
    if args.command == "source-status":
        _print_result({"sources": get_source_status(args.source)})
        return 0
    if args.command == "retry-failed":
        result = retry_failed_sources(args.source, apply=args.apply,
                                      include_partial=args.include_partial)
        _print_result(result)
        return 1 if any(row["status"] in {"failed", "partial", "error", "busy"}
                        for row in result.get("results", [])) else 0
    if args.command == "recover-interrupted":
        result = recover_interrupted(apply=args.apply)
        _print_result(result)
        if result.get("status") == "busy":
            return 2
        return 1 if any(row["status"] in {"failed", "partial", "error", "stale"}
                        for row in result.get("results", [])) else 0
    if args.command == "reprocess-pending":
        _print_result(reprocess_pending(source_slug=args.source, limit=args.limit,
                                        editorial_only=args.editorial_only))
        return 0
    if args.command == "translate-pending":
        _print_result(translate_pending(source_slug=args.source, limit=args.limit))
        return 0
    if args.command == "backfill-entities":
        _print_result(backfill_entities())
        return 0

    print("Worker 已启动；每日 Asia/Shanghai 06:00 采集。按 Ctrl+C 停止。")
    while True:
        time.sleep(_seconds_until_next_run())
        try:
            day = datetime.now(SHANGHAI).date().isoformat()
            _print_result(run_ingestion(trigger_type="scheduled",
                                        idempotency_key=f"scheduled:{day}"))
        except IngestionBusy as exc:
            _print_result({"status": "busy", "active_run_id": str(exc.run_id)})
        except Exception as exc:
            print(json.dumps({"status": "failed", "error_class": type(exc).__name__}))


if __name__ == "__main__":
    raise SystemExit(main())
