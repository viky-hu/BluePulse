from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy.orm import Session

from bluepulse_backend.db import Base, make_engine
from bluepulse_backend import models


def sample(**changes):
    defaults = dict(
        language="en", revision=2, translation_revision=2, translation_status="available", selected_at=None,
        source_body="## Evidence\n\nA <script> example.\n\n```json\n{\"sample\": 1}\n```",
        zh_body="## 证据\n\n一段译文。", body_status="full_text",
        source=SimpleNamespace(full_text_allowed=True, syndicate_full_text_allowed=False),
    )
    return SimpleNamespace(**{**defaults, **changes})


def test_reader_sends_one_language_and_escapes_source_text():
    from bluepulse_backend.reading import reading_body

    original = reading_body(sample(), "original")
    assert original["bodyLanguage"] == "original"
    assert original["body"]["zh"] is None
    assert original["hasTranslation"]
    assert original["outline"] == [{"id": "sec-1", "text": "Evidence", "level": 2}]
    assert "&lt;script&gt;" in original["body"]["original"]
    assert '<pre><code class="language-json">' in original["body"]["original"]


def test_reader_hides_translation_for_previous_revision():
    from bluepulse_backend.reading import reading_body

    reader = reading_body(sample(translation_revision=1), "zh")
    assert reader["bodyLanguage"] == "original"
    assert reader["body"]["zhKind"] is None
    assert reader["hasTranslation"] is False


def test_long_translation_is_partial_and_reader_keeps_the_original_tail():
    from bluepulse_backend.editorial import translate
    from bluepulse_backend.reading import reading_body

    tail = "Evidence beyond the translation limit."
    original = "A" * 60_000 + "\n\n" + tail

    def translate_chunk(_capability, _purpose, _prompt, payload, _max_tokens):
        return {"blocks": ["译文" for _ in payload["blocks"]]}, None

    translation, complete = translate(original, translate_chunk)
    assert not complete
    article = sample(source_body=original, zh_body=translation, translation_status="partial")
    assert reading_body(article, "zh")["body"]["complete"] is False
    assert tail in reading_body(article, "original")["body"]["original"]


def test_reader_returns_no_body_when_current_source_permission_disallows_it():
    from bluepulse_backend.reading import reading_body

    reader = reading_body(sample(source=SimpleNamespace(full_text_allowed=False)), "zh")
    assert reader == {"body": None, "outline": [], "bodyLanguage": "original", "hasTranslation": False}


def test_markdown_checks_redistribution_separately():
    from bluepulse_backend.reading import export_markdown

    now = datetime(2026, 11, 8, tzinfo=UTC)
    article = sample(id="223a5981-9cc2-4056-9c45-43ab42683314", source_url="https://example.test/news",
                     published_at=now, published_date=None, first_seen_at=now,
                     zh_title="执法记录试点", source_title="Pilot", zh_summary="公开摘要",
                     source=SimpleNamespace(name="公开来源", full_text_allowed=True,
                                            syndicate_full_text_allowed=False))
    markdown = export_markdown(article, "http://127.0.0.1:3000")
    assert "公开摘要" in markdown
    assert "A <script>" not in markdown
    article.source.syndicate_full_text_allowed = True
    markdown = export_markdown(article, "http://127.0.0.1:3000")
    assert "&lt;script&gt;" in markdown
    assert "一段译文。" in markdown


def test_media_origin_validation_requires_approved_https_host():
    from bluepulse_backend.reader_media import approved_image_url

    allowed = ["example.test"]
    assert approved_image_url("https://example.test/news/image.webp", allowed)
    for url in ("http://example.test/img", "https://example.test:81/img",
                "https://example.test@127.0.0.1/img", "https://other.example.test/img",
                "https://example.test\\@127.0.0.1/img", "https://example.test/img#fragment"):
        assert not approved_image_url(url, allowed)


