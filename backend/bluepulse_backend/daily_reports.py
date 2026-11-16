"""AIHOT reports/edition.ts, compose.ts and publication/reports.ts for Pulse daily issues.

Copyright (c) 2026 数字生命卡兹克. MIT. See THIRD_PARTY_NOTICES.md.
"""

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import floor, log2

from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, joinedload

from .daily_inputs import BEIJING, DAY, RECOVERY_WINDOW, daily_inputs, daily_window, edition_key
from .edition_evidence import _participant_key, public_at, story_reports, timeline_at, title_of, utc
from .edition_models import DailyIssue, DailyIssueRevision
from .editorial_models import FactMention, Story
from .models import FactGroup, FactReport, Material, SourceRun, now_utc
from .publication import relevance_allowed


MAIN_LIMIT = 12
SOURCE_LIMIT = 2
INDEX_LIMIT = 400
VERSION = "daily-v2-collection"
SECTIONS = {
    "product": "产品发布与更新", "practice": "警务实战应用", "paper": "论文研究进展",
    "law": "法制政策动态", "embodied": "具身智能装备", "public-opinion": "舆情治理观察",
    "low-altitude": "低空警务应用", "other": "其它警务科技", "unclassified": "其他警务科技",
}


@dataclass(slots=True)
class FactCandidate:
    key: str
    reports: list[tuple[Material, FactGroup | None]]
    coverage: dict[str, int]
    sources: set[str]


@dataclass(slots=True)
class DailyCandidate:
    citation: dict
    story_id: str | None
    mentions: set[str]
    source_ids: set[str]
    authority: int
    importance: float


def _all_citations(content: dict):
    for entry in [*content["main"], *content["flashes"]]:
        yield entry
        yield from entry.get("related", [])


def correct_article_summary(session: Session, article: Material, now: datetime) -> None:
    """Revise matching citations while preserving the published issue's selection and date."""
    issues = session.scalars(select(DailyIssue).where(DailyIssue.generated_at <= now))
    for issue in issues:
        content = deepcopy(issue.content)
        for citation in _all_citations(content):
            if citation["itemId"] == article.id and citation["revision"] == article.revision:
                citation["summary"] = article.zh_summary
        if content == issue.content:
            continue
        session.add(DailyIssueRevision(
            issue_key=issue.key, version=issue.version, generated_at=issue.generated_at,
            corrected_at=now, actor="maintenance", reason="更新引用稿件的 AI 导读",
            content=issue.content,
        ))
        issue.content = content
        issue.version += 1


def _current_groupings(session: Session, article_ids: set[str]) -> dict[str, tuple[str, str | None]]:
    return {
        article_id: (fact_id, story_id)
        for article_id, fact_id, story_id in session.execute(
            select(FactReport.material_id, FactReport.fact_id, FactGroup.story_id)
            .join(FactGroup, FactReport.fact_id == FactGroup.id)
            .join(Material, and_(Material.id == FactReport.material_id, Material.revision == FactReport.revision))
            .where(FactReport.material_id.in_(article_ids), FactReport.relation.in_(("primary", "report")),
                   Material.grouping_status == "complete", Material.editorial_scope != "composite")
        )
    }


def _memory(session: Session, key: str) -> tuple[set[str], dict[str, str]]:
    memory_start = (date.fromisoformat(key) - 7 * DAY).isoformat()
    issues = session.scalars(select(DailyIssue).where(DailyIssue.key >= memory_start, DailyIssue.key < key)
                             .order_by(DailyIssue.key.desc())).all()
    known = {entry["itemId"] for issue in issues for entry in _all_citations(issue.content)}
    groupings = _current_groupings(session, known)
    facts = {f"a:{item_id}" for item_id in known}
    stories = {}
    for issue in issues:
        for entry in _all_citations(issue.content):
            if entry["factId"]:
                facts.add(entry["factId"])
            current = groupings.get(entry["itemId"])
            if current is not None:
                facts.add(current[0])
                if current[1]:
                    stories.setdefault(current[1], issue.key)
    return facts, stories


def _report_groups(rows):
    picked = defaultdict(list)
    participants = defaultdict(set)
    for article, fact in rows:
        picked[fact.id if fact else f"a:{article.id}"].append((article, fact))
        if fact and fact.story_id:
            participants[fact.story_id].add(_participant_key(article.source))
    return [FactCandidate(key, members,
                          {article.id: article.revision for article, _ in members},
                          {article.source_id for article, _ in members})
            for key, members in picked.items()], participants


