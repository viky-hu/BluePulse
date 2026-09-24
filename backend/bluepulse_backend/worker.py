from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, time as datetime_time, timedelta
from zoneinfo import ZoneInfo

from bluepulse_backend.ingestion.pipeline import run_ingestion, sync_reference_data

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
        choices=("sync-config", "ingest-once", "schedule"),
        help="同步来源/主题配置、立即采集一次，或启动每日 06:00 调度",
    )
    args = parser.parse_args()

    if args.command == "sync-config":
        _print_result(sync_reference_data())
        return 0
    if args.command == "ingest-once":
        _print_result(run_ingestion())
        return 0

    print("Worker 已启动；每日 Asia/Shanghai 06:00 采集。按 Ctrl+C 停止。")
    while True:
        time.sleep(_seconds_until_next_run())
        try:
            _print_result(run_ingestion(trigger_type="scheduled"))
        except Exception as exc:
            print(json.dumps({"status": "failed", "error_class": type(exc).__name__}))


if __name__ == "__main__":
    raise SystemExit(main())
