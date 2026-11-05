from __future__ import annotations

import json
from datetime import date

from bluepulse_backend.source_quality_summary import summarize


def test_quality_density_counts_unique_urls_and_only_reviewed_topics(tmp_path):
    url = "https://www.nist.gov/news-events/news/2026/10/test"
    item = {"url": url, "title": "Policing test", "body_chars": 1000,
            "published_at": "2026-10-20T12:00:00+00:00", "published_date": None}
    for day in ("2026-11-01", "2026-11-02"):
        report = {"run_at": f"{day}T120000+0800", "sources": [{
            "source": "nist-public-safety", "diagnostics": {"feed_items": 40},
            "items": [item, {**item, "url": url + "-unreviewed"}],
        }]}
        (tmp_path / f"baseline-{day}.json").write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "review-2026-11-01.json").write_text(json.dumps({
        "run_at": "2026-11-01T120000+0800", "items": [{"source": "nist-public-safety",
        "url": url, "topic_fit": "direct", "evidence_sufficient": True,
        "editorial_fit": False, "page_checked": True}]}), encoding="utf-8")
    (tmp_path / "review-2026-11-02.json").write_text(json.dumps({
        "run_at": "2026-11-02T120000+0800", "items": [{"source": "nist-public-safety",
        "url": url, "topic_fit": None, "evidence_sufficient": None,
        "editorial_fit": True, "page_checked": False}]}), encoding="utf-8")
    rows, details = summarize(tmp_path, as_of=date(2026, 11, 2))
    row = next(row for row in rows if row["source"] == "nist-public-safety")
    assert (row["unique_sampled"], row["reviewed"], row["direct"]) == (2, 1, 1)
    assert (row["direct_evidence"], row["recent_direct_60d"], row["editorial_fit"]) == (1, 1, 1)
    assert row["original_pages_checked"] == 1
    assert len([item for item in details if item["source"] == "nist-public-safety"]) == 2
    daily, _ = summarize(tmp_path, as_of=date(2026, 11, 2),
                         run_from=date(2026, 11, 2), run_to=date(2026, 11, 2))
    assert next(row for row in daily if row["source"] == "nist-public-safety")["reviewed"] == 1
    new_daily, _ = summarize(tmp_path, as_of=date(2026, 11, 2),
                             run_from=date(2026, 11, 2), run_to=date(2026, 11, 2),
                             new_only=True)
    assert next(row for row in new_daily if row["source"] == "nist-public-safety")["reviewed"] == 0
    empty, _ = summarize(tmp_path, as_of=date(2026, 11, 2),
                         run_from=date(2026, 11, 3))
    assert next(row for row in empty if row["source"] == "nist-public-safety")["reviewed"] == 0
