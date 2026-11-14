"""Plan, preview and apply a bounded rewrite of the current public article summaries."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from .admin_models import AdminContentOverride
from .db import database_url, make_engine
from .editorial_copy import COPY_VERSION, grounded_reading_value, summary_copy
from .editorial_models import PaidAttempt, WorkItem
from .models import Material, now_utc
from .public_reads import listed_query
from .publication import visible
from .reading import can_show_reading_value
from .work_queue import enqueue, serialized, utc
from .worker import REWRITE_SUMMARY as KIND


REPAIR_VERSION = "concise-1"


def has_manual_summary(session, material_id):
    override = session.get(AdminContentOverride, material_id)
    return bool(override and "zh_summary" in (override.fields or {}))


def work_key(item):
    return f"{item.id}:{item.revision}:{COPY_VERSION}"


def queue_rewrites(session, items, now, *, preview, max_attempts, run_key=None, repair=False):
    run_key = run_key or f"summary-copy:{COPY_VERSION}"
    for item in items:
        job = enqueue(session, KIND, work_key(item), {
            "material_id": item.id, "revision": item.revision, "copy_version": COPY_VERSION,
            "preview": preview, "max_attempts": max_attempts, "run_key": run_key,
            "with_reason": can_show_reading_value(session, item, at=now), "historical": True,
        }, now)
        if (not preview and job.status == "done" and job.payload.get("preview")):
            job.payload = {**job.payload, "preview": False, "run_key": run_key, "max_attempts": max_attempts,
                           "reviewed_copy": job.result if (job.result or {}).get("input_hash") else None}
            job.status, job.due_at, job.result = "pending", now, None
        elif (not preview and job.payload.get("preview") and
              (job.status == "pending" or job.status == "running" and utc(job.expires_at) <= now)):
            job.payload = {**job.payload, "preview": False, "run_key": run_key, "max_attempts": max_attempts}
            if job.status == "running":
                job.status, job.token, job.expires_at, job.due_at = "pending", None, None, now
        elif (not preview and job.status == "failed" and job.error == "request_budget_total"
              and (job.payload.get("run_key") != run_key or max_attempts > job.payload["max_attempts"])):
            job.payload = {**job.payload, "preview": False, "run_key": run_key, "max_attempts": max_attempts}
            job.status, job.due_at, job.error = "pending", now, None
        elif not preview and job.status == "pending":
            job.payload = {**job.payload, "run_key": run_key, "max_attempts": max_attempts}
        elif (repair and job.status == "failed" and job.error == "invalid_editorial_copy"
              and not job.payload.get("repair")):
            job.payload = {**job.payload, "run_key": run_key, "max_attempts": max_attempts,
                           "repair": REPAIR_VERSION}
            job.status, job.due_at, job.error = "pending", now, None


def _targets(session, now):
    rows = session.scalars(listed_query().order_by(Material.first_seen_at.desc(), Material.id))
    return [item for item in rows if visible(item, at=now)]


def _sample(items, limit):
    picked = {}
    criteria = (
        lambda item: item.selected_at is not None,
        lambda item: "paper" in item.topics,
        lambda item: item.editorial_scope == "composite" and "paper" not in item.topics,
        lambda item: any(word in item.source_title for word in ("招标", "采购", "成交", "中标")),
        lambda item: any(word in item.source_body[:3000].casefold() for word in ("试点", "pilot", "trial")),
        lambda item: item.language.lower().startswith("zh"),
        lambda item: not item.language.lower().startswith("zh"),
    )
    for matches in criteria:
        if len(picked) >= limit:
            break
        item = next((item for item in items if item.id not in picked and matches(item)), None)
        if item:
            picked[item.id] = item
    for item in items:
        if len(picked) >= limit:
            break
        picked[item.id] = item
    return list(picked.values())


def _report(session, items, run_key):
    jobs = {row.identity: row for row in session.scalars(select(WorkItem).where(
        WorkItem.kind == KIND, WorkItem.payload["copy_version"].as_string() == COPY_VERSION))}
    rows = []
    for item in items:
        job = jobs.get(work_key(item))
        if has_manual_summary(session, item.id):
            status = "manual_summary"
        elif (item.editorial_data or {}).get("copy_version") == COPY_VERSION:
            status = "current"
        elif job:
            status = (job.result or {}).get("skipped") or ("previewed" if (job.result or {}).get("preview")
                                                           else job.status)
        else:
            status = "eligible"
        rows.append({"id": item.id, "revision": item.revision, "title": item.source_title,
                     "source": item.source.slug, "status": status, "summary_chars": len(item.zh_summary or ""),
                     **({"error": job.error} if job and job.error else {}),
                     **({"preview": job.result} if job and status == "previewed" else {})})
    attempts = select(func.count()).select_from(PaidAttempt).where(
        PaidAttempt.run_key == run_key)
    counts = dict(Counter(row["status"] for row in rows))
    return {"version": COPY_VERSION, "total": len(rows), "counts": counts,
            "estimated_new_calls": counts.get("eligible", 0),
            "paid_attempts": session.scalar(attempts), "items": rows}


def _apply_review(session, filename, now):
    from .daily_reports import correct_article_summary
    from .editorial import input_hash, rewrite_input

    reviewed = json.loads(filename.read_text(encoding="utf-8-sig"))
    if reviewed["version"] != COPY_VERSION:
        raise ValueError("review_prompt_version_changed")
    for entry in reviewed["items"]:
        item = session.get(Material, entry["id"])
        job = session.scalar(select(WorkItem).where(WorkItem.kind == KIND,
                                                    WorkItem.identity == work_key(item))) if item else None
        if not item or not job or not visible(item, at=now) or has_manual_summary(session, item.id):
            raise ValueError("review_preview_missing_or_changed")
        data = rewrite_input(item)
        current_hash = input_hash(json.dumps(data, ensure_ascii=False, sort_keys=True))
        if entry["input_hash"] != current_hash:
            raise ValueError("review_preview_missing_or_changed")
        saved = (job.result or {}) if job.payload.get("preview") else job.payload.get("reviewed_copy") or {}
        if job.status == "running" and utc(job.expires_at) > now:
            raise ValueError("review_job_still_running")
        summary = summary_copy(entry["summary"], data["title"], data["text"])
        with_reason = can_show_reading_value(session, item, at=now)
        reason = (grounded_reading_value(entry.get("reason"), data["title"], data["text"], summary=summary)
                  if with_reason else None)
        if (item.editorial_data or {}).get("copy_version") == COPY_VERSION:
            from .editorial import save_summary_copy

            save_summary_copy(item, summary, reason)
            correct_article_summary(session, item, now)
            continue
        result = {**saved, "preview": True, "input_hash": current_hash, "summary": summary, "reason": reason,
                  "with_reason": with_reason}
        job.payload = {**job.payload, "preview": True}
        job.status, job.token, job.expires_at, job.error, job.result = "done", None, None, None, result


def main():
    from .worker import Worker, _budget_from_env, _client
    from .receipts import recover_receipts

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=database_url())
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", type=int, metavar="ARTICLES")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--max-attempts", type=int)
    parser.add_argument("--workers", type=int, choices=range(1, 7), default=1)
    parser.add_argument("--reviewed", type=Path, help="optional copy corrections from the reviewed preview")
    parser.add_argument("--repair-failed", action="store_true", help="retry rejected output once with a stricter prompt")
    parser.add_argument("--run-key", default=f"summary-copy:{COPY_VERSION}")
    args = parser.parse_args()
    execute = args.preview is not None or args.apply
    budget = _budget_from_env() if execute else None
    if execute and budget is None:
        parser.error("set BLUEPULSE_MODEL_CALLS_ENABLED=1 and configure the model budgets")
    if execute and not (args.max_attempts and args.max_attempts > 0):
        parser.error("--preview and --apply require a positive --max-attempts")
    if args.preview is not None and not 1 <= args.preview <= args.max_attempts:
        parser.error("--preview requires an article count within the attempt cap")
    if args.reviewed and not args.apply:
        parser.error("--reviewed requires --apply")
    if args.repair_failed and not args.apply:
        parser.error("--repair-failed requires --apply")
    url = make_url(args.database_url)
    if url.get_backend_name() != "sqlite" or not url.database or not Path(url.database).is_file():
        parser.error("an existing SQLite database is required")
    uri = Path(url.database).resolve().as_uri() + "?mode=ro"
    read_engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True, timeout=30))
    engine = make_engine(args.database_url) if execute else None
    try:
        now = now_utc()
        with Session(read_engine) as session:
            items = _targets(session, now)
            eligible = [item for item in items if not has_manual_summary(session, item.id)
                        and (item.editorial_data or {}).get("copy_version") != COPY_VERSION]
            ids = {item.id for item in (_sample(eligible, args.preview) if args.preview else eligible)}
        if execute:
            with serialized(engine) as session:
                existing = set(session.scalars(select(WorkItem.payload["material_id"].as_string()).where(
                    WorkItem.kind == KIND, WorkItem.payload["run_key"].as_string() == args.run_key,
                    WorkItem.payload["copy_version"].as_string() == COPY_VERSION,
                    WorkItem.payload["preview"].as_boolean().is_(True))))
                if args.preview and existing:
                    ids = existing
                if args.apply and session.scalar(select(WorkItem.id).where(
                    WorkItem.kind == KIND, WorkItem.payload["copy_version"].as_string() == COPY_VERSION,
                    WorkItem.payload["preview"].as_boolean().is_(True), WorkItem.status == "running",
                    WorkItem.expires_at > now,
                ).limit(1)):
                    parser.error("a preview is still running")
                if args.reviewed:
                    _apply_review(session, args.reviewed, now)
                failed = set(session.scalars(select(WorkItem.identity).where(
                    WorkItem.kind == KIND, WorkItem.status == "failed", WorkItem.error == "invalid_editorial_copy",
                    WorkItem.payload["copy_version"].as_string() == COPY_VERSION))) if args.repair_failed else None
                queue_rewrites(session, [item for item in _targets(session, now) if item.id in ids
                                         and (failed is None or work_key(item) in failed)
                                         and not has_manual_summary(session, item.id)
                                         and (item.editorial_data or {}).get("copy_version") != COPY_VERSION],
                               now, preview=args.preview is not None, max_attempts=args.max_attempts,
                               run_key=args.run_key, repair=args.repair_failed)
            recover_receipts(engine, now)
            worker = Worker(engine, _client, budget=budget)

            def run():
                while worker.run_one(args.run_key, kinds={KIND}, preview=args.preview is not None):
                    pass

            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                for future in [executor.submit(run) for _ in range(args.workers)]:
                    future.result()
        with Session(read_engine) as session:
            report = _report(session, _targets(session, now_utc()), args.run_key)
        print(json.dumps(report, ensure_ascii=False))
    finally:
        read_engine.dispose()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
