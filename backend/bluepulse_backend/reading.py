"""Public reading projections adapted from AIHOT publication/detail.ts and stories.ts.

AIHOT is MIT-licensed. Copyright (c) 2026 数字生命卡兹克.
"""
from __future__ import annotations

import html
import hashlib
import os
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import httpx
from fastapi import Depends, Query, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func, select

from . import publication
from .agent_access import site_origin
from .edition_models import DailyIssue
from .editorial_models import FactMention, Story
from .models import FactGroup, FactReport, Material, Source, Topic
from .public_metadata import public_tags
from .public_reads import listed_query
from .reader_media import fetch_raster, media_path, public_media, verified_media
from .reader_media import public_cover as public_cover, public_source_icon as public_source_icon
from .reader_share import render_share


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value):
    return _aware(value).astimezone(UTC).isoformat().replace("+00:00", "Z")


def _title(article):
    return article.zh_title or article.source_title


def _timeline_at(article):
    return article.published_sort_at or article.published_at or article.first_seen_at


def _body_as_html(text):
    """Render stored plain text, with safe headings and fenced code when present."""
    parts, outline = [], []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paragraph = []
    code = None
    language = ""

    def paragraph_end():
        if paragraph:
            parts.append("<p>" + "<br>".join(html.escape(line) for line in paragraph) + "</p>")
            paragraph.clear()

    for line in lines:
        if code is not None:
            if line.strip() == "```":
                cls = f' class="language-{language}"' if language else ""
                parts.append(f"<pre><code{cls}>" + html.escape("\n".join(code)) + "</code></pre>")
                code = None
            else:
                code.append(line)
            continue
        fence = re.fullmatch(r"```([a-zA-Z0-9_-]{0,24})\s*", line)
        heading = re.fullmatch(r"(#{2,4})[ \t]+(.+)", line)
        if fence:
            paragraph_end()
            code, language = [], fence[1]
        elif heading:
            paragraph_end()
            level = len(heading[1])
            title = heading[2].strip()
            anchor = f"sec-{len(outline) + 1}"
            outline.append({"id": anchor, "text": title[:80], "level": level})
            parts.append(f'<h{level} id="{anchor}">{html.escape(title)}</h{level}>')
        elif not line.strip():
            paragraph_end()
        else:
            paragraph.append(line)
    if code is not None:
        parts.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
    paragraph_end()
    return "".join(parts), outline


def _original(article):
    if article.source.full_text_allowed and article.body_status == "full_text":
        return (article.source_body or "").strip() or None
    return None


def _translation(article):
    if (not article.language.lower().startswith("zh") and
            article.translation_revision == article.revision):
        return (article.zh_body or "").strip() or None
    return None


def reading_body(article, language):
    empty = {"body": None, "outline": [], "hasTranslation": False, "bodyLanguage": "original"}
    original = _original(article)
    if not original:
        return empty
    chinese = article.language.lower().startswith("zh")
    translation = _translation(article)
    zh = original if chinese else translation
    shown = zh if language == "zh" and zh else original
    body_language = "zh" if shown is zh and language == "zh" else "original"
    content, outline = _body_as_html(shown)
    return {
        "body": {"zh": content if body_language == "zh" else None,
                 "original": content if body_language == "original" else None,
                 "zhKind": "original" if chinese else "translation" if translation else None,
                 "complete": body_language == "original" or chinese or
                 bool(translation and article.translation_status == "available")},
        "outline": outline, "hasTranslation": bool(translation), "bodyLanguage": body_language,
    }


def _editorial(article):
    return (article.editorial_data or {}) if article.editorial_revision == article.revision else {}


def _current_report():
    return (FactReport.revision == Material.revision,
            FactReport.relation.in_(("primary", "report")),
            Material.grouping_status == "complete")


def _fact_reports(session, fact_id):
    query = (listed_query().join(FactReport, FactReport.material_id == Material.id)
             .where(FactReport.fact_id == fact_id, *_current_report()))
    return [article for article in session.scalars(query) if publication.visible(article)]


