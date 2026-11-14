"""Current-evidence event summaries, adapted from AIHOT events/digest.ts."""
import json

from .edition_evidence import story_reports, timeline_at, title_of
from .editorial import SAFETY, input_hash
from .editorial_models import StoryDigest
from .work_queue import enqueue


DIGEST = SAFETY + """
为第一次了解事件的读者写中文事件概览。首句直接交代谁做了什么、核心变化及最新可核实的结果。之后只补理解事件所必需的背景、适用条件或分歧，不逐条复述时间线。
通常100–300字、1–3个短段。事实少就写短一些。用具体主体、动作和结果写清各方所做的事，省去报道数量、采集情况、履历、宣传语和资料完整性评价。
只以同一事件的当前主报道与跟进报道为依据。适用对象、地域、规模和限制必须绑定相应事实。宣布、试点、采购、部署和实际效果分开写；宣传或引用只支持相应来源的主张。影响结论的报道分歧、修正要明确归属及先后。没有依据的数字、实体及结论不要写。
只输出 JSON {digest}。"""
DIGEST_VERSION = input_hash(DIGEST)


def _digest_reports(session, story_id, now):
    rows = sorted(story_reports(session, story_id, now),
                  key=lambda row: (timeline_at(row[0]), row[0].id))
    return [
        {"id": article.id, "revision": article.revision, "fact": fact.id,
         "at": timeline_at(article).isoformat(), "source": article.source.name,
         "title": title_of(article), "summary": article.zh_summary,
         "evidence": ((article.editorial_data or {}).get("fact")
                      if article.editorial_revision == article.revision else None)}
        for article, fact in rows
    ]


def digest_context(session, story_id, now):
    reports = _digest_reports(session, story_id, now)
    return input_hash(json.dumps([DIGEST_VERSION, reports], ensure_ascii=False, sort_keys=True)), reports[-40:]


def schedule_digest(session, story_id, now, run_key):
    if not story_id:
        return
    key, reports = digest_context(session, story_id, now)
    if len(reports) >= 2 and not session.get(StoryDigest, (story_id, key)):
        enqueue(session, "digest", f"{story_id}:{key}",
                {"story_id": story_id, "input_hash": key, "run_key": run_key}, now)


def save_digest(session, story_id, key, digest, now):
    current, reports = digest_context(session, story_id, now)
    if len(reports) < 2 or current != key:
        return False
    if session.get(StoryDigest, (story_id, key)) is None:
        session.add(StoryDigest(story_id=story_id, input_hash=key, digest=digest, generated_at=now))
    return True


def load_digest(session, story_id, now):
    reports = _digest_reports(session, story_id, now)
    if len(reports) < 2:
        return None
    key = input_hash(json.dumps([DIGEST_VERSION, reports], ensure_ascii=False, sort_keys=True))
    current = session.get(StoryDigest, (story_id, key))
    if current:
        return current
    legacy_reports = [{name: value for name, value in row.items() if name != "evidence"} for row in reports]
    legacy_key = input_hash(json.dumps(legacy_reports, ensure_ascii=False, sort_keys=True))
    return session.get(StoryDigest, (story_id, legacy_key))