def _citation(article: Material, fact: FactGroup | None, coverage: dict[str, int]) -> dict:
    category = next((topic for topic in article.topics if topic in SECTIONS), "unclassified")
    return {
        "itemId": article.id, "revision": article.revision,
        "factId": fact.id if fact else None, "storyId": fact.story_id if fact else None,
        "title": title_of(article), "summary": article.zh_summary or "",
        "sourceId": article.source_id, "sourceUrl": article.source_url,
        "publishedAt": utc(article.published_at).isoformat() if article.published_at else None,
        "category": category, "coverage": coverage,
    }


def _mentioned_stories(session: Session, ids: set[str]) -> dict[str, set[str]]:
    rows = session.execute(
        select(FactMention.material_id, FactGroup.story_id)
        .join(Material, and_(Material.id == FactMention.material_id, Material.revision == FactMention.revision))
        .join(FactGroup, FactGroup.id == FactMention.fact_id)
        .join(Story, Story.id == FactGroup.story_id)
        .where(FactMention.material_id.in_(ids), Story.merged_into_id.is_(None))
    )
    by_article = defaultdict(set)
    for article_id, story_id in rows:
        by_article[article_id].add(story_id)
    return by_article


def _ranked_entries(session: Session, key: str, rows):
    from .reading import representative_key

    facts, participants = _report_groups(rows)
    seen, previous_stories = _memory(session, key)
    events = defaultdict(list)
    for fact in facts:
        if fact.key in seen or any(f"a:{article.id}" in seen for article, _ in fact.reports):
            continue
        first_group = fact.reports[0][1]
        story_id = first_group.story_id if first_group else None
        events[story_id or fact.key].append(fact)
    mention_by_article = _mentioned_stories(session, {article.id for group in events.values() for fact in group
                                                     for article, grouping in fact.reports if grouping is None})
    result = []
    for event in events.values():
        ordered = sorted(event, key=lambda fact: (-len(fact.sources),
                         min(timeline_at(article) for article, _ in fact.reports), fact.key))
        leaders = [min(fact.reports, key=lambda row: representative_key(*row)) for fact in ordered]
        article, group = leaders[0]
        story_id = group.story_id if group else None
        source_ids = set().union(*(fact.sources for fact in event))
        coverage = {key: revision for fact in event for key, revision in fact.coverage.items()}
        citation = _citation(article, group, coverage)
        if len(leaders) > 1:
            citation["related"] = [_citation(item, fact, {}) for item, fact in leaders[1:]]
        previous = previous_stories.get(story_id)
        if previous:
            citation["followUp"] = previous
        score = max(item.importance_score for fact in event for item, _ in fact.reports)
        authority = representative_key(article, group)[0]
        official = any(representative_key(item, fact)[0] < 3 for member in event for item, fact in member.reports)
        voices = len(participants.get(story_id) or source_ids)
        importance = score + 5 * log2(1 + voices) + (5 if official else 0) - (6 if previous else 0)
        mentions = set().union(*(mention_by_article[item.id] for member in event for item, _ in member.reports))
        result.append(DailyCandidate(citation, story_id, mentions, source_ids, authority, importance))
    result.sort(key=lambda entry: (-entry.importance, entry.citation["itemId"]))
    return result


def _arrange(entries: list[DailyCandidate]) -> tuple[list[dict], list[dict]]:
    stories = {entry.story_id: entry for entry in entries if entry.story_id}
    folded = set()
    for entry in entries:
        matching = [stories[story_id] for story_id in sorted(entry.mentions) if story_id in stories]
        if not matching or entry.story_id:
            continue
        host = max(matching, key=lambda candidate: candidate.importance)
        host.source_ids.update(entry.source_ids)
        host.citation["coverage"].update(entry.citation["coverage"])
        related = {key: value for key, value in entry.citation.items() if key not in {"related", "coverage"}}
        host.citation.setdefault("related", []).extend([related, *entry.citation.get("related", [])])
        folded.add(entry.citation["itemId"])

    live = [entry for entry in entries if entry.citation["itemId"] not in folded]

    def earned(entry: DailyCandidate) -> bool:
        return ("followUp" not in entry.citation
                or (entry.authority < 3 and entry.citation["category"] != "public-opinion")
                or len(entry.source_ids) >= 4)

    any_earned = any(earned(entry) for entry in live)
    quotas = Counter()
    main, flashes = [], []
    for entry in live:
        source = entry.citation["sourceId"]
        if len(main) < MAIN_LIMIT and quotas[source] < SOURCE_LIMIT and (not any_earned or earned(entry)):
            main.append(entry.citation)
            quotas[source] += 1
        else:
            flashes.append(entry.citation)
    return main, flashes