def representative_key(article, fact=None):
    source = article.source
    owner = getattr(source, "owner_entity", None)
    publisher = getattr(source, "publisher_role", None)
    subjects = re.split(r"[,，、;；+＋&＆/]", getattr(fact, "subject", None) or "")
    priority = 3
    if getattr(source, "tier", None) == "T1":
        priority = 0
    elif owner and any(owner.casefold() == value.strip().casefold() for value in subjects):
        priority = {"organization": 1, "person": 2}.get(publisher, 3)
    return (priority, not bool(_original(article)), -article.importance_score,
            _aware(_timeline_at(article)), article.id)


def _public_story(session, story_id):
    story = session.get(Story, story_id) if story_id else None
    return story if story and not story.merged_into_id else None


def _story_ref(story, title=None):
    return {"publicId": story.id, "title": title or story.title}


def reader_projection(session, article, body_language="zh"):
    reading = reading_body(article, body_language)
    result = {
        **reading, "readingMode": "full" if article.source.full_text_allowed else "summary-only",
        "selected": False, "reason": None, "sameEvent": None, "group": None,
        "story": None, "relatedStories": [], "tags": [], "channel": "news", "x": None,
        "indexable": False, "markdownAvailable": False,
    }
    if not article.source.full_text_allowed:
        return result
    selected = publication.selected(article)
    result["selected"] = selected
    result["tags"] = public_tags(article)
    result["markdownAvailable"] = bool(article.zh_summary or _original(article))
    mentioned = session.scalars(select(FactGroup.story_id).join(FactMention, FactGroup.id == FactMention.fact_id)
                                .where(FactMention.material_id == article.id,
                                       FactMention.revision == article.revision).distinct().limit(6)).all()
    for story_id in mentioned:
        related = _public_story(session, story_id)
        if related and (title := _current_story_title(session, related.id)):
            result["relatedStories"].append(_story_ref(related, title))
    member = session.get(FactReport, article.id)
    if not member or member.revision != article.revision or article.grouping_status != "complete":
        return result
    fact = session.get(FactGroup, member.fact_id)
    if fact is None or member.relation not in ("primary", "report"):
        return result
    reports = _fact_reports(session, member.fact_id)
    chosen = [row for row in reports if publication.selected(row)]
    representative = min(chosen, key=lambda row: representative_key(row, fact), default=None)
    story = _public_story(session, fact.story_id)
    if story and (title := _current_story_title(session, story.id)):
        result["story"] = _story_ref(story, title)
    result["group"] = {
        "factId": fact.id,
        "reportCount": len(reports),
        "additionalSourceCount": len({r.source_id for r in reports} - {article.source_id}),
    }
    if representative and representative.id != article.id:
        result["sameEvent"] = {"id": representative.id, "title": _title(representative)}
    elif selected:
        result["reason"] = _editorial(article).get("reason")
    result["indexable"] = selected
    return result


def apply_reader(session, article, detail, body_language="zh"):
    reader = reader_projection(session, article, body_language)
    result = {**detail, "reader": reader}
    if reader["readingMode"] == "summary-only":
        result.update(source_body=None, zh_body=None, body_source_url=None, author=None,
                      importance_score=0, topics=[], entities=[], media=[], media_preview=None)
    else:
        result["source_body"] = _original(article) if body_language == "original" or not reader["hasTranslation"] else None
        result["zh_body"] = _translation(article) if body_language == "zh" else None
        images = []
        for index, image in enumerate(public_media(article)):
            path = media_path(article, index, image)
            if path:
                images.append({"kind": "image", "url": path, "thumbnail_url": path,
                               "alt_text": image.get("alt"), "position": index})
        result["media"] = images
    return result


def _md(text):
    return html.escape(text, quote=False).replace("[", r"\[").replace("]", r"\]")


