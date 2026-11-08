"""AIHOT reports/edition.ts, compose.ts and publication/reports.ts for Pulse daily issues.

Copyright (c) 2026 数字生命卡兹克. MIT. See THIRD_PARTY_NOTICES.md.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from math import floor, log2

from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, joinedload

from . import publication
from .edition_evidence import current_signals, public_at, story_reports, timeline_at, title_of, utc
from .edition_models import DailyIssue, DailyIssueRevision
from .editorial_models import FactMention, Story
from .models import FactGroup, FactReport, Material, now_utc


BEIJING = timezone(timedelta(hours=8))
DAY = timedelta(days=1)
MAIN_LIMIT = 12
FLASH_LIMIT = 10
SOURCE_LIMIT = 2
INDEX_LIMIT = 400
VERSION = "daily-v1-rule-based"
SECTIONS = {
    "product": "产品发布与更新", "practice": "警务实战应用", "paper": "论文研究进展",
    "law": "法制政策动态", "embodied": "具身智能装备", "public-opinion": "舆情治理观察",
    "low-altitude": "低空警务应用", "unclassified": "其他警务科技",
}
JUDGED = {"qualified", "below_threshold", "uncalibrated", "complete"}


class DailyUnjudged(ValueError):
    """There is no completed upstream editorial judgement in the issue's window."""


def daily_window(key: str) -> tuple[datetime, datetime]:
    day = date.fromisoformat(key)
    if day.isoformat() != key:
        raise ValueError("invalid_daily_date")
    end = datetime.combine(day, time(8), BEIJING).astimezone(UTC)
    return end - DAY, end


@dataclass(slots=True)
class FactCandidate:
    key: str
    reports: list[tuple[Material, FactGroup | None]]
    coverage: dict[str, int]
    sources: set[str]
    selected: bool


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


def _coverage(session: Session, fact_ids: set[str], cutoff: datetime) -> dict[str, list[Material]]:
    rows = session.execute(
        select(FactReport.fact_id, Material).options(joinedload(Material.source))
        .join(Material, and_(FactReport.material_id == Material.id, FactReport.revision == Material.revision))
        .where(FactReport.fact_id.in_(fact_ids), FactReport.relation.in_(("primary", "report")),
               Material.grouping_status == "complete")
    )
    result = defaultdict(list)
    for fact_id, item in rows:
        if (item.source.participation_mode == "editorial" and item.editorial_scope != "composite"
                and timeline_at(item) < cutoff and public_at(item, cutoff - timedelta(microseconds=1))):
            result[fact_id].append(item)
    return result


def _fact_rows(session: Session, start: datetime, end: datetime):
    timeline = func.coalesce(Material.published_at, Material.published_sort_at, Material.first_seen_at)
    query = (
        select(Material, FactGroup).options(joinedload(Material.source))
        .outerjoin(FactReport, and_(FactReport.material_id == Material.id, FactReport.revision == Material.revision,
                                   FactReport.relation.in_(("primary", "report"))))
        .outerjoin(FactGroup, FactGroup.id == FactReport.fact_id)
        .where(Material.timeline_kind == "fresh", Material.backfill_reason.is_(None),
               Material.public.is_(True), Material.withdrawn.is_(False),
               timeline >= start - DAY, timeline < end)
    )
    cutoff = end - timedelta(microseconds=1)
    return [(article, fact if article.editorial_scope != "composite" else None)
            for article, fact in session.execute(query)
            if article.source.participation_mode == "editorial" and public_at(article, cutoff)]


def _report_groups(session: Session, start: datetime, end: datetime):
    from .reading import representative_key

    rows = _fact_rows(session, start, end)
    picked = defaultdict(list)
    selected_count = 0
    judged = 0
    for article, fact in rows:
        timeline = timeline_at(article)
        if (start <= timeline and article.editorial_revision == article.revision
                and article.selection_status in JUDGED):
            judged += 1
        if article.selected_at is None or not publication.selected(article, at=end):
            continue
        # The issue observes the later of source time, arrival, and actual release/confirmation.
        times = (article.first_seen_at, article.published_public_at, article.visible_after, article.selected_at)
        assigned = max(timeline, *(utc(moment) for moment in times if moment is not None))
        if start <= assigned < end:
            picked[fact.id if fact else f"a:{article.id}"].append((article, fact))
            selected_count += 1

    signals = current_signals(session, start - DAY, end, visible_at=end - timedelta(microseconds=1))
    by_fact, by_story = defaultdict(list), defaultdict(set)
    for signal in signals:
        if signal.fact_id and signal.at < end:
            by_fact[signal.fact_id].append(signal)
        if start <= signal.at < end:
            by_story[signal.story_id].add(signal.participant)

    possible = {}
    for article, fact in rows:
        if fact and article.grouping_status == "complete" and start <= timeline_at(article) < end:
            possible[fact.id] = fact
    fact_ids = set(possible) | {key for key in picked if not key.startswith("a:")}
    coverage = _coverage(session, fact_ids, end)
    fillins = set()
    for fact_id, fact in possible.items():
        if fact_id in picked or utc(fact.anchor_at) < start - DAY:
            continue
        members = coverage[fact_id]
        if any(article.selected_at is not None and utc(article.selected_at) < end
               and publication.selected(article, at=end) for article in members):
            continue
        independent = {signal.participant for signal in by_fact[fact_id]}
        eligible = [article for article in members if article.source.tier != "EXCLUDE_MP"]
        if (len(independent) >= 3 and eligible
                and any(representative_key(article, fact)[0] < 3 for article in eligible)):
            picked[fact_id] = [(article, fact) for article in eligible]
            fillins.add(fact_id)

    facts = []
    for key, members in picked.items():
        cited = {article.id: article.revision for article in coverage[key]}
        cited.update({article.id: article.revision for article, _ in members})
        facts.append(FactCandidate(key, members, cited,
                                   {article.source_id for article in coverage[key]}
                                   | {article.source_id for article, _ in members}, key not in fillins))
    return facts, by_story, judged, selected_count