def _empty_lead(start: datetime, end: datetime, coverage: str | None) -> dict[str, str]:
    start, end = start.astimezone(BEIJING), end.astimezone(BEIJING)
    window = (f"{start.month} 月 {start.day} 日 08:00 至 {end.month} 月 {end.day} 日 08:00，")
    return {
        "title": "本期资讯待补" if coverage else "警务科技动态平静",
        "leadParagraph": window + (coverage or "本期采集与研判已完成，暂无可刊资讯。"),
    }


def _coverage_note(stats):
    notes = []
    if stats["pendingReports"]:
        notes.append(f'{stats["pendingReports"]} 篇稿件仍待处理或公开。')
    if stats.get("coverageMeasured", True) and (
            not stats["sourcesExpected"] or stats["sourcesCovered"] < stats["sourcesExpected"]):
        notes.append(f'截止前两小时，{stats["sourcesCovered"]}/{stats["sourcesExpected"]} 个编辑信源完成采集。')
    return "".join(notes) or None


def prepare_daily(session: Session, key: str, now: datetime, *, historical_source_dates: bool | None = None):
    start, end = daily_window(key)
    if end > now:
        raise ValueError("daily_not_due")
    if historical_source_dates is None:
        previous = session.get(DailyIssue, key)
        historical_source_dates = bool(previous and
            previous.content.get("generator", {}).get("inputMode") == "source-date-history")
    rows, candidates, stats = daily_inputs(session, start, end, now,
                                          historical_source_dates=historical_source_dates)
    ranked = _ranked_entries(session, key, rows)
    main, flashes = _arrange(ranked)
    coverage = _coverage_note(stats)
    content = {"main": main, "flashes": flashes, "coverageNote": coverage,
               "quietLead": _empty_lead(start, end, coverage) if not main else None,
               "generator": {"version": VERSION, "eligibleReports": len(rows), "events": len(ranked), **stats}}
    if historical_source_dates:
        content["generator"]["inputMode"] = "source-date-history"
    return content, candidates


def compose_daily(
    session: Session, key: str, *, now: datetime | None = None, reason: str | None = None,
    actor: str | None = None, expected_version: int | None = None, commit: bool = True, refresh: bool = False,
    historical_source_dates: bool | None = None,
) -> dict:
    now = utc(now or now_utc())
    start, end = daily_window(key)
    if end > now:
        raise ValueError("daily_not_due")
    issue = session.get(DailyIssue, key)
    if (reason is not None or actor is not None) and (not reason or not reason.strip() or not actor or not actor.strip()):
        raise ValueError("daily_correction_requires_actor_and_reason")
    if expected_version is not None and (issue is None or issue.version != expected_version):
        raise ValueError("daily_version_changed")
    if issue is not None and reason is None and not refresh:
        return _compose_result(issue.key, issue.content, issue.version, False)
    content, _ = prepare_daily(session, key, now, historical_source_dates=historical_source_dates)
    if issue is not None and issue.content == content:
        return _compose_result(issue.key, issue.content, issue.version, False)
    written = True
    next_version = 1
    if issue is None:
        statement = insert(DailyIssue).values(key=key, version=1, window_start=start, window_end=end,
                                              generated_at=now, content=content)
        written = bool(session.execute(statement.on_conflict_do_nothing(index_elements=[DailyIssue.key])).rowcount)
    else:
        version, old_content, generated_at = issue.version, issue.content, issue.generated_at
        next_version = version + 1
        changed = session.execute(update(DailyIssue).where(DailyIssue.key == key, DailyIssue.version == version)
                                  .values(version=next_version, generated_at=now, content=content)).rowcount
        if not changed:
            raise ValueError("daily_version_changed")
        session.add(DailyIssueRevision(issue_key=key, version=version, generated_at=generated_at,
                                       corrected_at=now, actor=actor.strip() if actor else "worker",
                                       reason=reason.strip() if reason else "补入已完成采集或研判的资讯",
                                       content=old_content))
    if commit:
        session.commit()
    else:
        session.flush()
    return _compose_result(key, content, next_version, written)


def _compose_result(key, content, version, written):
    return {"key": key, "entries": len(content["main"]), "written": written, "version": version,
            "pending": bool(content.get("coverageNote"))}


