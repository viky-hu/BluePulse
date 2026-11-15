import hashlib
import sqlite3
from pathlib import Path

import httpx

from bluepulse_backend.source_audit import reconcile


def test_reconcile_distinguishes_reviewed_gap_and_capture_mismatch(tmp_path):
    db_path = tmp_path / "snapshot.db"
    with sqlite3.connect(db_path) as db:
        db.executescript("""
            CREATE TABLE sources (id TEXT, slug TEXT);
            INSERT INTO sources VALUES ('a', 'govuk');
            CREATE TABLE materials (id TEXT, source_id TEXT, canonical_url TEXT, source_url TEXT,
                revision INTEGER, published_at TEXT, published_date TEXT, duplicate_of_id TEXT,
                collection_state TEXT, body_status TEXT, public INTEGER, withdrawn INTEGER);
            CREATE TABLE discoveries (id TEXT, source_id TEXT, material_id TEXT, url TEXT,
                outcome TEXT, reason_code TEXT, discovered_at TEXT);
            INSERT INTO materials VALUES ('1', 'a', 'https://www.gov.uk/present',
                'https://www.gov.uk/present', 3, NULL, '2026-11-09', NULL, 'ready', 'full_text', 1, 0);
        """)
    raw = b"upstream list bytes"
    (tmp_path / "listing.raw").write_bytes(raw)
    page = {"source": "govuk", "url": "https://www.gov.uk/list", "status": 200,
            "file": "listing.raw", "sha256": hashlib.sha256(raw).hexdigest()}
    items = [{"source": "govuk", "url": "https://www.gov.uk/" + slug,
              "evidence_url": page["url"], "evidence_sha256": page["sha256"],
              "published_date": date, "title": slug, "scope": scope}
             for slug, date, scope in (("present", "2026-11-09", "in_scope"),
                                       ("missing", "2026-11-10", "in_scope"),
                                       ("undated", None, "in_scope"),
                                       ("pending", "2026-11-10", "pending"),
                                       ("outside", "2026-11-10", "out_of_scope"))]
    items[-1]["reason"] = "Unrelated subject"
    evidence = {"from": "2026-11-08T00:00:00+08:00", "through": "2026-11-14T21:00:00+08:00",
                "pages": [page], "items": items,
                "entries": [{"source": "govuk", "entry": "news", "status": "partial",
                             "reason": "archive ended early"}]}

    result, manifest = reconcile(db_path, evidence, tmp_path)

    assert [row["status"] for row in result["items"]] == [
        "stored", "missing", "date_unverified", "scope_pending", "out_of_scope"]
    assert result["entries"] == evidence["entries"]
    assert [row["url"] for row in manifest["items"]] == ["https://www.gov.uk/missing"]

    (tmp_path / "listing.raw").write_bytes(b"different content")
    result, manifest = reconcile(db_path, evidence, tmp_path)
    assert {row["status"] for row in result["items"]} == {"evidence_unverified"}
    assert manifest["items"] == []


def test_window_keeps_source_day_precision_at_cutoff():
    from bluepulse_backend.source_audit import window_status

    assert window_status({"published_at": "2026-11-07T16:00:00Z"},
                         "2026-11-08T00:00:00+08:00", "2026-11-14T21:00:00+08:00") == "in_window"
    assert window_status({"published_date": "2026-11-14"},
                         "2026-11-08T00:00:00+08:00", "2026-11-14T21:00:00+08:00") == "date_cutoff_unverified"
    assert window_status({"published_at": "2026-11-14T15:00:00"},
                         "2026-11-08T00:00:00+08:00", "2026-11-14T21:00:00+08:00") == "date_unverified"
    correction = {"published_at": "2019-01-24T00:00:00Z", "updated_at": "2026-11-10T12:00:00Z"}
    assert window_status(correction,
                         "2026-11-08T00:00:00+08:00", "2026-11-14T21:00:00+08:00") == "out_of_window"
    assert window_status({**correction, "correction": True},
                         "2026-11-08T00:00:00+08:00", "2026-11-14T21:00:00+08:00") == "in_window"


def test_reconcile_flags_syndication_time_stored_as_original_publication():
    from bluepulse_backend.source_audit import _disposition

    page = ("govuk", "https://www.gov.uk/list", "hash")
    item = {"source": "govuk", "url": "https://www.gov.uk/test", "evidence_url": page[1],
            "evidence_sha256": page[2], "published_date": "2026-11-11", "source_offset": "+08:00",
            "syndicated_at": "2026-11-14T01:10:00+08:00", "scope": "in_scope"}
    material = {"published_at": "2026-11-13 17:10:00", "published_date": None,
                "withdrawn": False, "duplicate_of_id": None, "collection_state": "ready",
                "body_status": "full_text", "revision": 1}
    evidence = {"from": "2026-11-08T00:00:00+08:00", "through": "2026-11-14T21:00:00+08:00"}
    assert _disposition(item, evidence, {page}, material, None, None) == "stored_date_differs"


def test_capture_saves_hash_and_stops_after_retry_after(tmp_path):
    from bluepulse_backend.source_audit_capture import capture

    def response(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        if request.url.path == "/ok":
            return httpx.Response(200, content=b"raw public listing")
        if request.url.path == "/later":
            return httpx.Response(429, headers={"Retry-After": "120"})
        raise AssertionError(f"Unallowed request {request.url}")

    urls = ["/private", "/ok", "/later", "/after"]
    plan = [{"source": "govuk", "url": "https://www.gov.uk" + path} for path in urls]
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        rows = capture(client, plan, tmp_path, sleep=lambda _: None)

    assert rows[0]["error"] == "robots_disallowed"
    assert (tmp_path / Path(rows[1]["file"])).read_bytes() == b"raw public listing"
    assert rows[1]["sha256"] == hashlib.sha256(b"raw public listing").hexdigest()
    assert rows[2]["retry_after"] == "120"
    assert rows[3]["error"] == "host_throttled"
