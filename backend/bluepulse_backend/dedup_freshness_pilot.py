"""Replay the reviewed 60 entrance samples to audit same-copy and age decisions."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import make_engine
from .models import Discovery, Material
from .pipeline import Candidate, MockSourceAdapter, canonical_url
from .source_collection import SOURCES, collect
from .source_validation import _migrate


BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = BACKEND / "data/source-validation"
DEFAULT_OUTPUT = BACKEND / "data/dedup-freshness-pilot/2026-11-03"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(input_dir: Path, output_dir: Path) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output_directory_must_be_empty")
    quality = _read(input_dir / "source-quality-2026-11-02.json")
    wanted = {(row["source"], canonical_url(row["url"], [SOURCES[row["source"]].host]))
              for row in quality["items"]}
    if len(wanted) != 60 or {slug for slug, _ in wanted} != set(SOURCES):
        raise ValueError("expected_60_samples_from_15_sources")
    snapshots = {}
    for path in sorted(input_dir.glob("baseline-*.json")):
        for source in _read(path).get("sources", []):
            slug = source["source"]
            for item in source.get("items", []):
                key = slug, canonical_url(item["url"], [SOURCES[slug].host])
                if key in wanted and (key not in snapshots or
                                      len(item.get("body") or "") > len(snapshots[key].get("body") or "")):
                    snapshots[key] = item
    if set(snapshots) != wanted:
        raise ValueError("reviewed_sample_missing_archived_body")
    output_dir.mkdir(parents=True, exist_ok=True)
    database = output_dir / "pilot.db"
    address = f"sqlite:///{database.as_posix()}"
    _migrate(address)
    engine = make_engine(address)
    try:
        with Session(engine) as session:
            for slug, spec in SOURCES.items():
                candidates = []
                for key, item in snapshots.items():
                    if key[0] != slug:
                        continue
                    candidates.append(Candidate(
                        url=item["url"], title=item["title"], body=item.get("body"),
                        summary=item.get("summary"),
                        published_at=datetime.fromisoformat(item["published_at"])
                        if item.get("published_at") else None,
                        published_date=date.fromisoformat(item["published_date"])
                        if item.get("published_date") else None,
                        language=spec.language))
                collect(session, spec, MockSourceAdapter(candidates))
            materials = session.scalars(select(Material).order_by(Material.source_url)).all()
            by_id = {row.id: row for row in materials}
            cross_entry = defaultdict(set)
            for material_id, source_id in session.execute(select(Discovery.material_id, Discovery.source_id)):
                cross_entry[material_id].add(source_id)
            same_url = [by_id[material_id].canonical_url for material_id, source_ids in cross_entry.items()
                        if material_id in by_id and len(source_ids) > 1]
            copies = [{"original_url": by_id[row.duplicate_of_id].source_url,
                       "mirror_url": row.source_url, "reason": row.duplicate_reason,
                       "published_date": (row.published_date or row.published_at.date()).isoformat()}
                      for row in materials if row.duplicate_of_id]
            rows = [{"source": row.source.slug, "url": row.source_url,
                     "published_at": row.published_at.isoformat() if row.published_at else None,
                     "published_date": row.published_date.isoformat() if row.published_date else None,
                     "first_seen_at": row.first_seen_at.isoformat(),
                     "timeline_kind": row.timeline_kind, "duplicate_of_url":
                     by_id[row.duplicate_of_id].source_url if row.duplicate_of_id else None}
                    for row in materials]
            counts = dict(Counter(row.timeline_kind for row in materials))
            by_source = {slug: dict(Counter(row.timeline_kind for row in materials
                                            if row.source.slug == slug)) for slug in SOURCES}
            report = {"sample": "2026-11-01_to_2026-11-02_archived_reviewed",
                      "run_at": datetime.now(UTC).isoformat(), "entrances": len(SOURCES),
                      "entrance_samples": len(wanted), "materials_after_url_dedup": len(materials),
                      "cross_entrance_same_url": sorted(same_url),
                      "cross_url_same_copy": copies,
                      "independent_copies": len(materials) - len(copies),
                      "timeline": counts, "timeline_by_material_owner": by_source,
                      "date_only": sum(row.published_date is not None and row.published_at is None
                                       for row in materials),
                      "unknown_date": sum(row.published_sort_at is None for row in materials),
                      "production_writes": 0, "model_calls": 0, "public": session.scalar(
                          select(func.count()).select_from(Material).where(Material.public.is_(True))),
                      "database": str(database)}
    finally:
        engine.dispose()
    (output_dir / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    with (output_dir / "materials.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run(args.input_dir, args.output_dir)
    print(json.dumps({key: report[key] for key in (
        "entrances", "entrance_samples", "materials_after_url_dedup", "independent_copies",
        "timeline", "date_only", "unknown_date", "public")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
