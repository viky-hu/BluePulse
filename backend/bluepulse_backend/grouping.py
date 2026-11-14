"""Article–Fact–Story grouping adapted from AIHOT's events/group and recall."""
from dataclasses import dataclass
from datetime import timedelta
import math

from sqlalchemy import delete, select, update

from .editorial import SAFETY, input_hash
from .editorial_models import FactMention, Story, StorySignal
from .models import FactGroup, FactReport, Material, now_utc
from .publication import selected, visible
from .work_queue import utc


RELATION_RULES = """
先识别每篇报道的具体发生（主体、动作、对象、时间、地域和阶段），再逐对判断。摘要漏写的条件用附带的原文引文核对。
SAME_OCCURRENCE：同一个主体在同一时点对同一具体对象做的同一件事。不同语言、报道角度、发布媒介或内容详略不改变发生身份。
SAME_STORY：围绕同一个具体发生且有证据支持的直接后续，如某项目招标之后的成交、同一试点后续的验收、明确针对该项目的评估或回应。必须能连到根事实；同一主体的两个独立项目、同一产品的日常更新，不能只凭主题或时间先后归并。
ROUNDUP：一篇材料实质汇集多个可独立成条的发生，只把另一方作为其中一项。先检查是否为综合提及，综合稿不能替代事实或成为合并理由。用其他事情做背景或对比不算综合稿。
UNRELATED：缺乏具体发生或直接后续的联系，包括只共享机构、时间、地点、议题、装备名称或会议。
区分同一次与后续时，问两篇都成立时，是同一件事，还是先后发生了两件有直接关系的事。证据不全时降低置信度，不凭名称补足联系。"""
GROUP = SAFETY + RELATION_RULES + """
每个候选 C1、C2…恰好一项。另判断 selection：与标为 selected 的公开精选对照，实际出现的新动作、证据、结论、适用条件或可复用方法才算新增。未精选的候选只用于身份判断；没有已精选对照时 addsValue=true。同一次发生如已有精选代表，其他独立来源或更完整的一手报道保留代表竞争资格。换措辞或转载不构成新增；信息增量与事件身份分别判断。
只输出 JSON {decisions:[{id,relation,confidence}],selection:{addsValue,reason}}。confidence 范围 0–1，reason 只写一句具体新增或已覆盖的事实，供内部使用。"""
PAIR = SAFETY + RELATION_RULES + """
按同样规则复核当前两篇材料。只输出 JSON {relation,confidence}，confidence 范围 0–1。"""
RELATIONS = {"SAME_OCCURRENCE", "SAME_STORY", "ROUNDUP", "UNRELATED"}


@dataclass(frozen=True)
class CandidateFact:
    fact_id: str
    story_id: str
    title: str
    summary: str
    similarity: float
    root: bool
    selected: bool
    frame: dict | None = None


def _frame(article):
    if article.editorial_revision == article.revision:
        return (article.editorial_data or {}).get("fact")
    return None


@dataclass(frozen=True)
class Decision:
    fact_id: str | None = None
    story_id: str | None = None
    mentions: tuple[str, ...] = ()
    adds_value: bool = False
    creates_fact: bool = False
    signal_only: bool = False


def lexical_similarity(left: str, right: str) -> float:
    def bigrams(text):
        text = "".join(text.split())
        return {text[i:i + 2] for i in range(len(text) - 1)}

    a, b = bigrams(left), bigrams(right)
    return len(a & b) / min(len(a), len(b)) if a and b else 0


def _cosine(a, b):
    denom = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / denom if denom and len(a) == len(b) else 0


