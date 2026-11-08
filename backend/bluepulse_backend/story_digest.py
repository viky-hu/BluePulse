"""Current-evidence event summaries, adapted from AIHOT events/digest.ts."""
import json

from .edition_evidence import story_reports, timeline_at, title_of
from .editorial import SAFETY, input_hash
from .editorial_models import StoryDigest
from .work_queue import enqueue


DIGEST = SAFETY + """按报道时间梳理同一警务科技事件，交代发生了什么、最新可核实的进展以及来源明确的分歧。
如后续报道修正先前表述，应注明修正。不要把宣布、采购和部署效果混为一谈。不使用材料以外的人名、数字和结论。
返回 JSON {digest}，digest 用中文。"""


def digest_context(session, story_id, now):
    rows = sorted(story_reports(session, story_id, now),
                  key=lambda row: (timeline_at(row[0]), row[0].id))
    reports = [
        {"id": article.id, "revision": article.revision, "fact": fact.id,
         "at": timeline_at(article).isoformat(), "source": article.source.name,
         "title": title_of(article), "summary": article.zh_summary}
        for article, fact in rows
    ]
    return input_hash(json.dumps(reports, ensure_ascii=False, sort_keys=True)), reports[-40:]


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
    key, reports = digest_context(session, story_id, now)
    return session.get(StoryDigest, (story_id, key)) if len(reports) >= 2 else None
