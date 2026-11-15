"""Reconcile independently captured source evidence against a SQLite snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .pipeline import canonical_url
from .source_collection import SOURCES

AUDITABLE_STATUSES = {"stored", "revised", "duplicate", "duplicate_listing", "withdrawn",
                     "out_of_scope", "out_of_window"}


def _instant(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def window_status(item, start, through):
    first, last = _instant(start), _instant(through)
    if first is None or last is None or first >= last:
        raise ValueError("The audit window requires two increasing offset-aware timestamps")
    stamp = item.get("updated_at") if item.get("correction") else None
    stamp = stamp or item.get("published_at")
    if stamp:
        when = _instant(stamp)
        if when is None:
            return "date_unverified"
    elif item.get("published_date"):
        try:
            source_day = date.fromisoformat(item["published_date"])
            offset = item.get("source_offset") or "+08:00"
            when = _instant(f"{source_day}T00:00:00{offset}")
        except (TypeError, ValueError):
            return "date_unverified"
        if when is None:
            return "date_unverified"
        end_of_day = when + timedelta(days=1)
        if end_of_day <= first or when > last:
            return "out_of_window"
        if when < first or end_of_day > last:
            return "date_cutoff_unverified"
    else:
        return "date_unverified"
    return "in_window" if first <= when <= last else "out_of_window"


def _canonical(source, url):
    spec = SOURCES.get(source)
    if spec and isinstance(url, str):
        try:
            return canonical_url(url, [spec.host])
        except ValueError:
            pass
    return None


def _verified_pages(pages, directory):
    verified = {}
    directory = directory.resolve()
    hashes = {}
    for row in pages:
        path = row.get("file")
        source, url = row.get("source"), row.get("url")
        # Additional official archives and same-provider subdomains can supply evidence
        # for an article whose own URL still has to pass the Pulse source policy.
        try:
            origin = urlsplit(url or "")
            port = origin.port
        except ValueError:
            continue
        host = SOURCES[source].host.removeprefix("www.") if source in SOURCES else None
        if (host is None or origin.scheme != "https" or not origin.hostname
                or origin.username or origin.password or port not in (None, 443)
                or not (origin.hostname == host or origin.hostname.endswith("." + host))
                or row.get("status") != 200 or not isinstance(path, str)):
            continue
        resolved = (directory / path).resolve()
        if not resolved.is_relative_to(directory) or not resolved.is_file():
            continue
        if resolved not in hashes:
            hashes[resolved] = hashlib.sha256(resolved.read_bytes()).hexdigest()
        if hashes[resolved] == row.get("sha256"):
            verified[(source, url, row["sha256"])] = resolved.relative_to(directory).as_posix()
    return verified


def _snapshot(path):
    uri = path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        materials = {}
        for row in db.execute("""
            SELECT materials.id, sources.slug AS source, canonical_url, source_url, revision,
                   published_at, published_date, duplicate_of_id, collection_state, body_status, public, withdrawn
              FROM materials JOIN sources ON sources.id = materials.source_id
        """):
            data = dict(row)
            for url in (data["canonical_url"], data["source_url"]):
                if key := _canonical(data["source"], url):
                    materials[(data["source"], key)] = data
        discoveries = {}
        for row in db.execute("""
            SELECT sources.slug AS source, discoveries.url, discoveries.material_id, outcome, reason_code, discovered_at
              FROM discoveries JOIN sources ON sources.id = discoveries.source_id
             ORDER BY discovered_at, discoveries.id
        """):
            if key := _canonical(row["source"], row["url"]):
                discoveries[(row["source"], key)] = dict(row)
    return materials, discoveries


def _disposition(item, evidence, verified, storage, discovery, prior):
    page = (item["source"], item.get("evidence_url"), item.get("evidence_sha256"))
    if page not in verified:
        return "evidence_unverified"
    if item.get("scope") == "duplicate_listing" and item.get("reason"):
        return "duplicate_listing"
    if item.get("scope") == "out_of_scope" and item.get("reason"):
        return "out_of_scope"
    when = window_status(item, evidence["from"], evidence["through"])
    if when != "in_window":
        return when
    if not _canonical(item["source"], item["url"]):
        return "source_url_unrecognized"
    if item.get("scope") != "in_scope":
        return "scope_pending"
    if storage is None:
        if discovery is not None and discovery["reason_code"]:
            return "admission_or_parse_failure"
        return "missing"
    if storage["withdrawn"]:
        return "withdrawn"
    if storage["duplicate_of_id"] or storage.get("source", item["source"]) != item["source"]:
        return "duplicate"
    if storage["collection_state"] == "pending" or storage["body_status"] != "full_text":
        return "detail_pending"
    if item.get("correction"):
        observed = _instant(item.get("updated_at"))
        captured = _instant(item.get("baseline_revision_captured_at"))
        if observed and captured and captured >= observed:
            return "revised"
        if prior is None or storage["revision"] <= prior["revision"]:
            return "correction_pending"
        return "revised"
    if storage["published_at"] is None and storage["published_date"] is None:
        return "stored_date_missing"
    actual = datetime.fromisoformat(storage["published_at"]) if storage["published_at"] else None
    if actual is not None and actual.tzinfo is None:
        actual = actual.replace(tzinfo=timezone.utc)
    if item.get("published_at"):
        cutoff = _instant(item["published_at"])
        if actual and item.get("precision") == "minute":
            actual = actual.replace(second=0, microsecond=0)
        matches = cutoff == actual if actual else cutoff.date().isoformat() == storage["published_date"]
        if not matches:
            return "stored_date_differs"
    elif expected_day := item.get("published_date"):
        offset = item.get("source_offset") or "+08:00"
        zone = _instant(f"{expected_day}T00:00:00{offset}").tzinfo
        stored_day = actual.astimezone(zone).date().isoformat() if actual else storage["published_date"]
        if expected_day != stored_day:
            return "stored_date_differs"
    return "revised" if prior and storage["revision"] > prior["revision"] else "stored"


def reconcile(database: Path, evidence: dict, directory: Path, *, baseline: Path | None = None):
    materials, discoveries = _snapshot(database)
    previous, _ = _snapshot(baseline) if baseline else (materials, discoveries)
    verified = _verified_pages(evidence["pages"], directory)
    items = []
    sources: dict[str, Counter] = defaultdict(Counter)
    owners = {data["id"]: data for data in materials.values()}
    candidates = {}
    for item in evidence["items"]:
        source, url = item["source"], item["url"]
        key = source, _canonical(source, url)
        stored = materials.get(key)
        discovery = discoveries.get(key)
        if stored is None and discovery and discovery["outcome"] == "duplicate":
            stored = owners.get(discovery["material_id"])
        status = _disposition(item, evidence, verified, stored, discovery, previous.get(key))
        items.append({**item, "status": status, "material": stored, "discovery": discovery})
        sources[source][status] += 1
        if status in {"missing", "admission_or_parse_failure", "detail_pending",
                      "stored_date_missing", "stored_date_differs", "correction_pending"}:
            page = (source, item["evidence_url"], item["evidence_sha256"])
            fields = ("source", "url", "title", "published_at", "published_date", "source_offset",
                      "updated_at", "correction", "syndicated_at", "evidence_url", "evidence_sha256", "entry")
            row = {field: item[field] for field in fields if field in item}
            row["evidence_file"] = verified[page]
            candidates.setdefault(key, row)
    entries = []
    for row in evidence["entries"]:
        page = (row["source"], row.get("evidence_url"), row.get("evidence_sha256"))
        if row["status"] == "complete" and page not in verified:
            row = {**row, "status": "partial", "reason": "completion_evidence_unverified"}
        entries.append(row)
    verified_sources = {row["source"] for row in entries if row["status"] == "complete"}
    incomplete_sources = {row["source"] for row in entries if row["status"] != "complete"}
    passed = (set(SOURCES) == verified_sources and not incomplete_sources and
              all(set(counts) <= AUDITABLE_STATUSES for counts in sources.values()))
    report = {"from": evidence["from"], "through": evidence["through"], "passed": passed,
              "entries": entries, "items": items, "sources": dict(sources)}
    manifest = {"window_from": evidence["from"], "window_through": evidence["through"],
                "items": list(candidates.values())}
    return report, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True, help="Read-only snapshot or isolated replay database")
    parser.add_argument("--baseline", type=Path, help="Original snapshot to compare revisions against")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    files = [args.database, args.evidence]
    if args.baseline:
        files.append(args.baseline)
    outputs = [args.report]
    if args.manifest:
        if args.manifest.parent.resolve() != args.evidence.parent.resolve():
            parser.error("Place the manifest next to the evidence manifest so its raw file paths stay valid")
        outputs.append(args.manifest)
    if len({file.resolve() for file in files + outputs}) != len(files + outputs):
        parser.error("Inputs and outputs must be distinct files")
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    report, manifest = reconcile(args.database, evidence, args.evidence.parent, baseline=args.baseline)
    for path, result in zip(outputs, (report, manifest)):
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "sources": report["sources"],
                      "backfill_candidates": len(manifest["items"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
