"""AIHOT events/hot.ts and publication/hot.ts, adapted to SQLite.

Copyright (c) 2026 数字生命卡兹克. MIT. See THIRD_PARTY_NOTICES.md.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from math import floor

from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from .edition_evidence import Signal, current_signals, story_reports, timeline_at, title_of, utc
from .edition_models import HotRanking, StoryHeatHour
from .editorial_models import Story
from .models import Source, SourceRun, now_utc
from . import publication


HOUR = timedelta(hours=1)
WINDOW = 48 * HOUR
COMPARISON = 6 * HOUR
HOT_RULE_VERSION = "heat-v1-48h-halflife24h"
TIER_ORDER = {"T1": 0, "T1_5": 1, "T2": 2}


@dataclass(frozen=True, slots=True)
class SourceClock:
    since: datetime | None
    last_success: datetime | None
    grace: timedelta
    enabled: bool

    def behind(self, at: datetime, *, historical: bool = False) -> bool:
        return self.enabled and (
            self.last_success is None
            or self.last_success < (at if historical else at - self.grace)
        )


def source_clocks(session: Session, rows: list[Signal]) -> dict[str, SourceClock]:
    mode = SourceRun.fetch_metrics["mode"].as_string()
    version = SourceRun.fetch_metrics["collection_rule_version"].as_string()
    cover = SourceRun.fetch_metrics["coverage"].as_string()
    succeeded = and_(SourceRun.status.in_(("completed", "no_candidates")),
                     or_(mode.is_(None), mode.not_in(("bounded", "historical"))),
                     or_(version.is_(None), cover == "complete"))
    success_at = case((succeeded, SourceRun.finished_at))
    query = (select(Source.id, Source.enabled, Source.interval_minutes,
                    func.min(SourceRun.started_at), func.max(success_at))
             .outerjoin(SourceRun, SourceRun.source_id == Source.id)
             .where(Source.id.in_({row.source_id for row in rows}))
             .group_by(Source.id, Source.enabled, Source.interval_minutes))
    return {
        source_id: SourceClock(utc(first) if first else None, utc(last) if last else None,
                               timedelta(minutes=max(90, interval * 3)), enabled)
        for source_id, enabled, interval, first, last in session.execute(query)
    }


def _by_story(rows: list[Signal]) -> dict[str, list[Signal]]:
    result = defaultdict(list)
    for row in rows:
        result[row.story_id].append(row)
    return result


def _participants(rows: list[Signal], at: datetime) -> dict[str, list[Signal]]:
    result = defaultdict(list)
    for row in rows:
        if at - WINDOW < row.at <= at:
            result[row.participant].append(row)
    return result


def _heat(groups: dict[str, list[Signal]], at: datetime, exclude: set[str] | None = None) -> float:
    exclude = exclude or set()
    return sum(0.5 ** ((at - max(row.at for row in group)) / HOUR / 24)
               for participant, group in groups.items() if participant not in exclude)


def _index(value: float) -> float:
    return floor(value * 100 + 0.5) / 10


def _fingerprint(rows) -> str:
    evidence = sorted((r.participant, r.article_id, r.revision, r.source_id, r.kind, r.at.isoformat())
                      for r in rows)
    return sha256(repr(evidence).encode()).hexdigest()


def _display_participant(group: list[Signal]) -> Signal:
    return min(group, key=lambda row: (row.kind != "editorial", -row.at.timestamp(), row.article_id))


def _observation_incomplete(
    groups: dict[str, list[Signal]], clocks: dict[str, SourceClock], at: datetime, *, historical: bool = False,
) -> bool:
    return any(clocks[row.source_id].behind(at, historical=historical)
               for group in groups.values() for row in group)


def _ranking_values(rows: list[Signal], clocks: dict[str, SourceClock], at: datetime, first_at: datetime) -> dict:
    current = _participants(rows, at)
    previous_at = at - COMPARISON
    previous = _participants(rows, previous_at)
    excluded = {row.participant for row in rows if previous_at - WINDOW < row.at <= at and (
        clocks[row.source_id].behind(at) or clocks[row.source_id].since is None
        or clocks[row.source_id].since > previous_at - WINDOW
    )}
    before_all = _index(_heat(previous, previous_at))
    before = _index(_heat(previous, previous_at, excluded))
    current_comparable = _index(_heat(current, at, excluded))
    fraction = (current_comparable - before) / before if before else None
    trend = ("new" if not before_all else "unknown" if fraction is None else "up" if fraction > 0.1
             else "down" if fraction < -0.1 else "flat")
    recent = sum(min(row.at for row in group) > previous_at for group in current.values())
    surge = recent >= 3 and recent * 2 >= len(current)
    badges = []
    if surge:
        badges.append("surge")
    if at - first_at < COMPARISON:
        badges.append("new")
    if not surge and fraction is not None and fraction > 0.15:
        badges.append("rising")
    return {
        "heat": _index(_heat(current, at)), "trend": trend,
        "trendPct": None if fraction is None else floor(fraction * 1000 + 0.5) / 10,
        "badges": badges, "participantCount": len(current), "recentParticipants": recent,
        "observationComplete": not _observation_incomplete(current, clocks, at),
    }


def _choose_representative(reports, at: datetime):
    from .reading import representative_key

    by_fact = defaultdict(list)
    for article, fact in reports:
        by_fact[fact.id].append((article, fact))
    if not by_fact:
        return None
    members = min(by_fact.values(), key=lambda group: (
        -len({article.source_id for article, _ in group}),
        min(timeline_at(article) for article, _ in group), group[0][1].id,
    ))
    selected = [row for row in members if publication.selected(row[0], at=at) and utc(row[0].selected_at) <= at]
    return min(selected or members, key=lambda row: representative_key(*row))[0]


def compute_hot_ranking(session: Session, at: datetime | None = None) -> dict:
    at = utc(at or now_utc())
    evidence = current_signals(session, at - WINDOW - COMPARISON, at, visible_at=at)
    clocks = source_clocks(session, evidence)
    candidates = []
    for story_id, rows in _by_story(evidence).items():
        groups = _participants(rows, at)
        if len(groups) >= 2 and any(_display_participant(group).kind == "editorial" for group in groups.values()):
            candidates.append((_heat(groups, at), max(row.at for row in rows), story_id, rows))
    candidates.sort(key=lambda row: (-row[0], -row[1].timestamp(), row[2]))
    entries = []
    for _, _, story_id, rows in candidates:
        if len(entries) == 10:
            break
        reports = story_reports(session, story_id, at)
        representative = _choose_representative(reports, at)
        if representative is None:
            continue
        first_at = min(timeline_at(article) for article, _ in reports)
        entries.append({
            "rank": len(entries) + 1, "storyId": story_id, "itemId": representative.id,
            "revision": representative.revision, "evidenceHash": _fingerprint(rows),
            **_ranking_values(rows, clocks, at, first_at),
        })
    evidence_record = {
        "windowHours": 48, "halfLifeHours": 24, "minParticipants": 2, "candidates": len(candidates),
        "behindSources": sorted(source_id for source_id, clock in clocks.items() if clock.behind(at)),
    }
    values = {"computed_at": at, "rule_version": HOT_RULE_VERSION, "entries": entries, "evidence": evidence_record}
    statement = insert(HotRanking).values(**values)
    session.execute(statement.on_conflict_do_nothing(index_elements=[HotRanking.computed_at]))
    session.execute(delete(HotRanking).where(HotRanking.computed_at < at - timedelta(days=30)))
    session.commit()
    return {"computedAt": at.isoformat(), "entries": len(entries)}


def _save_hour(session: Session, story_id: str, hour: datetime, groups: dict[str, list[Signal]], complete: bool) -> None:
    values = {
        "story_id": story_id, "hour": hour, "heat": _index(_heat(groups, hour)),
        "participants": len(groups), "cohort": sum(_display_participant(g).kind == "editorial" for g in groups.values()),
        "complete": complete, "evidence_hash": _fingerprint(r for group in groups.values() for r in group),
    }
    statement = insert(StoryHeatHour).values(**values)
    updates = {key: statement.excluded[key] for key in values if key not in {"story_id", "hour"}}
    session.execute(statement.on_conflict_do_update(index_elements=["story_id", "hour"], set_=updates))


def snapshot_heat(session: Session, at: datetime | None = None) -> dict[str, int]:
    at = utc(at or now_utc())
    hour = at.replace(minute=0, second=0, microsecond=0)
    stale = session.execute(
        select(StoryHeatHour.story_id, StoryHeatHour.hour)
        .where(StoryHeatHour.complete.is_(False), StoryHeatHour.hour < hour,
               StoryHeatHour.hour > hour - WINDOW)
    ).all()
    first = min((utc(past) for _, past in stale), default=hour)
    evidence = current_signals(session, first - WINDOW, hour, visible_at=at)
    clocks = source_clocks(session, evidence)
    grouped = _by_story(evidence)
    stories = repaired = 0
    for story_id, rows in grouped.items():
        groups = _participants(rows, hour)
        if groups:
            _save_hour(session, story_id, hour, groups, not _observation_incomplete(groups, clocks, hour))
            stories += 1
    for story_id, past in stale:
        past = utc(past)
        groups = _participants(grouped.get(story_id, []), past)
        if groups and not _observation_incomplete(groups, clocks, past, historical=True):
            _save_hour(session, story_id, past, groups, True)
            repaired += 1
    session.commit()
    return {"stories": stories, "repaired": repaired}


def _spark(session: Session, story_id: str, at: datetime, now: datetime) -> list[float | None]:
    hour = at.replace(minute=0, second=0, microsecond=0)
    start = hour - 24 * HOUR
    points = {utc(row.hour): row for row in session.scalars(
        select(StoryHeatHour).where(StoryHeatHour.story_id == story_id, StoryHeatHour.complete.is_(True),
                                    StoryHeatHour.hour >= start, StoryHeatHour.hour <= hour))}
    evidence = current_signals(session, start - WINDOW, hour, visible_at=now, story_ids={story_id})
    clocks = source_clocks(session, evidence)
    output = []
    for index in range(25):
        at = start + index * HOUR
        point = points.get(at)
        value = None
        if point is not None:
            groups = _participants(evidence, at)
            if _fingerprint(r for group in groups.values() for r in group) == point.evidence_hash:
                value = point.heat
            elif groups and not _observation_incomplete(groups, clocks, at, historical=True):
                value = _index(_heat(groups, at))
        output.append(value)
    return output


def _latest_ranking(session: Session, now: datetime) -> HotRanking | None:
    return session.scalar(select(HotRanking).where(HotRanking.computed_at <= now)
                          .order_by(HotRanking.computed_at.desc()).limit(1))


def _public_ranking(session: Session, ranking: HotRanking, now: datetime):
    from .reading import public_source_icon

    at = utc(ranking.computed_at)
    story_ids = {entry["storyId"] for entry in ranking.entries}
    # Recheck permissions against today's records, but retain the ranking's release cutoff.
    evidence = current_signals(session, at - WINDOW - COMPARISON, at, visible_at=at, story_ids=story_ids)
    clocks = source_clocks(session, evidence)
    stories = _by_story(evidence)
    for stored in ranking.entries:
        story_id = stored["storyId"]
        story = session.get(Story, story_id)
        if story is None or story.merged_into_id is not None:
            continue
        reports = story_reports(session, story_id, now)
        representative = next((row for row in reports if row[0].id == stored["itemId"]
                               and row[0].revision == stored["revision"]), None)
        rows = stories.get(story_id, [])
        people = [_display_participant(group) for group in _participants(rows, at).values()]
        if representative is None or len(people) < 2 or not any(row.kind == "editorial" for row in people):
            continue
        first_at = min(timeline_at(article) for article, _ in reports)
        values = (stored if _fingerprint(rows) == stored["evidenceHash"]
                  else _ranking_values(rows, clocks, at, first_at))
        article = representative[0]
        sources = {source.id: source for source in session.scalars(
            select(Source).where(Source.id.in_({p.source_id for p in people})))}
        icons = {p.source_id: public_source_icon(sources[p.source_id])
                 for p in people if p.kind == "editorial"}
        people.sort(key=lambda row: (row.kind != "editorial", TIER_ORDER.get(row.tier, 3),
                                     not icons.get(row.source_id), -row.at.timestamp(), row.source_id))
        participants = {}
        for person in people[:40]:
            if person.name in participants or not person.name.strip():
                continue
            view = {"name": person.name, "kind": person.kind}
            icon = icons.get(person.source_id)
            if person.kind == "editorial" and len(participants) < 6:
                view["iconUrl"] = icon
            participants[person.name] = view
        source_names = list(dict.fromkeys(row.name for row in sorted(people, key=lambda p: -p.at.timestamp())
                                          if row.kind == "editorial"))[:8]
        founding = min(reports, key=lambda row: (timeline_at(row[0]), row[0].id))[0]
        # A once-current founding title must not outlive its evidence.
        title = story.title if story.title in {title_of(item) for item, _ in reports} else title_of(founding)
        cover_order = sorted(reports, key=lambda row: (
            row[0].id != article.id, row[0].source.tier != "T1",
            not publication.selected(row[0], at=now), -row[0].importance_score, row[0].id,
        ))
        yield {
            "rank": stored["rank"], "story": {"publicId": story_id, "title": title},
            **{key: values[key] for key in ("heat", "trend", "trendPct", "badges", "participantCount")},
            "sourceCount": sum(row.kind == "editorial" for row in people), "sourceNames": source_names,
            "participants": list(participants.values()),
        }, article, cover_order


def load_hot(session: Session, now: datetime | None = None) -> dict:
    from .reading import public_cover

    now = utc(now or now_utc())
    ranking = _latest_ranking(session, now)
    if ranking is None:
        return {"computedAt": None, "windowHours": 48, "entries": []}
    at = utc(ranking.computed_at)
    entries = []
    for view, article, reports in _public_ranking(session, ranking, now):
        summary = article.zh_summary or None
        latest = max((item for item, _ in reports), key=lambda item: (timeline_at(item), item.id))
        cover = next((image for item, _ in reports if item.source.full_text_allowed and (image := public_cover(item))
                      and (image["width"] is None or image["width"] >= 480)), None)
        entries.append({
            **view, "spark": _spark(session, view["story"]["publicId"], at, now),
            "summary": summary[:480] + "…" if summary and len(summary) > 480 else summary,
            "latest": title_of(latest), "cover": cover,
        })
    return {"computedAt": at.isoformat(), "windowHours": 48, "entries": entries}


def load_hot_strip(session: Session, now: datetime | None = None) -> list[dict] | None:
    now = utc(now or now_utc())
    ranking = _latest_ranking(session, now)
    if ranking is None:
        return None
    entries = [{
        "rank": view["rank"], "title": view["story"]["title"], "heat": view["heat"],
        "trend": view["trend"], "storyPublicId": view["story"]["publicId"], "itemId": article.id,
        "participants": view["participants"], "participantCount": view["participantCount"],
    } for view, article, _ in _public_ranking(session, ranking, now)]
    return entries[:5] if len(entries) >= 3 else None


def heat_series(session: Session, story_id: str, now: datetime | None = None, days: int = 7) -> list[dict]:
    now = utc(now or now_utc())
    hours = [utc(hour) for hour in session.scalars(
        select(StoryHeatHour.hour)
        .where(StoryHeatHour.story_id == story_id, StoryHeatHour.complete.is_(True),
               StoryHeatHour.hour > now - timedelta(days=days), StoryHeatHour.hour <= now)
        .order_by(StoryHeatHour.hour))]
    if not hours:
        return []
    since = hours[0] - WINDOW
    evidence = current_signals(session, since, now, visible_at=now, story_ids={story_id})
    clocks = source_clocks(session, evidence)
    late = {row.participant for row in evidence if clocks[row.source_id].since is None
            or clocks[row.source_id].since > since}
    output = []
    for hour in hours:
        groups = _participants(evidence, hour)
        output.append({"hour": hour.isoformat(), "heat": _index(_heat(groups, hour, late)),
                       "participants": len(groups.keys() - late)})
    return output if any(row["heat"] > 0 for row in output) else []


def story_heat(session: Session, story_id: str, now: datetime | None = None) -> dict:
    now = utc(now or now_utc())
    rows = current_signals(session, now - WINDOW, now, visible_at=now, story_ids={story_id})
    groups = _participants(rows, now)
    clocks = source_clocks(session, rows)
    ranking = _latest_ranking(session, now)
    rank = None
    if ranking and any(entry["storyId"] == story_id for entry in ranking.entries):
        rank = next((view["rank"] for view, _, _ in _public_ranking(session, ranking, now)
                     if view["story"]["publicId"] == story_id), None)
    return {
        "whyHot": {
            "participants48h": len(groups),
            "newParticipants6h": sum(min(row.at for row in group) > now - COMPARISON for group in groups.values()),
            "recentReports24h": len({row.article_id for row in rows
                                     if row.kind == "editorial" and row.at > now - 24 * HOUR}),
            "observationComplete": bool(groups) and not _observation_incomplete(groups, clocks, now),
            "rank": rank,
        },
        "heat": heat_series(session, story_id, now),
    }
