"""Offline first-batch editorial review. Never analyzes or publishes materials."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import make_engine
from .models import Material
from .pipeline import Candidate, MockSourceAdapter, canonical_url
from .source_collection import SOURCES, collect
from .source_quality_summary import summarize
from .source_validation import _migrate


BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_SELECTION = BACKEND / "config/editorial-pilot-4.json"
DEFAULT_INPUT = BACKEND / "data/source-validation"
DEFAULT_OUTPUT = BACKEND / "data/editorial-pilot/first-batch"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
                    encoding="utf-8")


def _latest_snapshots(directory: Path) -> dict[tuple[str, str], tuple[str, dict]]:
    latest = {}
    for path in sorted(directory.glob("baseline-*.json")):
        for source in _read(path)["sources"]:
            slug = source["source"]
            for item in source["items"]:
                url = canonical_url(item["url"], [SOURCES[slug].host])
                latest[(slug, url)] = (path.name, item)
    return latest


def _candidate(slug: str, item: dict) -> Candidate:
    return Candidate(
        url=item["url"], title=item["title"], body=item.get("body"),
        summary=item.get("summary"),
        published_at=datetime.fromisoformat(item["published_at"])
        if item.get("published_at") else None,
        published_date=date.fromisoformat(item["published_date"])
        if item.get("published_date") else None,
        language=SOURCES[slug].language,
    )


def _passage(body: str, anchor: str) -> dict:
    offset = body.casefold().find(anchor.casefold())
    if offset < 0:
        raise ValueError(f"claim_anchor_missing:{anchor}")
    start = body.rfind("\n", 0, offset) + 1
    end = body.find("\n", offset)
    if end < 0:
        end = len(body)
    return {"offset": offset, "paragraph": body[start:end][:1000]}


def prepare(selection_file: Path, input_dir: Path, output_dir: Path) -> dict:
    """Import only selected archived candidates into a fresh isolated database."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output_directory_must_be_empty")
    selection = _read(selection_file)["items"]
    snapshots = _latest_snapshots(input_dir)
    _, details = summarize(input_dir, as_of=datetime.now(UTC).date())
    reviews = {(item["source"], item["url"]): item for item in details}
    prepared = []
    seen = set()
    for requested in selection:
        slug = requested["source"]
        if slug not in SOURCES:
            raise ValueError(f"unknown_source:{slug}")
        url = canonical_url(requested["url"], [SOURCES[slug].host])
        key = slug, url
        if url in seen:
            raise ValueError(f"duplicate_selection:{url}")
        seen.add(url)
        if key not in snapshots:
            raise ValueError(f"snapshot_missing:{url}")
        review = reviews.get(key, {})
        if (review.get("topic_fit") != "direct" or review.get("evidence_sufficient") is not True
                or review.get("editorial_fit") is not True):
            raise ValueError(f"prescreen_missing:{url}")
        baseline, item = snapshots[key]
        body = item.get("body") or ""
        if len(body.strip()) < 500 or not item.get("published_date") and not item.get("published_at"):
            raise ValueError(f"body_or_date_insufficient:{url}")
        claims = [{"id": claim["id"], "claim": claim["claim"],
                   "anchor": claim["anchor"], **_passage(body, claim["anchor"])}
                  for claim in requested["claims"]]
        if not claims or len({claim["id"] for claim in claims}) != len(claims):
            raise ValueError(f"invalid_claims:{url}")
        prepared.append({"source": slug, "url": url, "baseline": baseline,
                         "item": item, "review": review, "claims": claims})
    if not prepared:
        raise ValueError("selection_empty")

    output_dir.mkdir(parents=True, exist_ok=True)
    database = output_dir / "editorial-pilot.db"
    _migrate(f"sqlite:///{database.as_posix()}")
    engine = make_engine(f"sqlite:///{database.as_posix()}")
    outcomes = []
    try:
        with Session(engine) as session:
            grouped = defaultdict(list)
            for entry in prepared:
                grouped[entry["source"]].append(_candidate(entry["source"], entry["item"]))
            for slug, candidates in grouped.items():
                first = collect(session, SOURCES[slug], MockSourceAdapter(candidates))
                replay = collect(session, SOURCES[slug], MockSourceAdapter(candidates))
                outcomes.append({"source": slug, "first": first["discoveries"],
                                 "replay": replay["discoveries"]})
            packet_items = []
            for entry in prepared:
                material = session.scalar(select(Material).where(Material.canonical_url == entry["url"]))
                if material is None or material.public or material.state != "analysis_pending":
                    raise ValueError("isolation_or_ingest_gate_failed")
                if material.source.excerpt_allowed or material.source.full_text_allowed:
                    raise ValueError("source_permission_gate_failed")
                packet_items.append({
                    "material_id": material.id, "revision": material.revision,
                    "content_hash": material.content_hash, "source": entry["source"],
                    "url": entry["url"], "title": material.source_title,
                    "published_at": entry["item"].get("published_at"),
                    "published_date": entry["item"].get("published_date"),
                    "body": material.source_body, "body_chars": len(material.source_body or ""),
                    "baseline": entry["baseline"],
                    "prescreen": {field: entry["review"].get(field) for field in
                                  ("topic_fit", "evidence_sufficient", "editorial_fit", "page_checked")},
                    "claims": entry["claims"], "state": material.state,
                    "public": material.public,
                    "excerpt_allowed": material.source.excerpt_allowed,
                    "full_text_allowed": material.source.full_text_allowed,
                })
    finally:
        engine.dispose()
    fingerprint = hashlib.sha256(json.dumps(
        [(item["source"], item["url"], item["content_hash"])
         for item in packet_items], ensure_ascii=False).encode()).hexdigest()
    packet = {"schema_version": 1, "packet_id": fingerprint,
              "created_at": datetime.now(UTC).isoformat(),
              "database": str(database), "items": packet_items, "ingest": outcomes,
              "notice": "Internal evidence only. No model call or publication."}
    template = {"schema_version": 1, "packet_id": fingerprint,
                "items": [{"material_id": item["material_id"], "revision": item["revision"],
                           "content_hash": item["content_hash"], "url": item["url"],
                           "decision": "pending", "reviewer": "", "reason": "",
                           "source_page_checked": False,
                           "claim_checks": {claim["id"]: False for claim in item["claims"]},
                           "rights_note": ""}
                          for item in packet_items]}
    _write(output_dir / "packet.json", packet)
    _write(output_dir / "review-template.json", template)
    return packet