def test_proxy_token_is_revoked_on_license_or_revision_change(monkeypatch):
    from bluepulse_backend.reader_media import media_path, verified_media

    monkeypatch.setenv("BLUEPULSE_MEDIA_SECRET", "test-secret-for-signed-media")
    image = {"kind": "image", "url": "https://example.test/photo.png"}
    article = models.Material(
        id="223a5981-9cc2-4056-9c45-43ab42683314", revision=1, public=True,
        relevant=True, withdrawn=False, zh_summary="公开摘要", body_status="full_text",
        source_body="Public source evidence. " * 40, source_url="https://example.test/report",
        source=models.Source(enabled=True, participation_mode="editorial", excerpt_allowed=True,
                             media_allowed=True, full_text_allowed=True, allowed_hosts=["example.test"]),
        source_media=[image],
    )
    path = media_path(article, 0, image)
    args = parse_qs(urlsplit(path).query)
    expiry, signature = int(args["exp"][0]), args["sig"][0]
    assert verified_media(article, 0, expiry, signature) == image["url"]
    article.source.full_text_allowed = False
    assert verified_media(article, 0, expiry, signature) is None
    article.source.full_text_allowed = True
    article.source.media_allowed = False
    assert verified_media(article, 0, expiry, signature) is None
    article.source.media_allowed = True
    article.revision += 1
    assert verified_media(article, 0, expiry, signature) is None


def test_share_artifact_is_decodable_and_uses_requested_size():
    from PIL import Image
    from bluepulse_backend.reader_share import render_share

    article = sample(id="223a5981-9cc2-4056-9c45-43ab42683314", zh_title="警务科技试点",
                     zh_summary="可核实的公开摘要。", source_title="Pilot", importance_score=61,
                     published_at=datetime(2026, 11, 8, tzinfo=UTC), published_date=None,
                     first_seen_at=datetime(2026, 11, 8, tzinfo=UTC),
                     source=SimpleNamespace(name="公开信源"))
    for mode, size in [("poster", (1080, 1440)), ("og", (1200, 630))]:
        with Image.open(BytesIO(render_share(article, mode, "http://127.0.0.1:3000", True))) as image:
            assert (image.format, image.size) == ("PNG", size)
            assert len(image.getcolors(100_000)) > 20


def test_police_science_ingests_only_body_images():
    from bluepulse_backend.police_science_source import parse_news_html

    parsed = parse_news_html('''
        <img src="/branding.png"><h1 class="article_title">Patrol</h1>
        <div class="article_copy"><p>Evidence</p>
        <img src="/assets/evidence.png" alt="Field trial" width="800" height="400">
        <img src="https://unrelated.example.test/avatar.png">
        </div>
    ''')
    assert parsed.media == [{"kind": "image", "url": "https://science.police.uk/assets/evidence.png",
                             "alt": "Field trial", "width": 800, "height": 400}]


@pytest.fixture
def public_story_db(tmp_path):
    from bluepulse_backend.editorial_models import FactMention, Story

    now = datetime(2026, 11, 8, 3, tzinfo=UTC)
    engine = make_engine("sqlite:///" + (tmp_path / "reading.db").as_posix())
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        main = Story(title="当前事件")
        later = Story(title="另一个事件")
        session.add_all([main, later])
        session.flush()
        fact = models.FactGroup(story_id=main.id, title=main.title, identity_key="first", anchor_at=now)
        other = models.FactGroup(story_id=later.id, title=later.title, identity_key="second", anchor_at=now)
        official = models.Source(slug="police-science", name="官方信源", region="foreign",
                                 excerpt_allowed=True, full_text_allowed=True, media_allowed=True, tier="T1",
                                 allowed_hosts=["example.test"])
        news = models.Source(slug="news", name="新闻信源", region="domestic", excerpt_allowed=True,
                             full_text_allowed=True, tier="T2", allowed_hosts=["example.test"])
        session.add_all([fact, other, official, news])
        session.flush()

        def add(name, source, group=None, **values):
            url = f"https://example.test/{name}"
            article = models.Material(
                canonical_url=url, source_url=url, source=source, source_title=name, zh_title=name,
                zh_summary="公开摘要", public=True, relevant=True, body_status="full_text", revision=1,
                source_body="National Police announced a field test. " * 30, content_hash="a" * 64,
                grouping_status="complete", editorial_revision=1, selected_at=now,
                featured_candidate=True, timeline_kind="fresh", published_at=now, first_seen_at=now,
                fetched_at=now, language="en", **values,
            )
            session.add(article)
            session.flush()
            if group:
                session.add(models.FactReport(material_id=article.id, fact_id=group.id,
                                               revision=1, relation="report"))
            return article

        root = add("Official report", official, fact, source_media=[
            {"kind": "image", "url": "https://example.test/photo.png"},
        ])
        sibling = add("News report", news, fact)
        development = add("Another event", official, other)
        roundup = add("Roundup", news, editorial_scope="composite")
        session.add(FactMention(material_id=roundup.id, fact_id=fact.id, revision=1))
        session.commit()
        yield session, engine.url.render_as_string(hide_password=False), main, root, sibling, development, roundup, now
    engine.dispose()