def compose_due_reports(session: Session, now: datetime | None = None, limit: int = 8, *,
                        retry_from: str | None = None) -> dict:
    now = utc(now or now_utc())
    local = now.astimezone(BEIJING)
    due = local.date() if local.hour >= 8 else local.date() - DAY
    have = {row.key: row.content.get("generator", {}) for row in session.scalars(select(DailyIssue))}
    # With no issues, use the first recorded collection day as the service start.
    first_run = session.scalar(select(func.min(SourceRun.started_at)))
    first_covered = date.fromisoformat(edition_key(first_run)) if first_run else None
    key = min([due, *(date.fromisoformat(label) for label in have), *([first_covered] if first_covered else [])])
    if retry_from:
        retry = date.fromisoformat(retry_from)
        key = min(key, max(retry, first_covered) if first_covered else retry)
    session.rollback()
    generated, updated, pending, failed = [], [], [], []
    errors = {}
    while key <= due and len(generated) + len(updated) < limit:
        label = key.isoformat()
        stats = have.get(label)
        refresh = (stats is not None and stats.get("version") == VERSION
                   and (due - key <= RECOVERY_WINDOW or stats.get("pendingReports", 0) > 0))
        if stats is None or refresh:
            try:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                result = compose_daily(session, label, now=now, refresh=label in have)
                session.commit()
            except Exception as exc:
                session.rollback()
                failed.append(label)
                errors[label] = type(exc).__name__
            else:
                if result["pending"]:
                    pending.append(label)
                if result["written"]:
                    (updated if label in have else generated).append(label)
        key += DAY
    return {"generated": generated, "updated": updated, "pending": pending, "failed": failed, "errors": errors}


def _current_materials(session: Session, ids: set[str]) -> dict[str, Material]:
    by_id = {}
    ordered = sorted(ids)
    for offset in range(0, len(ordered), 500):
        rows = session.scalars(select(Material).options(joinedload(Material.source))
                               .where(Material.id.in_(ordered[offset:offset + 500])))
        by_id.update((item.id, item) for item in rows)
    return by_id


def _available(citation: dict, current: dict[str, Material], now: datetime) -> Material | None:
    material = current.get(citation["itemId"])
    if (material is not None and material.revision == citation["revision"]
            and material.source.participation_mode == "editorial" and public_at(material, now)):
        return material
    return None


def _excluded_by_relevance(citation: dict, current: dict[str, Material]) -> bool:
    article = current.get(citation["itemId"])
    return bool(article is not None and not article.withdrawn and not relevance_allowed(article))


def _public_citation(raw: dict, current: dict[str, Material], now: datetime, *, related: bool = False) -> dict:
    from .reading import public_source_icon

    article = _available(raw, current, now)
    if article is None:
        # Match the original withdrawn citation treatment. The frozen title is struck out by the
        # UI; the withheld story supplies no text, link, provenance or cover.
        return {
            "itemId": raw["itemId"], "title": raw["title"], "summary": None,
            "sourceName": "", "sourceUrl": "", "sourceIconUrl": None,
            "firstParty": False, "publishedAt": None, "available": False,
        }
    result = {
        "itemId": raw["itemId"], "title": raw["title"], "summary": None if related else raw["summary"],
        "sourceName": article.source.name, "sourceUrl": article.source_url,
        "sourceIconUrl": public_source_icon(article.source), "firstParty": article.source.tier == "T1",
        "publishedAt": raw["publishedAt"], "available": True,
    }
    if not related:
        coverage = {current[item_id].source_id for item_id, revision in raw.get("coverage", {}).items()
                    if _available({"itemId": item_id, "revision": revision}, current, now)}
        if len(coverage) > 1:
            result["otherSources"] = len(coverage) - 1
        related_items = [_public_citation(item, current, now, related=True) for item in raw.get("related", [])
                         if not _excluded_by_relevance(item, current)]
        if related_items:
            result["related"] = related_items
        if raw.get("followUp"):
            result["followUp"] = raw["followUp"]
    return result


def _visible_lead(issue: DailyIssue, current: dict[str, Material], now: datetime) -> dict | None:
    return next((raw for raw in issue.content["main"] if _available(raw, current, now)), None)