def export_markdown(article, origin):
    lines = [f"# {_md(_title(article))}", ""]
    if article.zh_title and article.zh_title != article.source_title:
        lines.extend((f"> 原标题：{_md(article.source_title)}", ""))
    lines.append(f"- 来源：{_md(article.source.name)}")
    if article.published_at or article.published_date:
        date = _iso(article.published_at) if article.published_at else article.published_date.isoformat()
        lines.append(f"- 发布时间：{date}")
    else:
        lines.append(f"- 收录时间：{_iso(article.first_seen_at)}")
    lines.extend((f"- Pulse：{origin}/articles/{article.id}", f"- 原文：{_md(article.source_url)}", ""))
    if article.zh_summary:
        lines.extend(("## 摘要", "", _md(article.zh_summary), ""))
    if article.source.full_text_allowed and article.selected_at and publication.selected(article):
        reason = _editorial(article).get("reason")
        if reason:
            lines.extend(("## 推荐理由", "", _md(reason), ""))
    if _original(article) and article.source.syndicate_full_text_allowed:
        translation = _translation(article)
        if translation:
            lines.extend(("## 正文 · 中文译文", "", _md(translation), ""))
        lines.extend(("## 正文 · 原文", "", _md(_original(article)), ""))
    return "\n".join(lines)


def availability_item(article, article_id):
    if not article or not publication.visible(article):
        return {"id": article_id, "available": False, "status": "unavailable"}
    return {"id": article_id, "available": True, "source_name": article.source.name,
            "status": "public" if article.source.full_text_allowed else "summary-only"}


def _story_reports(session, story_id, *, mentions=False, now=None):
    query = (listed_query().add_columns(FactGroup)
             .join(FactReport, FactReport.material_id == Material.id)
             .join(FactGroup, FactReport.fact_id == FactGroup.id)
             .where(FactGroup.story_id == story_id, *_current_report()))
    reports = [(article, fact) for article, fact in session.execute(query) if publication.visible(article, at=now)]
    if not mentions:
        return reports
    mention_query = (listed_query().join(FactMention, FactMention.material_id == Material.id)
                     .join(FactGroup, FactMention.fact_id == FactGroup.id)
                     .where(FactGroup.story_id == story_id, FactMention.revision == Material.revision,
                            Material.grouping_status == "complete").distinct())
    member_ids = {article.id for article, _ in reports}
    return reports + [(article, None) for article in session.scalars(mention_query)
                      if article.id not in member_ids and publication.visible(article, at=now)]


def _current_story_title(session, story_id):
    # A former root's title is not exposed after withdrawal or loss of eligibility.
    rows = _story_reports(session, story_id)
    root = min(rows, key=lambda row: (_aware(row[1].anchor_at), row[1].id,
                                     representative_key(row[0], row[1])), default=None)
    return _title(root[0]) if root else None


def _grouped(rows):
    facts, members = {}, defaultdict(list)
    for article, fact in rows:
        if fact is not None:
            facts[fact.id] = fact
            members[fact.id].append(article)
    return [(facts[key], members[key]) for key in members]


def _first_party(article):
    return article.source.tier == "T1"


def _report_view(article, now):
    return {
        "id": article.id, "title": _title(article), "summary": article.zh_summary,
        "source": {"name": article.source.name, "firstParty": _first_party(article)},
        "publishedAt": _iso(_timeline_at(article)), "selected": publication.selected(article, at=now),
    }


def story_detail(session, story, now=None):
    from .hotspots import story_heat
    from .story_digest import load_digest

    now = now or datetime.now(UTC)
    rows = _story_reports(session, story.id, mentions=True, now=now)
    ordered = sorted(rows, key=lambda row: (-_aware(_timeline_at(row[0])).timestamp(), row[0].id))
    primary = [article for article, fact in ordered if fact is not None]
    if not primary:
        return None
    developments = []
    for fact, members in _grouped(ordered):
        chosen = [item for item in members if publication.selected(item, at=now)]
        rep = min(chosen or members, key=lambda article: representative_key(article, fact))
        start = min(_aware(_timeline_at(item)) for item in members)
        developments.append({"factId": fact.id, "title": _title(rep), "firstReportAt": _iso(start),
                             "reportCount": len(members), "representative": _report_view(rep, now)})
    developments.sort(key=lambda item: (item["firstReportAt"], item["factId"]), reverse=True)
    root = developments[-1]["representative"]
    topic_counts = Counter(slug for article, _ in ordered for slug in (article.topics or []))
    topics = {row.slug: row.name_zh for row in session.scalars(
        select(Topic).where(Topic.enabled.is_(True), Topic.slug.in_(list(topic_counts))))}
    latest, earliest = _aware(_timeline_at(primary[0])), _aware(_timeline_at(primary[-1]))
    age = _aware(now) - latest
    digest = load_digest(session, story.id, now)
    return {
        **_story_ref(story, root["title"]),
        **story_heat(session, story.id, now),
        "status": "active" if age < timedelta(days=1) else "watching" if age < timedelta(days=3) else "settled",
        "reportCount": len(ordered), "sourceCount": len({article.source_id for article, _ in ordered}),
        "firstReportAt": _iso(earliest), "latestAt": _iso(latest),
        "digest": digest.digest if digest else None,
        "digestUpdatedAt": _iso(digest.generated_at) if digest else None,
        "summary": None, "excerpt": {"text": root["summary"], "sourceName": root["source"]["name"]} if root["summary"] else None,
        "latest": _title(primary[0]), "latestReport": {"id": primary[0].id},
        "developments": developments, "timeline": [_report_view(article, now) for article, _ in ordered[:100]],
        "officialReports": [_report_view(article, now) for article in primary if _first_party(article)][:12],
        "related": [], "topics": [{"slug": slug, "name": topics[slug]} for slug, _ in topic_counts.most_common() if slug in topics],
    }