def test_public_story_uses_current_fact_evidence_and_representative(public_story_db):
    from bluepulse_backend.reading import reader_projection, story_detail, story_followups

    session, _, story, root, sibling, _, roundup, now = public_story_db
    view = story_detail(session, story, now)
    assert view["reportCount"] == 3
    assert {row["id"] for row in view["timeline"]} == {root.id, sibling.id, roundup.id}
    assert view["developments"][0]["reportCount"] == 2
    assert view["developments"][0]["representative"]["id"] == root.id
    assert story_followups(session, story.id)["items"][0]["representative"]["id"] == root.id
    assert reader_projection(session, sibling)["sameEvent"]["id"] == root.id
    root.withdrawn = True
    session.commit()
    assert story_detail(session, story, now)["title"] == "News report"
    sibling.withdrawn = True
    session.commit()
    assert story_detail(session, story, now) is None


def test_public_reading_value_comes_from_current_selected_representative(public_story_db, monkeypatch):
    from fastapi.testclient import TestClient

    from bluepulse_backend.api import create_app
    from bluepulse_backend.fact_grouping import CONFIRMED_WINDOW

    session, url, _, root, sibling, _, _, _ = public_story_db
    monkeypatch.setenv("BLUEPULSE_SITE_ORIGIN", "http://127.0.0.1:3000")
    edition = models.FeaturedEdition(window_policy=CONFIRMED_WINDOW)
    session.add(edition)
    session.flush()
    session.add(models.FeaturedSlot(edition_id=edition.id, article_id=root.id, slot="p0",
                                    importance_score=80, featured_reason="近期自动编排；未进行五轴评分"))
    reason = "官方公告交代了野外测试安排。"
    root.editorial_data = {"reason": reason}
    sibling.editorial_data = {"reason": "新闻稿概括了测试安排。"}
    session.commit()

    with TestClient(create_app(url)) as client:
        home = client.get("/api/v1/home/featured").json()["items"][0]
        assert home["featured_reason"] == home["article"]["featured_reason"] == reason
        cards = {item["id"]: item for item in client.get("/api/v1/articles?period=all").json()["items"]}
        assert cards[root.id]["featured_reason"] == reason
        assert cards[sibling.id]["featured_reason"] is None
        assert client.get(f"/api/v1/articles/{root.id}").json()["reader"]["reason"] == reason
        assert reason in client.get(f"/api/v1/articles/{root.id}/markdown").text
        assert "推荐理由" not in client.get(f"/api/v1/articles/{sibling.id}/markdown").text

        root.editorial_data = {"reason": "本站把这篇报道列为精选，评分达到门槛。"}
        session.commit()
        assert client.get("/api/v1/home/featured").json()["items"][0]["featured_reason"] is None
        assert client.get(f"/api/v1/articles/{root.id}").json()["reader"]["reason"] is None


def test_metadata_is_exact_scoped_to_current_revision_and_license(public_story_db):
    from bluepulse_backend.public_metadata import entity_links, entity_page, entity_slug, with_metadata_match
    from bluepulse_backend.public_reads import listed_query

    session, _, _, root, sibling, _, _, _ = public_story_db
    slug = entity_slug("National Police", "organization")
    assert slug == entity_slug("national police", "organization")
    root.editorial_data = {"tags": ["field test"], "entities": [
        {"name": "National Police", "slug": slug, "type": "organization", "evidence": "National Police announced"},
    ]}
    sibling.editorial_data = {"tags": ["field test plan"], "entities": [
        {"name": "National Police", "slug": slug, "type": "organization", "evidence": "National Police announced"},
    ]}
    sibling.editorial_revision = 0
    session.commit()
    assert entity_links(root) == [{"name": "National Police", "slug": slug, "entity_type": "organization"}]
    assert list(session.scalars(with_metadata_match(listed_query(), tag="field test"))) == [root]
    assert list(session.scalars(with_metadata_match(listed_query(), tag="field"))) == []
    assert list(session.scalars(with_metadata_match(listed_query(), entity=slug))) == [root]
    assert entity_page(session, region="foreign")["items"][0]["article_count"] == 1
    root.source.full_text_allowed = False
    session.commit()
    assert not entity_links(root) and not entity_page(session)["items"]
    assert list(session.scalars(with_metadata_match(listed_query(), entity=slug))) == []