def record(output_dir: Path, review_file: Path) -> dict:
    """Validate version-bound editorial decisions; never modify publication fields."""
    packet = _read(output_dir / "packet.json")
    form = _read(review_file)
    if form.get("packet_id") != packet["packet_id"] or form.get("schema_version") != 1:
        raise ValueError("packet_mismatch")
    entries = form.get("items")
    expected = {item["material_id"]: item for item in packet["items"]}
    if not isinstance(entries, list) or len(entries) != len(expected):
        raise ValueError("review_item_count_mismatch")
    database = output_dir / "editorial-pilot.db"
    engine = make_engine(f"sqlite:///{database.as_posix()}")
    results = []
    try:
        with Session(engine) as session:
            seen = set()
            for entry in entries:
                material_id = entry.get("material_id")
                if material_id in seen or material_id not in expected:
                    raise ValueError("review_item_identity_mismatch")
                seen.add(material_id)
                source = expected[material_id]
                material = session.get(Material, material_id)
                if (material is None or material.canonical_url != source["url"]
                        or material.revision != source["revision"]
                        or material.content_hash != source["content_hash"]
                        or material.public or material.source.excerpt_allowed
                        or material.source.full_text_allowed):
                    raise ValueError("material_changed_or_permission_gate_failed")
                if (entry.get("url") != source["url"] or entry.get("revision") != source["revision"]
                        or entry.get("content_hash") != source["content_hash"]):
                    raise ValueError("review_revision_mismatch")
                decision = entry.get("decision")
                if decision not in {"pending", "advance", "hold", "reject"}:
                    raise ValueError("invalid_decision")
                checks = entry.get("claim_checks")
                claim_ids = {claim["id"] for claim in source["claims"]}
                if not isinstance(checks, dict) or set(checks) != claim_ids or any(
                        type(value) is not bool for value in checks.values()):
                    raise ValueError("invalid_claim_checks")
                if decision != "pending" and not str(entry.get("reviewer") or "").strip():
                    raise ValueError("reviewer_required")
                if decision == "advance" and (entry.get("source_page_checked") is not True
                                               or not all(checks.values())):
                    raise ValueError("advance_requires_page_and_claim_checks")
                if decision in {"hold", "reject"} and not str(entry.get("reason") or "").strip():
                    raise ValueError("reason_required")
                results.append({"material_id": material_id, "url": source["url"],
                                "source": source["source"], "revision": source["revision"],
                                "content_hash": source["content_hash"],
                                "decision": decision, "reviewer": entry.get("reviewer") or "",
                                "reason": entry.get("reason") or "",
                                "rights_note": entry.get("rights_note") or "",
                                "source_page_checked": entry.get("source_page_checked") is True,
                                "claim_checks": checks})
    finally:
        engine.dispose()
    counts = {value: sum(item["decision"] == value for item in results)
              for value in ("pending", "advance", "hold", "reject")}
    source_yield = {}
    for slug in sorted({item["source"] for item in results}):
        source_items = [item for item in results if item["source"] == slug]
        source_yield[slug] = {"reviewed": len(source_items),
                              **{value: sum(item["decision"] == value for item in source_items)
                                 for value in ("pending", "advance", "hold", "reject")}}
    result = {"schema_version": 1, "packet_id": packet["packet_id"],
              "recorded_at": datetime.now(UTC).isoformat(), "counts": counts,
              "source_yield": source_yield,
              "items": results, "publications": 0,
              "notice": "Internal editorial decision; not a publication approval."}
    destination = output_dir / ("review-result-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    result["record_file"] = str(destination)
    _write(destination, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "record"))
    parser.add_argument("--selection-file", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--review-file", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        result = prepare(args.selection_file, args.input_dir, args.output_dir)
        print(json.dumps({"packet_id": result["packet_id"], "items": len(result["items"]),
                          "output_dir": str(args.output_dir), "publications": 0}, ensure_ascii=False))
    else:
        if args.review_file is None:
            parser.error("record requires --review-file")
        result = record(args.output_dir, args.review_file)
        print(json.dumps({"counts": result["counts"], "publications": 0,
                          "record_file": result["record_file"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