def recall(session, material, now, vectors=None) -> list[CandidateFact]:
    rows = session.execute(select(FactGroup, FactReport, Material).join(
        FactReport, FactReport.fact_id == FactGroup.id).join(
        Material, Material.id == FactReport.material_id).join(
        Story, Story.id == FactGroup.story_id).where(
        FactGroup.anchor_at >= now - timedelta(days=14),
        Story.merged_into_id.is_(None), Material.id != material.id,
        FactReport.revision == Material.revision,
        FactReport.relation.in_(("primary", "report")), Material.grouping_status == "complete",
    ).order_by(FactGroup.anchor_at, FactGroup.id)).all()
    signal_only = material.source.participation_mode == "hot_signal"
    query = f"{material.zh_title or material.source_title}。{(material.zh_summary or material.source_summary or '')[:300]}"
    rows = [(fact, member, other) for fact, member, other in rows
            if other.editorial_scope != "composite" and visible(other, at=now)]
    candidates: dict[str, CandidateFact] = {}
    first = {}
    story_ids = {fact.story_id for fact, _, _ in rows}
    if story_ids:
        roots = session.execute(select(FactGroup, Material).join(
            FactReport, FactReport.fact_id == FactGroup.id).join(
            Material, Material.id == FactReport.material_id).where(
            FactGroup.story_id.in_(story_ids), FactReport.revision == Material.revision,
            FactReport.relation.in_(("primary", "report")), Material.grouping_status == "complete",
        ).order_by(FactGroup.anchor_at, FactGroup.id))
        for fact, report in roots:
            if report.editorial_scope != "composite" and visible(report, at=now):
                first.setdefault(fact.story_id, fact.id)
    texts = [query, *(f"{row.zh_title or row.source_title}。{(row.zh_summary or '')[:300]}"
                      for _, _, row in rows)]
    embeddings = vectors(texts) if vectors and rows else None
    for index, (fact, _, other) in enumerate(rows):
        similarity = (_cosine(embeddings[0], embeddings[index + 1]) if embeddings else
                      lexical_similarity(query, texts[index + 1]))
        if signal_only and not embeddings:
            similarity = max(similarity, lexical_similarity(query, other.source_title))
        if similarity < (0.6 if embeddings else 0.25):
            continue
        previous = candidates.get(fact.id)
        candidate = CandidateFact(fact.id, fact.story_id, fact.title, other.zh_summary or "",
                                  similarity, first[fact.story_id] == fact.id,
                                  selected(other, at=now) or bool(previous and previous.selected), _frame(other))
        if previous and previous.similarity > similarity:
            candidate = CandidateFact(previous.fact_id, previous.story_id, previous.title, previous.summary,
                                      previous.similarity, previous.root, candidate.selected, previous.frame)
        candidates[fact.id] = candidate
    return sorted(candidates.values(), key=lambda x: (-x.similarity, x.fact_id))[:4 if signal_only else 10]


def _verdict(item):
    relation, confidence = item.get("relation"), item.get("confidence")
    if relation not in RELATIONS or type(confidence) not in {int, float} or not 0 <= confidence <= 1:
        raise ValueError("invalid_grouping_verdict")
    return relation, confidence


def decide(material, candidates: list[CandidateFact], step) -> Decision:
    frame = (material.editorial_data or {}).get("fact")
    signal = bool(material.source and material.source.participation_mode == "hot_signal")
    if not signal and material.editorial_scope == "unknown" and not frame:
        return Decision()
    if material.timeline_kind in {"backfill", "historical"} or (
        not signal and not material.relevant and material.relevant is not None
    ):
        return Decision()
    query = {"title": material.zh_title or material.source_title,
             "summary": material.zh_summary or (material.source_summary or material.source_body or "")[:500],
             "scope": material.editorial_scope, "fact": frame}
    if not candidates:
        creates_fact = not signal and material.editorial_scope != "composite"
        return Decision(creates_fact=creates_fact, adds_value=creates_fact)
    index = {f"C{n}": candidate for n, candidate in enumerate(candidates, 1)}
    output, _ = step("group", "group", GROUP, {"article": query, "candidates": [
        {"id": id, "title": item.title, "summary": item.summary, "fact": item.frame,
         "storyRoot": item.root, "selected": item.selected} for id, item in index.items()
    ]}, 2200)
    decisions = output.get("decisions")
    if not isinstance(decisions, list) or len(decisions) != len(index) or (
        {item.get("id") for item in decisions if isinstance(item, dict)} != set(index)
    ):
        raise ValueError("incomplete_grouping_verdicts")
    verdicts = {item["id"]: _verdict(item) for item in decisions}
    if material.editorial_scope == "composite":
        mentions = tuple(index[id].fact_id for id, (relation, confidence) in verdicts.items()
                         if relation != "UNRELATED" and confidence >= .8)
        return Decision(mentions=mentions)
    occurrences = sorted((id for id, v in verdicts.items() if v[0] == "SAME_OCCURRENCE"),
                         key=lambda id: (-verdicts[id][1], -index[id].similarity))
    if signal:
        target = next((index[id] for id in occurrences if verdicts[id][1] >= .8), None)
        target = target or next((index[id] for id, v in verdicts.items() if v[0] == "SAME_STORY" and v[1] >= .8), None)
        return Decision(story_id=target.story_id if target else None, signal_only=True)
    selection = output.get("selection")
    has_selected = any(item.selected for item in candidates)
    if has_selected and (not isinstance(selection, dict) or type(selection.get("addsValue")) is not bool):
        raise ValueError("invalid_grouping_selection")
    adds_value = not has_selected or selection["addsValue"]
    for id in occurrences:
        candidate = index[id]
        if candidate.similarity >= .85 and verdicts[id][1] >= .8:
            relation = "SAME_OCCURRENCE"
        else:
            review, _ = step("groupReview", f"pair:{id}", PAIR,
                             {"article": query, "candidate": {"title": candidate.title, "summary": candidate.summary,
                                                                "fact": candidate.frame}}, 450)
            relation, confidence = _verdict(review)
            if confidence < .75:
                continue
        if relation == "SAME_OCCURRENCE":
            return Decision(candidate.fact_id, candidate.story_id, adds_value=adds_value or candidate.selected)
        if relation == "SAME_STORY" and candidate.root:
            return Decision(story_id=candidate.story_id, adds_value=adds_value, creates_fact=True)
    root = next((index[id] for id, (relation, confidence) in verdicts.items()
                 if relation == "SAME_STORY" and index[id].root and confidence >= .75), None)
    return Decision(story_id=root.story_id if root else None, adds_value=adds_value, creates_fact=True)


