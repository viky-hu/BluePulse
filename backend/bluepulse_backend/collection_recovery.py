"""Queue verified historical source evidence, or replay collection in an isolated database."""
import argparse
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from sqlalchemy import select
from sqlalchemy.orm import Session

from .collection_version import collection_identity, sqlite_database_path
from .db import database_url, make_engine
from .editorial_models import WorkItem
from .models import Source, SourceRun, now_utc
from .pipeline import Candidate, canonical_url
from .source_audit import _verified_pages, window_status
from .source_collection import SOURCES
from .work_queue import enqueue, serialized


def manifest_rows(path, now):
    data = json.loads(path.read_text(encoding="utf-8"))
    start, through = data["window_from"], data["window_through"]
    if datetime.fromisoformat(through) > now:
        raise ValueError("audit_cutoff_in_future")
    rows, hashes = {}, {}
    for row in data["items"]:
        slug = row["source"]
        url = canonical_url(row["url"], [SOURCES[slug].host])
        evidence_key = (slug, row["evidence_url"], row["evidence_sha256"], row["evidence_file"])
        if evidence_key not in hashes:
            hashes[evidence_key] = _verified_pages([dict(zip(
                ("source", "url", "sha256", "file"), evidence_key, strict=True), status=200)], path.parent)
        if not hashes[evidence_key]:
            raise ValueError("invalid_audit_evidence")
        dates = {**row, "published_at": row["updated_at"]} if row.get("correction") else row
        if window_status(dates, start, through) != "in_window":
            raise ValueError("audit_item_outside_window")
        rows.setdefault((slug, url), {**row, "url": url, "window_from": start, "window_through": through})
    return rows


def queue_manifest(engine, path, now, *, apply=False, recheck=False):
    groups = defaultdict(list)
    recheck_version = collection_identity()["collection_rule_version"] if recheck else None
    for (slug, _), item in manifest_rows(path, now).items():
        if recheck_version:
            item["recheck_version"] = recheck_version
        groups[slug].append(item)
    jobs = []
    with (serialized(engine) if apply else Session(engine)) as session:
        for slug, rows in groups.items():
            source = session.scalar(select(Source).where(Source.slug == slug))
            if not source or not source.enabled or source.allowed_hosts != [SOURCES[slug].host]:
                raise ValueError("audit_source_unavailable")
            rows.sort(key=lambda row: row["url"])
            for start in range(0, len(rows), 25):
                batch = rows[start:start + 25]
                digest = sha256(json.dumps(batch, sort_keys=True).encode()).hexdigest()
                identity = f"{slug}:audit:{digest}"
                exists = session.scalar(select(WorkItem.id).where(WorkItem.kind == "collect", WorkItem.identity == identity))
                if exists:
                    continue
                jobs.append({"source": slug, "items": len(batch)})
                if apply:
                    enqueue(session, "collect", identity, {"slug": slug, "historical": True, "audit_items": batch}, now)
    return {"items": sum(map(len, groups.values())), "queued": len(jobs), "batches": jobs, "applied": apply}


def audit_candidates(rows, language):
    for row in rows:
        yield Candidate(url=row["url"], title=row.get("title") or "", language=language,
                        published_at=datetime.fromisoformat(row["published_at"]) if row.get("published_at") else None,
                        published_date=date.fromisoformat(row["published_date"]) if row.get("published_date") else None,
                        source_updated_at=datetime.fromisoformat(row["updated_at"]) if row.get("updated_at") else None)


def _replay(baseline, output, slugs, evidence=None, *, manifest_only=False):
    from concurrent.futures import ThreadPoolExecutor
    from time import sleep

    from .worker import WORKER_LANES, Worker, _client, _dispatch

    if (baseline.resolve() == output.resolve() or output.resolve() == sqlite_database_path(database_url())
            or output.is_symlink() or output.exists()):
        raise ValueError("replay_requires_new_isolated_database")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb"), closing(sqlite3.connect(baseline.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(output)) as target:
            source.backup(target)
    engine = make_engine(f"sqlite:///{output.resolve().as_posix()}")
    worker = Worker(engine, _client, collect_enabled=True, slugs=slugs)
    started = now_utc()
    try:
        with serialized(engine) as session:
            for job in session.scalars(select(WorkItem).where(WorkItem.kind.in_(("collect", "extract")),
                                                            WorkItem.status.in_(("pending", "running")))):
                job.status, job.error = "failed", "baseline_work_excluded"
            if not manifest_only:
                worker._schedule_collection(session, worker.clock(), recover=True)
        if evidence:
            queue_manifest(engine, evidence, now_utc(), apply=True)
        active = [set() for _ in WORKER_LANES]
        with ThreadPoolExecutor() as executor:
            while True:
                _dispatch(worker, executor, active)
                if not any(active):
                    break
                sleep(.25)
        with Session(engine) as session:
            deferred = [{"kind": job.kind, "due_at": job.due_at, "error": job.error}
                        for job in session.scalars(select(WorkItem).where(
                            WorkItem.kind.in_(("collect", "extract")),
                            WorkItem.status.in_(("pending", "running"))
                        ).order_by(WorkItem.due_at))]
            return {"database": str(output), "deferred": deferred, "runs": [{"source": slug, "status": run.status,
                     "error": run.error_code, "metrics": run.fetch_metrics}
                    for run, slug in session.execute(select(SourceRun, Source.slug).join(Source,
                        SourceRun.source_id == Source.id).where(SourceRun.started_at >= started))]}
    finally:
        engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    replay = commands.add_parser("replay")
    replay.add_argument("--baseline", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    replay.add_argument("--source", choices=sorted(SOURCES), action="append")
    replay.add_argument("--manifest", type=Path)
    replay.add_argument("--manifest-only", action="store_true")
    enqueue_command = commands.add_parser("queue")
    enqueue_command.add_argument("--manifest", type=Path, required=True)
    enqueue_command.add_argument("--apply", action="store_true")
    enqueue_command.add_argument("--recheck", action="store_true", help="Recheck evidence once with the current collector version")
    args = parser.parse_args(argv)
    if args.action == "replay":
        if args.manifest_only and not args.manifest:
            parser.error("--manifest-only requires --manifest")
        result = _replay(args.baseline, args.output, args.source, args.manifest, manifest_only=args.manifest_only)
    else:
        engine = make_engine()
        try:
            result = queue_manifest(engine, args.manifest, now_utc(), apply=args.apply, recheck=args.recheck)
        finally:
            engine.dispose()
    print(json.dumps(result, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