def story_followups(session, story_id):
    reports = [(article, fact) for article, fact in _story_reports(session, story_id)
               if publication.selected(article)]
    entries = []
    for fact, members in _grouped(reports):
        chosen = min(members, key=lambda article: representative_key(article, fact))
        first = min(_aware(_timeline_at(article)) for article in members)
        entries.append((first, fact.id, {
            "factId": fact.id,
            "representative": {"id": chosen.id, "title": _title(chosen),
                               "source": {"name": chosen.source.name}, "timelineAt": _iso(_timeline_at(chosen))},
        }))
    entries.sort(key=lambda entry: (-entry[0].timestamp(), entry[1]))
    return {"items": [entry[2] for entry in entries[:8]], "more": len(entries) > 8}


def _resolve_story(session, story_id):
    original = session.get(Story, story_id)
    if not original:
        return None
    target = original
    seen = {original.id}
    while target.merged_into_id:
        if target.merged_into_id in seen or len(seen) >= 10:
            return None
        seen.add(target.merged_into_id)
        target = session.get(Story, target.merged_into_id)
        if target is None:
            return None
    return target


def public_stats(session, now=None):
    from .source_collection import SOURCES

    now = _aware(now or datetime.now(UTC))
    local = now.astimezone(timezone(timedelta(hours=8)))
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    visible_items = [article for article in session.scalars(listed_query()) if publication.visible(article, at=now)]
    selected = [article for article in visible_items if publication.selected(article, at=now)]
    sources = list(session.scalars(select(Source).where(Source.enabled.is_(True), Source.excerpt_allowed.is_(True))))
    samples = []
    for source in sources:
        spec = SOURCES.get(source.slug)
        kind = spec.kind if spec else ""
        kind = ("rss" if kind.endswith("_rss") else "json_list" if kind.endswith("_api")
                else "web_list" if kind.endswith(("_html", "_news")) or kind == "police_science" else "other")
        samples.append({"name": source.name, "kind": kind, "heatOnly": source.participation_mode == "hot_signal"})
    samples.sort(key=lambda item: hashlib.sha256(f"{local.date()}:{item['name']}".encode()).digest())
    selected.sort(key=lambda item: (-_aware(item.selected_at).timestamp(), item.id))
    seen_facts = set()
    representatives = []
    for article in selected:
        member = session.get(FactReport, article.id)
        if not member or member.fact_id in seen_facts:
            continue
        seen_facts.add(member.fact_id)
        reports = [row for row in _fact_reports(session, member.fact_id) if publication.selected(row, at=now)]
        if reports:
            fact = session.get(FactGroup, member.fact_id)
            representatives.append(min(reports, key=lambda row: representative_key(row, fact)))
    return {
        "sources": len(sources), "sourceKinds": dict(Counter(item["kind"] for item in samples)),
        "items": len(visible_items), "selected": len(representatives),
        "dailies": session.scalar(select(func.count()).select_from(DailyIssue)),
        "day": {"collected": sum(start <= _aware(article.first_seen_at) <= now for article in visible_items),
                "selected": sum(start <= _aware(article.selected_at) <= now for article in representatives)},
        "sampleSources": samples[:180],
        "latest": [{"id": article.id, "title": _title(article), "source": article.source.name} for article in representatives[:8]],
    }


