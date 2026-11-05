"""Seed the longitudinal audit database from already fetched, local baseline JSON."""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from .db import make_engine
from .pipeline import Candidate, MockSourceAdapter
from .source_collection import SOURCES, collect
from .source_validation import _migrate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data/source-validation")
    args = parser.parse_args()
    root = args.input_dir.resolve()
    database = root / "observation.db"
    output = root / "observation-seed.json"
    if database.exists() or output.exists():
        parser.error("observation database or seed record already exists")
    latest: dict[str, tuple[Path, dict]] = {}
    for path in sorted(root.glob("baseline-*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        for row in report["sources"]:
            if row["error_code"] is None and row["items"]:
                latest[row["source"]] = path, row
    if set(latest) != set(SOURCES):
        parser.error(f"baseline missing sources: {sorted(set(SOURCES) - set(latest))}")
    url = f"sqlite:///{database.as_posix()}"
    _migrate(url)
    engine = make_engine(url)
    results = []
    try:
        with Session(engine) as session:
            for slug in SOURCES:
                path, row = latest[slug]
                candidates = [Candidate(
                    url=item["url"], title=item["title"], body=item["body"],
                    summary=item["summary"],
                    published_at=datetime.fromisoformat(item["published_at"])
                    if item["published_at"] else None,
                    published_date=date.fromisoformat(item["published_date"])
                    if item["published_date"] else None,
                    language=SOURCES[slug].language,
                ) for item in row["items"]]
                first = collect(session, SOURCES[slug], MockSourceAdapter(candidates))
                repeat = collect(session, SOURCES[slug], MockSourceAdapter(candidates))
                results.append({"source": slug, "baseline_file": path.name,
                                "first": first["discoveries"], "repeat": repeat["discoveries"],
                                "public": first["current_public"]})
    finally:
        engine.dispose()
    output.write_text(json.dumps({"database": str(database), "sources": results},
                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(output))


if __name__ == "__main__":
    main()