def _citation(article: Material, fact: FactGroup | None, coverage: dict[str, int]) -> dict:
    category = next((topic for topic in article.topics if topic in SECTIONS), "unclassified")
    return {
        "itemId": article.id, "revision": article.revision,
        "factId": fact.id if fact else None, "storyId": fact.story_id if fact else None,
        "title": title_of(article), "summary": article.zh_summary or "",
        "sourceId": article.source_id, "sourceUrl": article.source_url,
        "publishedAt": timeline_at(article).isoformat(),
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


def _ranked_entries(session: Session, key: str, start: datetime, end: datetime):
    from .reading import representative_key

    facts, participants, judged, selected = _report_groups(session, start, end)
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
        score = max(article.importance_score, *(item.importance_score
                    for fact in event if fact.selected for item, _ in fact.reports), 0)
        authority = representative_key(article, group)[0]
        official = any(representative_key(item, fact)[0] < 3 for member in event for item, fact in member.reports)
        voices = len(participants.get(story_id) or source_ids)
        importance = score + 5 * log2(1 + voices) + (5 if official else 0) - (6 if previous else 0)
        mentions = set().union(*(mention_by_article[item.id] for member in event for item, _ in member.reports))
        result.append(DailyCandidate(citation, story_id, mentions, source_ids, authority, importance))
    result.sort(key=lambda entry: (-entry.importance, entry.citation["itemId"]))
    return result, {"judgedReports": judged, "selectedReports": selected, "events": len(result)}


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
        elif len(flashes) < FLASH_LIMIT:
            flashes.append(entry.citation)
    return main, flashes


def _quiet_lead(start: datetime, end: datetime) -> dict[str, str]:
    start, end = start.astimezone(BEIJING), end.astimezone(BEIJING)
    return {
        "title": "警务科技动态平静",
        "leadParagraph": f"{start.month} 月 {start.day} 日 08:00 至 {end.month} 月 {end.day} 日 08:00，"
                         "本刊已完成资讯研判，暂无需要进入日报的重大进展。",
    }


def compose_daily(
    session: Session, key: str, *, now: datetime | None = None, reason: str | None = None,
    actor: str | None = None, expected_version: int | None = None, commit: bool = True,
) -> dict:
    now = utc(now or now_utc())
    start, end = daily_window(key)
    if end > now:
        raise ValueError("daily_not_due")
    issue = session.get(DailyIssue, key)
    if issue is not None and reason is None:
        return {"key": key, "entries": len(issue.content["main"]), "written": False, "version": issue.version}
    if reason is not None and (not reason.strip() or not actor or not actor.strip()):
        raise ValueError("daily_correction_requires_actor_and_reason")
    if expected_version is not None and (issue is None or issue.version != expected_version):
        raise ValueError("daily_version_changed")
    ranked, stats = _ranked_entries(session, key, start, end)
    if not ranked and not stats["judgedReports"]:
        raise DailyUnjudged("daily_nothing_judged")
    main, flashes = _arrange(ranked)
    content = {"main": main, "flashes": flashes, "quietLead": _quiet_lead(start, end) if not main else None,
               "generator": {"version": VERSION, **stats}}
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
                                       corrected_at=now, actor=actor.strip(), reason=reason.strip(),
                                       content=old_content))
    if commit:
        session.commit()
    else:
        session.flush()
    return {"key": key, "entries": len(main), "written": written, "version": next_version}


def compose_due_reports(session: Session, now: datetime | None = None, limit: int = 8) -> dict:
    now = utc(now or now_utc())
    local = now.astimezone(BEIJING)
    due = local.date() if local.hour >= 8 else local.date() - DAY
    have = set(session.scalars(select(DailyIssue.key)))
    key = date.fromisoformat(min(have)) if have else due
    generated, failed = [], []
    while key <= due and len(generated) < limit:
        label = key.isoformat()
        if label not in have:
            try:
                result = compose_daily(session, label, now=now)
            except DailyUnjudged:
                session.rollback()
                failed.append(label)
            else:
                if result["written"]:
                    generated.append(label)
        key += DAY
    return {"generated": generated, "failed": failed}


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
        if raw.get("related"):
            result["related"] = [_public_citation(item, current, now, related=True) for item in raw["related"]]
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
        lead = {"title": raw_lead["title"], "leadParagraph": raw_lead["summary"]}
        cover = _lead_cover(session, current[raw_lead["itemId"]], now)
    main = issue.content["main"]
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
        "flashes": [_public_citation(raw, current, now) for raw in issue.content["flashes"]],
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
        "count": len(issue.content["main"]),
    } for index, issue in enumerate(issues)]


def daily_navigation(index: list[dict], key: str) -> list[dict]:
    position = next((n for n, row in enumerate(index) if row["key"] == key), -1)
    return [{
        "key": row["key"], "issueNumber": row["issueNumber"],
        **({"title": row["title"]} if row["key"][:7] == key[:7] or n < 3 or abs(n - position) <= 1 else {}),
    } for n, row in enumerate(index)]