def register_reading(router, session_dep, ApiError):
    def article_or_404(session, article_id):
        article = session.get(Material, str(article_id))
        if article is None or not publication.visible(article):
            raise ApiError(404, "article_not_found", "文章不存在。")
        return article

    @router.get("/articles/{article_id}/markdown")
    def markdown(article_id: UUID, session=Depends(session_dep)):
        article = article_or_404(session, article_id)
        if not article.source.full_text_allowed or not (article.zh_summary or _original(article)):
            raise ApiError(404, "export_unavailable", "该文章暂不提供导出。")
        origin = site_origin(os.environ.get("BLUEPULSE_SITE_ORIGIN"))
        if origin is None:
            raise ApiError(503, "share_origin_unconfigured", "公开站点地址尚未配置。")
        return PlainTextResponse(export_markdown(article, origin), media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="pulse-{article_id}.md"'})

    def share(request, article_id, session, mode):
        article = article_or_404(session, article_id)
        origin = site_origin(os.environ.get("BLUEPULSE_SITE_ORIGIN"))
        if not origin and mode == "poster":
            raise ApiError(503, "share_origin_unconfigured", "公开站点地址尚未配置。")
        try:
            data = render_share(article, mode, origin, article.source.full_text_allowed and publication.selected(article))
        except (OSError, ValueError):
            raise ApiError(503, "share_unavailable", "暂时无法生成分享图片。") from None
        etag = '"' + hashlib.sha256(data).hexdigest()[:32] + '"'
        headers = {"ETag": etag, "X-Content-Type-Options": "nosniff"}
        if etag in (tag.strip() for tag in request.headers.get("if-none-match", "").split(",")):
            return Response(status_code=304, headers=headers)
        return Response(data, media_type="image/png", headers=headers)

    @router.get("/articles/{article_id}/poster.png")
    def poster(request: Request, article_id: UUID, session=Depends(session_dep)):
        return share(request, article_id, session, "poster")

    @router.get("/articles/{article_id}/og.png")
    def og(request: Request, article_id: UUID, session=Depends(session_dep)):
        return share(request, article_id, session, "og")

    @router.get("/site/media/{article_id}/{index}")
    def media(article_id: UUID, index: int, exp: int = Query(ge=0),
              sig: str = Query(pattern=r"^[a-f0-9]{64}$"), session=Depends(session_dep)):
        article = article_or_404(session, article_id)
        url = verified_media(article, index, exp, sig)
        if url is None:
            raise ApiError(404, "media_not_found", "图片不存在或链接已失效。")
        try:
            data = fetch_raster(url)
        except (httpx.HTTPError, OSError, ValueError):
            raise ApiError(503, "media_unavailable", "暂时无法读取图片。") from None
        session.rollback()
        article = article_or_404(session, article_id)
        if verified_media(article, index, exp, sig) != url:
            raise ApiError(404, "media_not_found", "图片不存在或链接已失效。")
        return Response(data, media_type="image/webp", headers={"X-Content-Type-Options": "nosniff"})

    @router.get("/site/stories/{public_id}")
    def story(public_id: UUID, session=Depends(session_dep)):
        found = _resolve_story(session, str(public_id))
        detail = story_detail(session, found) if found else None
        if detail is None:
            raise ApiError(404, "story_not_found", "事件不存在或尚未公开。")
        if found.id != str(public_id):
            return Response(status_code=308, headers={"Location": f"/story/{found.id}"})
        return detail

    @router.get("/site/stories/{public_id}/followups")
    def followups(public_id: UUID, session=Depends(session_dep)):
        found = _public_story(session, str(public_id))
        if not found or not _story_reports(session, found.id):
            raise ApiError(404, "story_not_found", "事件不存在或尚未公开。")
        return story_followups(session, found.id)

    @router.get("/site/stats")
    def stats(session=Depends(session_dep)):
        return public_stats(session)