def _lead_cover(session: Session, lead: Material, now: datetime) -> dict | None:
    from .reading import public_cover, representative_key

    image = public_cover(lead) if lead.source.full_text_allowed else None
    if image and (image["width"] is None or image["width"] >= 480):
        return {**image, "caption": None}
    grouping = _current_groupings(session, {lead.id}).get(lead.id)
    if grouping is None or grouping[1] is None:
        return None
    alternatives = sorted(story_reports(session, grouping[1], now), key=lambda row: representative_key(*row))
    for article, _ in alternatives:
        if article.id == lead.id or not article.source.full_text_allowed:
            continue
        image = public_cover(article)
        if image and (image["width"] is None or image["width"] >= 480):
            return {**image, "caption": None}
    return None


def load_daily(session: Session, key: str, now: datetime | None = None) -> dict | None:
    now = utc(now or now_utc())
    issue = session.get(DailyIssue, key)
    if issue is None or utc(issue.generated_at) > now:
        return None
    ids = {item_id for item in _all_citations(issue.content)
           for item_id in (item["itemId"], *item.get("coverage", {}))}
    current = _current_materials(session, ids)
    raw_lead = _visible_lead(issue, current, now)
    cover = None
    lead = issue.content["quietLead"]
    if raw_lead is not None:
        lead = {"title": raw_lead["title"], "leadParagraph": " ".join(filter(None, (
            raw_lead["summary"], issue.content.get("coverageNote"))))}
        cover = _lead_cover(session, current[raw_lead["itemId"]], now)
    main = [raw for raw in issue.content["main"] if not _excluded_by_relevance(raw, current)]
    projected = [_public_citation(raw, current, now) for raw in main]
    sections = defaultdict(list)
    for raw, view in zip(main, projected):
        sections[raw["category"]].append(view)
    available = [item for item in projected if item["available"]]
    cites = available + [relative for item in available for relative in item.get("related", []) if relative["available"]]
    cited_sources = {current[item["itemId"]].source_id for item in cites}
    prev = session.scalar(select(func.max(DailyIssue.key)).where(DailyIssue.key < key, DailyIssue.generated_at <= now))
    next_key = session.scalar(select(func.min(DailyIssue.key)).where(DailyIssue.key > key, DailyIssue.generated_at <= now))
    number = session.scalar(select(func.count()).select_from(DailyIssue)
                            .where(DailyIssue.key <= key, DailyIssue.generated_at <= now))
    words = sum(len(item["title"]) + len(item["summary"] or "") for item in cites) + len((lead or {}).get("leadParagraph", ""))
    lead_id = raw_lead["itemId"] if raw_lead else None
    return {
        "kind": "daily", "key": key, "issueNumber": number, "title": f"AI日报 · {key}",
        "generatedAt": utc(issue.generated_at).isoformat(), "lead": lead, "leadItemId": lead_id, "overview": None,
        "highlights": [item for item in available if item["itemId"] != lead_id][:3],
        "sections": [{"label": label, "summary": None, "items": sections[slug]}
                     for slug, label in SECTIONS.items() if sections[slug]],
        "flashes": [_public_citation(raw, current, now) for raw in issue.content["flashes"]
                    if not _excluded_by_relevance(raw, current)],
        "cover": cover, "metrics": {"totalEvents": len(main), "sourcesCount": len(cited_sources),
                                     "firstPartyEvents": sum(item["firstParty"] for item in available)},
        "readingMinutes": max(1, floor(words / 450 + 0.5)), "prev": prev, "next": next_key,
    }


def daily_index(session: Session, now: datetime | None = None) -> list[dict]:
    now = utc(now or now_utc())
    released = DailyIssue.generated_at <= now
    total = session.scalar(select(func.count()).select_from(DailyIssue).where(released))
    issues = list(session.scalars(select(DailyIssue).where(released).order_by(DailyIssue.key.desc()).limit(INDEX_LIMIT)))
    current = _current_materials(session, {item["itemId"] for issue in issues for item in issue.content["main"]})
    return [{
        "key": issue.key, "issueNumber": total - index,
        "title": lead["title"] if (lead := _visible_lead(issue, current, now) or issue.content["quietLead"]) else None,
        "count": sum(not _excluded_by_relevance(raw, current) for raw in issue.content["main"]),
    } for index, issue in enumerate(issues)]


def daily_navigation(index: list[dict], key: str) -> list[dict]:
    position = next((n for n, row in enumerate(index) if row["key"] == key), -1)
    return [{
        "key": row["key"], "issueNumber": row["issueNumber"],
        **({"title": row["title"]} if row["key"][:7] == key[:7] or n < 3 or abs(n - position) <= 1 else {}),
    } for n, row in enumerate(index)]
