from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.cli import TOPICS, sync_taxonomy
from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.full_day_pilot import run
from bluepulse_backend.models import Topic
from bluepulse_backend.source_collection import SOURCES


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_taxonomy_registers_frontend_seven_and_preserves_legacy_rows(tmp_path):
    address = f"sqlite:///{(tmp_path / 'taxonomy.db').as_posix()}"
    engine = make_engine(address)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Topic(slug="policing", name_zh="旧分类", name_en="Legacy"))
        session.commit()
    sync_taxonomy(address)
    with Session(engine) as session:
        rows = session.scalars(select(Topic)).all()
        assert {row.slug for row in rows if row.enabled} == {row[0] for row in TOPICS}
        assert next(row for row in rows if row.slug == "policing").enabled is False
    engine.dispose()


def test_full_day_all_15_sources_processed_without_publication(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    seed = {"sources": []}
    reviews = {"run_at": "2026-11-01T120000+0800", "items": []}
    categories = {"sample_day": "2026-11-01", "items": []}
    for slug, spec in SOURCES.items():
        first = f"https://{spec.host}/pilot/{slug}/direct"
        second = f"https://{spec.host}/pilot/{slug}/off"
        filename = f"baseline-2026-11-01-{slug}.json"
        write(inputs / filename, {"run_at": "2026-11-01T120000+0800", "sources": [{
            "source": slug, "error_code": None,
            "items": [{"url": url, "title": f"{slug} {kind}",
                       "body": f"Evidence for {kind}", "summary": None,
                       "published_at": None, "published_date": "2026-11-01"}
                      for url, kind in ((first, "direct"), (second, "off"))]}]})
        seed["sources"].append({"source": slug, "baseline_file": filename})
        for url, kind in ((first, "direct"), (second, "off")):
            reviews["items"].append({"source": slug, "url": url, "topic_fit": kind,
                                     "evidence_sufficient": True,
                                     "editorial_fit": kind == "direct"})
        categories["items"].append({"source": slug, "url": first,
                                    "primary_topic": "practice", "reason": "Fixture evidence."})
    write(inputs / "observation-seed.json", seed)
    write(inputs / "review-2026-11-01Tmanual+0800.json", reviews)
    category_file = tmp_path / "categories.json"
    write(category_file, categories)
    output = tmp_path / "output"
    report = run(inputs, category_file, output)
    assert report["source_count"] == 15 and report["item_count"] == 30
    assert report["processing"] == {"applied": 30, "failed": 0, "unknown": 0}
    assert report["dispositions"] == {"ready_for_review": 15, "reject": 15}
    assert report["database_counts"]["public"] == 0
    assert report["real_api"]["articles"] == 0
    assert report["synthetic_api"]["practice_items"] == 1
    assert all(row["first"] == {"new": 2} and row["replay"] == {"duplicate": 2}
               for row in report["source_runs"])
    assert (output / "review.html").exists()
    with pytest.raises(ValueError, match="output_directory_must_be_empty"):
        run(inputs, category_file, output)