def apply_grouping(session, material, decision, now, override: dict):
    member = session.get(FactReport, material.id)
    manual = bool(material.standalone or member and member.manual)
    session.execute(delete(StorySignal).where(StorySignal.material_id == material.id))
    session.execute(delete(FactMention).where(FactMention.material_id == material.id))
    story_id = decision.story_id
    if manual:
        if member and member.manual:
            member.revision = material.revision
            story_id = session.get(FactGroup, member.fact_id).story_id
        else:
            story_id = None
    elif decision.creates_fact or decision.fact_id:
        frame = (material.editorial_data or {}).get("fact") or {}
        title = frame.get("title") or material.zh_title or material.source_title
        fact = session.get(FactGroup, decision.fact_id) if decision.fact_id else None
        if decision.fact_id and fact is None:
            raise ValueError("group_target_changed")
        if fact is None:
            key = input_hash(f"semantic:{material.id}:{material.revision}")
            fact = session.scalar(select(FactGroup).where(FactGroup.identity_key == key))
            if fact is None:
                story = session.get(Story, story_id) if story_id else None
                if story is None:
                    story = Story(title=title)
                    session.add(story)
                    session.flush()
                elif story.merged_into_id:
                    raise ValueError("group_target_changed")
                fact = FactGroup(identity_key=key, title=title, story_id=story.id,
                                 subject=frame.get("subject"), anchor_at=material.published_sort_at or material.first_seen_at)
                session.add(fact)
                session.flush()
        story_id = fact.story_id
        if member is None:
            member = FactReport(material_id=material.id, fact_id=fact.id, revision=material.revision)
            session.add(member)
        member.fact_id, member.revision, member.grouped_at = fact.id, material.revision, now
        member.relation = "report" if decision.fact_id else "primary"
    elif member:
        session.delete(member)
    for fact_id in decision.mentions:
        if session.get(FactGroup, fact_id):
            session.add(FactMention(fact_id=fact_id, material_id=material.id, revision=material.revision))
    if story_id and material.published_at and material.timeline_kind == "fresh" and material.source.participation_mode != "isolated":
        session.add(StorySignal(story_id=story_id, material_id=material.id, revision=material.revision,
                               observed_at=material.published_at,
                               participant_key=material.source.participant_key or material.source_id,
                               kind="signal" if decision.signal_only else "editorial"))
    material.grouping_value = bool(manual or decision.adds_value or override.get("selected") is True)
    material.grouping_status = "complete"
    if material.featured_candidate and material.grouping_value and material.timeline_kind == "fresh" and visible(material, at=now):
        material.selected_at = material.selected_at or now


def correct_membership(session, material_id, *, fact_id: str | None, standalone: bool) -> bool:
    material = session.get(Material, material_id)
    fact = session.get(FactGroup, fact_id) if fact_id else None
    if material is None or (fact_id and fact is None) or bool(fact_id) == standalone:
        return False
    member = session.get(FactReport, material_id)
    material.standalone = standalone
    if standalone and member:
        session.delete(member)
    elif fact:
        if member is None:
            member = FactReport(material_id=material_id, fact_id=fact.id, revision=material.revision)
            session.add(member)
        member.manual, member.fact_id, member.relation = True, fact.id, "report"
    session.flush()
    apply_grouping(session, material, Decision(), now_utc(), {})
    return True


def merge_stories(session, from_id, into_id) -> bool:
    source, target = session.get(Story, from_id), session.get(Story, into_id)
    if not source or not target or from_id == into_id or source.merged_into_id or target.merged_into_id:
        return False
    session.execute(update(FactGroup).where(FactGroup.story_id == from_id).values(story_id=into_id))
    for signal in session.scalars(select(StorySignal).where(StorySignal.story_id == from_id)):
        old = session.get(StorySignal, (into_id, signal.material_id))
        if old is None:
            signal.story_id = into_id
        elif utc(signal.observed_at) > utc(old.observed_at):
            old.observed_at, old.revision = signal.observed_at, signal.revision
            session.delete(signal)
        else:
            session.delete(signal)
    session.execute(update(Story).where(Story.merged_into_id == from_id).values(merged_into_id=into_id))
    source.merged_into_id = into_id
    return True