def test_image_fetch_pins_only_public_dns_answers(monkeypatch):
    from bluepulse_backend import reader_media

    def answer(*addresses):
        return [(None, None, None, None, (ip, 443)) for ip in addresses]

    monkeypatch.setattr(reader_media.socket, "getaddrinfo", lambda *args, **kwargs: answer("127.0.0.1", "::1"))
    with pytest.raises(ValueError, match="image_origin_not_public"):
        reader_media._pinned_origin("https://example.test/image.png")
    monkeypatch.setattr(reader_media.socket, "getaddrinfo", lambda *args, **kwargs: answer("127.0.0.1", "93.184.216.34"))
    assert reader_media._pinned_origin("https://example.test/image.png?a=2") == (
        "https://93.184.216.34/image.png?a=2", "example.test",
    )


def test_public_http_uses_same_current_evidence_for_reading_sharing_and_story(public_story_db, monkeypatch):
    from fastapi.testclient import TestClient
    from bluepulse_backend.api import create_app
    from bluepulse_backend.editorial_models import PaidAttempt, Story
    from bluepulse_backend import reading

    session, url, story, root, sibling, _, _, _ = public_story_db
    monkeypatch.setenv("BLUEPULSE_MEDIA_SECRET", "local-test-signing-secret")
    monkeypatch.setenv("BLUEPULSE_SITE_ORIGIN", "http://127.0.0.1:3000")
    monkeypatch.setattr(reading, "fetch_raster", lambda url: b"controlled raster fixture")
    alias = Story(title="Alias", merged_into_id=story.id)
    session.add(alias)
    root.zh_body = "本次修订的公开译文。"
    root.translation_revision = 1
    root.translation_status = "available"
    session.commit()
    api = f"/api/v1/articles/{root.id}"
    event = f"/api/v1/site/stories/{story.id}"
    with TestClient(create_app(url), follow_redirects=False) as client:
        default = client.get(api).json()
        assert default["reader"]["bodyLanguage"] == "zh" and default["reader"]["body"]["original"] is None
        assert default["source_body"] is None
        original = client.get(api, params={"body_language": "original"}).json()
        assert original["reader"]["bodyLanguage"] == "original" and original["zh_body"] is None
        assert client.get(f"{api}/markdown").text.count("National Police announced") == 0
        poster = client.get(f"{api}/poster.png")
        assert poster.status_code == 200 and poster.headers["content-type"] == "image/png"
        assert client.get(f"{api}/poster.png", headers={"If-None-Match": poster.headers["etag"]}).status_code == 304
        img = default["media"][0]["url"].replace("/api/bluepulse/", "/api/v1/", 1)
        assert client.get(img).content == b"controlled raster fixture"
        assert client.get(img[:-1]).status_code == 422
        assert client.get(event).json()["latest"]
        moved = client.get(f"/api/v1/site/stories/{alias.id}")
        assert moved.status_code == 308 and moved.headers["location"] == f"/story/{story.id}"
        root.source.full_text_allowed = False
        root.source.media_allowed = False
        session.commit()
        restricted = client.get(api).json()
        assert restricted["reader"]["readingMode"] == "summary-only"
        assert restricted["source_body"] is None and restricted["zh_body"] is None
        assert client.get(f"{api}/markdown").status_code == 404
        assert client.get(img).status_code == 404
        assert client.get("/api/v1/articles/availability", params={"ids": root.id}).json()["items"][0]["status"] == "summary-only"
        root.withdrawn = True
        sibling.withdrawn = True
        session.commit()
        assert client.get(f"{api}/poster.png", headers={"If-None-Match": poster.headers["etag"]}).status_code == 404
        assert client.get(event).status_code == 404
        assert client.get(f"{event}/followups").status_code == 404
    assert session.query(PaidAttempt).count() == 0
