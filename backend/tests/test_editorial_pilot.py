from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.db import make_engine
from bluepulse_backend.editorial_pilot import prepare, record
from bluepulse_backend.models import Material, Source


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_offline_pilot_binds_review_to_revision_and_keeps_publication_closed(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    output = tmp_path / "output"
    url = "https://www.police.gov.sg/Media-Hub/Police-Life/2026/11/example"
    body = "First paragraph with specific pilot fact.\n" + "Evidence detail. " * 45
    item = {"url": url, "title": "Police technology pilot", "body": body,
            "summary": None, "body_chars": len(body), "published_at": None,
            "published_date": "2026-11-01"}
    write(inputs / "baseline-2026-11-01T120000+0800.json", {
        "run_at": "2026-11-01T120000+0800", "sources": [{
            "source": "spf-police-life", "diagnostics": {}, "items": [item]}]})
    write(inputs / "review-2026-11-01T120000+0800.json", {
        "items": [{"source": "spf-police-life", "url": url, "topic_fit": "direct",
                   "evidence_sufficient": True, "editorial_fit": True,
                   "page_checked": False}]})
    selection = tmp_path / "selection.json"
    write(selection, {"items": [{"source": "spf-police-life", "url": url,
                                 "claims": [{"id": "fact", "claim": "A pilot fact",
                                             "anchor": "specific pilot fact"}]}]})

    packet = prepare(selection, inputs, output)
    assert len(packet["items"]) == 1
    assert packet["items"][0]["claims"][0]["paragraph"].startswith("First paragraph")
    assert packet["ingest"][0]["first"]["new"] == 1
    assert packet["ingest"][0]["replay"]["duplicate"] == 1
    engine = make_engine(f"sqlite:///{(output / 'editorial-pilot.db').as_posix()}")
    with Session(engine) as session:
        material = session.scalar(select(Material))
        source = session.scalar(select(Source))
        assert material.state == "analysis_pending" and material.public is False
        assert source.excerpt_allowed is False and source.full_text_allowed is False
    engine.dispose()

    form_path = output / "review-template.json"
    form = json.loads(form_path.read_text(encoding="utf-8"))
    assert record(output, form_path)["counts"]["pending"] == 1
    incomplete = tmp_path / "incomplete.json"
    form["items"][0].update(decision="advance", reviewer="human reviewer")
    write(incomplete, form)
    with pytest.raises(ValueError, match="advance_requires_page_and_claim_checks"):
        record(output, incomplete)
    form["items"][0].update(decision="advance", reviewer="human reviewer",
                             source_page_checked=True, claim_checks={"fact": True})
    approved = tmp_path / "approved.json"
    write(approved, form)
    result = record(output, approved)
    assert result["counts"]["advance"] == 1 and result["publications"] == 0
    assert result["source_yield"]["spf-police-life"]["advance"] == 1
    form["items"][0]["content_hash"] = "stale"
    write(approved, form)
    with pytest.raises(ValueError, match="review_revision_mismatch"):
        record(output, approved)
    form["items"][0]["content_hash"] = packet["items"][0]["content_hash"]
    write(approved, form)
    engine = make_engine(f"sqlite:///{(output / 'editorial-pilot.db').as_posix()}")
    with Session(engine) as session:
        material = session.scalar(select(Material))
        material.revision += 1
        session.commit()
    engine.dispose()
    with pytest.raises(ValueError, match="material_changed_or_permission_gate_failed"):
        record(output, approved)
