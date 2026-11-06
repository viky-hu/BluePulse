from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bluepulse_backend.api import create_app
from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.models import Material, Source


def _row(source: Source, suffix: str, title: str, summary: str,
         *, published_at: datetime | None, published_date=None,
         body: str | None = None) -> Material:
    now = datetime.now(UTC)
    return Material(
        canonical_url=f"https://example.gov.uk/{suffix}",
        source_url=f"https://example.gov.uk/{suffix}",
        source_id=source.id, source_title=title, zh_title=title,
        zh_summary=summary, source_body=body or ("Public evidence. " * 30),
        language="en", published_at=published_at, published_date=published_date,
        published_sort_at=(published_at or datetime.combine(published_date, time.min, UTC)
                           if published_date else published_at),
        first_seen_at=now, fetched_at=now, revision=1,
        content_hash=suffix.ljust(64, "0"), state="publication_pool",
        timeline_kind="fresh" if published_at is None or now - published_at < timedelta(days=2)
                      else "historical",
        body_status="full_text", translation_status="not_required",
        relevant=True, public=True, withdrawn=False,
    )


def test_agent_queries_share_public_scope_without_exposing_body(tmp_path, monkeypatch):
    address = f"sqlite:///{(tmp_path / 'agent.db').as_posix()}"
    engine = make_engine(address)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        source = Source(slug="official", name="Official", region="foreign",
                        country_code="GB", language="en", source_type="official",
                        topics=[], allowed_hosts=["example.gov.uk"],
                        excerpt_allowed=True, full_text_allowed=True)
        session.add(source)
        session.flush()
        current = _row(source, "current", "警务通信进展", "公开试点摘要",
                       published_at=now - timedelta(hours=2),
                       body="hiddenphrase " * 35)
        date_only = _row(source, "date", "日期级报道", "日期公开信息",
                         published_at=None, published_date=now.date())
        old = _row(source, "old", "历史技术稿", "旧稿仍可查",
                   published_at=now - timedelta(days=90))
        stale = _row(source, "stale", "无效正文", "不应出现",
                     published_at=now - timedelta(minutes=2), body="a" * 299)
        unsafe_link = _row(source, "unsafe", "无效原文链接", "不应进入 Agent",
                           published_at=now - timedelta(minutes=1))
        unsafe_link.source_url = "javascript:alert(1)"
        withdrawn = _row(source, "withdrawn", "撤回报道", "撤回摘要",
                         published_at=now - timedelta(minutes=3))
        withdrawn.withdrawn = True
        session.add_all([current, date_only, old, stale, unsafe_link, withdrawn])
        session.commit()
        source_id, current_id, date_id, old_id = source.id, current.id, date_only.id, old.id

    monkeypatch.delenv("BLUEPULSE_SITE_ORIGIN", raising=False)
    with TestClient(create_app(address)) as client:
        assert client.get("/api/v1/agent/latest").status_code == 503
        monkeypatch.setenv("BLUEPULSE_SITE_ORIGIN", "https://pulse.example")
        latest = client.get("/api/v1/agent/latest", headers={"Host": "attacker.example"})
        assert latest.status_code == 200
        payload = latest.json()
        assert payload["schema_version"] == 1
        assert payload["query"] == {"kind": "latest", "window": "7d", "limit": 10,
                                    "q": None, "sort_basis": "source_publication_then_first_seen"}
        assert [item["id"] for item in payload["items"]] == [current_id, date_id]
        assert payload["items"][0]["date_precision"] == "datetime"
        assert payload["items"][1]["date_precision"] == "date"
        assert payload["items"][1]["published_at"] is None
        assert payload["items"][0]["site_url"] == f"https://pulse.example/articles/{current_id}"
        assert payload["items"][0]["original_url"] == "https://example.gov.uk/current"
        assert "source_body" not in payload["items"][0]
        assert "hiddenphrase" not in str(payload)
        assert [item["id"] for item in client.get("/api/v1/agent/latest",
            params={"window": "24h"}).json()["items"]] == [current_id]
        assert [item["id"] for item in client.get("/api/v1/agent/latest",
            params={"limit": 1}).json()["items"]] == [current_id]
        browser_first = client.get("/api/v1/articles", params={
            "period": "all", "limit": 1}).json()
        assert browser_first["items"][0]["id"] == current_id
        assert browser_first["next_cursor"]
        assert [item["id"] for item in client.get("/api/v1/agent/search",
            params={"q": "历史技术"}).json()["items"]] == [old_id]
        assert [item["id"] for item in client.get("/api/v1/articles",
            params={"q": "历史技术", "period": "all"}).json()["items"]] == [old_id]
        assert client.get("/api/v1/agent/search", params={"q": "hiddenphrase"}).json()["items"] == []
        assert client.get("/api/v1/articles", params={
            "period": "all", "q": "hiddenphrase"}).json()["items"] == []
        assert client.get("/api/v1/agent/search", params={"q": "  "}).status_code == 422
        assert client.get("/api/v1/agent/latest", params={"limit": 31}).status_code == 422
        assert client.get("/api/v1/agent/latest", params={"window": "all"}).status_code == 422
        guide = client.get("/api/v1/agent")
        assert guide.status_code == 200
        assert guide.headers["content-type"].startswith("text/markdown")
        assert "https://pulse.example/articles/" in guide.text
        assert "window=7d" in guide.text and "window=all" in guide.text
        openapi = client.get("/openapi.json").json()["paths"]
        assert "text/markdown" in openapi["/api/v1/agent"]["get"]["responses"]["200"]["content"]

        monkeypatch.setenv("BLUEPULSE_SITE_ORIGIN", "https://name:secret@pulse.example")
        assert client.get("/api/v1/agent/latest").status_code == 503
        monkeypatch.setenv("BLUEPULSE_SITE_ORIGIN", "https://pulse.example")

        with Session(engine) as session:
            source = session.get(Source, source_id)
            source.excerpt_allowed = False
            session.commit()
        assert client.get("/api/v1/agent/latest").json()["items"] == []
        assert client.get("/api/v1/agent/search", params={"q": "历史技术"}).json()["items"] == []
        assert client.get("/api/v1/articles", params={"period": "all"}).json()["items"] == []
    engine.dispose()
