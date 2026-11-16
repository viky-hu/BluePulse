"""Pulse port of AIHOT's editorial analyze and translation stages."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re

from sqlalchemy import delete

from .editorial_copy import (COPY_VERSION, REWRITE_SELECTED, REWRITE_SUMMARY, SAFETY, SUMMARIZE,
                             UNDERSTAND, grounded_reading_value, summary_copy, title_copy)
from .live_model import DEFAULT_MODEL_ENV, SCORE_PROMPT
from .models import MaterialTopic
from .pipeline import PUBLIC_TOPIC_SLUGS
from .public_metadata import entity_slug
from .publication import evidence_allowed, project_visibility
from .selection_scoring import AXES, SelectionScore


PREFILTER = SAFETY + """
判定这条材料是否有实质性的警务科技关联，这是进入「全部动态」的第一道门槛。先读标题和正文，找出这次报道实际发生了什么，以及具体技术、技术治理或实战方法怎样关联一项警务或公共安全任务。新颖性、价值高低、时效和精选资格另外判断。
- PASS / direct：主要内容是有具体对象与用途的警务技术应用、试点、研究、建设、运维，或直接研究、评估、规范这类技术的实际应用。
- PASS / potential：报道以其他内容为主，但给出了值得追踪的具体技术应用或实战方法改进线索；也包括具有具体能力变化和明确警务应用路径的上游进展。理由写清线索怎样用于哪项任务。
- BLOCK / irrelevant：原文明确只涉及普通案件、会议、宣传、人事、活动、行政流程、常规防护或一般装备采购，或者笼统提到系统、智能、监控等，找不到具体技术用途或改进线索。
- UNKNOWN / uncertain：内容不足以作出上述判断，例如只有采购时间更正而采购对象和用途未载明，或只能靠附件猜测。标题已同时说明具体技术和警务任务时可以据标题判断。
采购先看本次采购对象和实际用途。采购单位是公安、消防、法院或应急部门，或标的含通用摄像机、门禁、消防报警器，均不能据此认定警务科技相关。说明用于道路违法取证的设备改造、警务专用视频网络运维等则可相关。更正、终止或成交公告仅用本篇明确交代的项目证据判断。
判断示例：
- 对警务人脸识别独立测试误识率与阈值，或公布人脸识别警务应用的专项公众调查：direct。
- 普通巡防报道明确写到用数字化平台联动巡防力量、支持走失人员寻回：potential。
- 联合打击手机盗窃，只有通用 IMEI 核验建议，缺少具体改进内容：uncertain。
- 江苏公安通报五起新型黑恶案件并给出防范提示，无科技研判措施；科技机构组织公益步行和虚拟跑步；警服及普通装备招标；仅提供电视节目受影响者支持渠道：irrelevant。
只输出 JSON {label,relevance,reason,evidence}。reason 是一句话。PASS 必须提供标题或正文中一段连续原文，足以支撑理由所说的技术或改进线索和用途，禁止拼接、翻译、把常识当证据。非 PASS 的 evidence 可为 null。"""
STRUCTURE = SAFETY + """
只做结构化提取。先读正文，识别这份材料自己的核心行动及用途。按正文重心分类，不以发布机构、原有产品名称或偶然提及的技术分类。不写面向读者的摘要，不打分。
category 从 product、practice、paper、law、embodied、public-opinion、low-altitude、other 中选一个主要类别，分别表示产品、实战、论文、法制、具身智能、舆情治理、低空警务、其它。优先选择有正文依据且贴切的前七类；确实涉及警务科技或有具体应用线索、但前七类都不贴切时选 other。不能因为普通警务报道不好分类就选 other；分类不代替相关性判断，也不决定是否精选。分类必须明确给出，不得省略或返回 null。
tags 是 0–6 个与当前主要信息一致、能在正文逐字找到的技术、方法、业务对象或项目阶段短词。省略通用采购条款、预算、投标资格和随手提及的词。没有明确标签时返回空数组。entities 为最多6个 {name,type,evidence}，type 为 vendor、model、organization，evidence 必须逐字含名称。
scope：single 表示一个具体发生或一项独立研究、评测、方法；composite 表示实质报道多个可独立成条的发生，同一机构、日期、会议或议题不足以合为一次；只作背景或比较不算独立条目；无法判断范围为 unknown。
fact 是 {title,subject,action,object,occurredAt,evidence,conditions} 或 null。抽取本次报道的动作，区分拟议、采购、测试、部署、复盘和实地效果。旧发布只作背景。主体是行动方，引用或媒体不自动成为行动方。occurredAt 只用正文明示的本次动作日期 YYYY-MM-DD，未知为 null。
evidence 逐字复制一条支撑本次核心动作的完整正文短句。conditions 最多四条，每项只有 {quote}，各逐字复制一条连续原文，保留会改变结论的对象、地域、规模、使用限制或例外。不要翻译、拼接或从标题抽取引文。综合稿、材料不足或没有可证实发生时 fact 为 null。
只输出 JSON {scope,category,tags,entities,fact}。"""
PROCUREMENT_STRUCTURE = """
这份材料是政府采购公告。分类看本次采购的实质对象。需求、招采、成交、更正和终止属于项目进展，引用采购法规不构成法制新闻，也不能表述成实战应用。明确的产品或系统可归 product。只有采购对象明确涉及无人机等低空作业时才归 low-altitude，明确涉及舆情或网络内容治理时才归 public-opinion。物理机器人属于 embodied，虚拟仿真不属于。其余相关采购归 other。"""
PROCUREMENT_CATEGORY_EVIDENCE = {
    "low-altitude": re.compile(r"低空|无人机|无人飞行器|无人驾驶航空器|飞行服务|无人机场|反无人机"),
    "public-opinion": re.compile(r"舆情|网络内容治理|有害信息治理|网络谣言|内容审核"),
    "embodied": re.compile(r"机器人|具身智能|机器狗|四足巡检"),
}
TRANSLATE = SAFETY + """
把输入 blocks 按原顺序逐项译为自然简体中文，输出相同数量的字符串。保留原文段落、行分隔和每个 ⟦数字⟧，每个占位符在相应位置恰好出现一次。网址、代码、命令和文件名保持原样；专名可保留原文，数字、单位、日期及价格沿用原文。已有中文及纯数字或符号原样返回。不增删信息，不加解释、译注、导读或点评。
只输出 JSON {blocks: string[]}。"""
STAGES = ("prefilter", "score", "structure", "understand", "summarize", "group", "groupReview", "digest", "translate")


def preset_paths() -> dict[str, Path]:
    data = json.loads(os.environ.get("BLUEPULSE_MODEL_PRESETS", "{}"))
    if not isinstance(data, dict) or any(
        not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", key) or key == "default" or
        not isinstance(path, str) or not Path(path).is_absolute() for key, path in data.items()
    ):
        raise ValueError("invalid_model_presets")
    return {"default": DEFAULT_MODEL_ENV, **{key: Path(path) for key, path in data.items()}}


def available_presets() -> list[str]:
    return list(preset_paths())


def input_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


PREFILTER_VERSION = input_hash(PREFILTER)


@dataclass(frozen=True)
class Analysis:
    label: str
    scope: str = "unknown"
    fact: dict | None = None
    topics: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    entities: tuple[dict, ...] = ()
    title: str | None = None
    summary: str | None = None
    reason: str | None = None
    score: int | None = None
    scores: tuple[int, ...] = ()
    candidate: bool = False
    input_chars: int = 0
    input_truncated: bool = False
    content_type: str | None = None
    prefilter: dict | None = None


def _text(value, length):
    return value.strip()[:length] if isinstance(value, str) and value.strip() else None


def _ground(value, original, limit):
    quote = _text(value, limit)
    return quote if quote and " ".join(quote.split()) in original else None


def run_prefilter(step, data):
    response, _ = step("prefilter", "prefilter", PREFILTER, data, 600)
    label = response.get("label")
    relevance = response.get("relevance")
    reason = response.get("reason")
    evidence = response.get("evidence")
    if (label not in ("PASS", "BLOCK", "UNKNOWN") or
            any(value is not None and not isinstance(value, str) for value in (relevance, reason, evidence))):
        raise ValueError("invalid_prefilter")
    reason = _text(reason, 500)
    evidence = " ".join((evidence or "").split())
    if not 4 <= len(evidence) <= 500 or not any(
        evidence in " ".join((data[field] or "").split()) for field in ("title", "text")
    ):
        evidence = None
    if label == "PASS" and not (relevance in ("direct", "potential") and reason and evidence):
        label = "UNKNOWN"
    if label == "BLOCK" and (data["bodyStatus"] != "full_text" or not data["text"].strip()):
        label = "UNKNOWN"
    if label != "PASS":
        relevance = "irrelevant" if label == "BLOCK" else "uncertain"
    return {"label": label, "relevance": relevance, "reason": reason,
            "evidence": evidence, "version": PREFILTER_VERSION}


def procurement_category(category, title, fact):
    evidence = PROCUREMENT_CATEGORY_EVIDENCE.get(category)
    primary = " ".join((title, (fact or {}).get("evidence") or ""))
    if category in {"practice", "paper", "law"} or (evidence and not evidence.search(primary)):
        return "other"
    return category


def _structure(step, data, *, procurement=False):
    prompt = STRUCTURE + PROCUREMENT_STRUCTURE if procurement else STRUCTURE
    output, _ = step("structure", "structure", prompt, data, 1800)
    original = " ".join(data["text"].split())
    scope = output.get("scope")
    if scope not in {"single", "composite", "unknown"}:
        raise ValueError("invalid_structure_scope")
    category = output.get("category")
    if not isinstance(category, str) or category not in PUBLIC_TOPIC_SLUGS:
        raise ValueError("invalid_structure_category")
    raw_tags = output.get("tags")
    tags = tuple(dict.fromkeys(quote for value in (raw_tags[:6] if isinstance(raw_tags, list) else [])
                               if isinstance(value, str) and 2 <= len(value.strip()) <= 80
                               and (quote := _ground(value, original, 80))))
    entities = []
    for entity in (output.get("entities") or [])[:6]:
        if not isinstance(entity, dict):
            continue
        name = _text(entity.get("name"), 100)
        evidence = _ground(entity.get("evidence"), original, 400)
        kind = entity.get("type")
        if name and evidence and name in evidence and kind in {"vendor", "model", "organization"}:
            entities.append({"name": name, "type": kind, "evidence": evidence, "slug": entity_slug(name, kind)})
    fact = output.get("fact")
    if scope == "single" and isinstance(fact, dict) and (quote := _ground(fact.get("evidence"), original, 600)):
        conditions = [{"quote": item} for condition in (fact.get("conditions") or [])[:4]
                      if isinstance(condition, dict) and (item := _ground(condition.get("quote"), original, 400))]
        occurred = _text(fact.get("occurredAt"), 32)
        try:
            occurred = date.fromisoformat(occurred).isoformat() if occurred and occurred in original else None
        except ValueError:
            occurred = None
        fact = {key: _text(fact.get(key), length) for key, length in
                (("title", 80), ("subject", 80), ("action", 80), ("object", 160))}
        fact.update(evidence=quote, conditions=conditions, occurredAt=occurred)
    else:
        fact = None
        if scope == "single" or not original:
            scope = "unknown"
    if procurement:
        category = procurement_category(category, data["title"], fact)
    return scope, fact, (category,), tags, tuple(entities)


def _score(step, data, ordinal):
    output, meta = step("score", f"score:{ordinal}", SCORE_PROMPT, data, 512)
    score = SelectionScore(content_type=output.get("content_type"),
                           **{axis: output.get(axis) for axis in AXES})
    return score.attention_score, meta.get("request_id"), score.content_type


def rewrite_input(material):
    text = (material.source_body or material.source_summary or "")[:12_000]
    fact = ((material.editorial_data or {}).get("fact")
            if material.editorial_revision == material.revision else None)
    return {"title": material.source_title, "text": text, "fact": fact, "bodyStatus": material.body_status}


def rewrite_summary(inputs, step, *, with_reason: bool, repair: bool = False):
    capability = "understand" if with_reason else "summarize"
    prompt = REWRITE_SELECTED if with_reason else REWRITE_SUMMARY
    if repair:
        prompt += ("\n前一次未通过校验。现在仅写一句自然的中文，保留核心动作和必要适用范围。"
                   "省略日期、金额、数量、型号中的非必要数字，不能换算单位或补写原文没有的细节。"
                   "有明确计划或试点时保留这个阶段。")
    output, _ = step(capability, "rewrite_summary", prompt, inputs, 900)
    summary = summary_copy(output.get("summaryZh"), inputs["title"], inputs["text"])
    reason = (grounded_reading_value(output.get("editorialJudgment"), inputs["title"], inputs["text"], summary=summary)
              if with_reason else None)
    return summary, reason


def save_summary_copy(material, summary, reason):
    data = material.editorial_data or {}
    material.zh_summary = summary
    material.editorial_data = {**data, "copy_version": COPY_VERSION, "reason": reason,
                               "model_fields": {**(data.get("model_fields") or {}), "zh_summary": summary}}


def analyze(material, step) -> Analysis:
    original = material.source_body or material.source_summary or ""
    text = original[:12_000]
    data = {"title": material.source_title, "text": text, "bodyStatus": material.body_status}
    prefilter = run_prefilter(step, data)
    label = prefilter["label"]
    if label != "PASS":
        return Analysis(label, input_chars=len(text), input_truncated=len(text) < len(original),
                        prefilter=prefilter)
    score_input = {"title": material.source_title, "text": text}
    with ThreadPoolExecutor(max_workers=1) as pool:
        structure = pool.submit(_structure, step, data, procurement=material.source.slug == "ccgp-policing-tech")
        scores = [_score(step, score_input, ordinal) for ordinal in (1, 2)] if text.strip() else []
        scope, fact, topics, tags, entities = structure.result()
    if len(scores) == 2 and scores[0][1] and scores[0][1] == scores[1][1]:
        raise ValueError("duplicate_score_response")
    values = tuple(value for value, _, _ in scores)
    score = sum(values) // 2 if len(values) == 2 else None
    threshold = material.source.selection_threshold
    candidate = score is not None and threshold is not None and sum(values) >= 2 * threshold
    title = summary = reason = None
    if text.strip():
        near = candidate or score is not None and sum(values) > 100
        kind = "understand" if near else "summarize"
        writing, _ = step(kind, kind, UNDERSTAND if near else SUMMARIZE,
                          {**data, "fact": fact}, 1900 if near else 900)
        title = title_copy(writing.get("titleZh"), material.source_title, text)
        summary = summary_copy(writing.get("summaryZh"), material.source_title, text)
        reason = (grounded_reading_value(writing.get("editorialJudgment"), material.source_title, text, summary=summary)
                  if near else None)
    return Analysis(label, scope, fact, topics, tags, entities, title, summary, reason,
                    score, values, candidate, len(text), len(text) < len(original),
                    scores[0][2] if scores else None, prefilter)


def apply_analysis(session, material, analysis: Analysis, now, override: dict):
    base_relevant = analysis.label == "PASS" and bool(
        analysis.prefilter and analysis.topics and analysis.summary and evidence_allowed(material))
    title, summary, topics = analysis.title, analysis.summary, list(analysis.topics)
    if analysis.label != "PASS" and override.get("relevant") is True and material.editorial_revision == material.revision:
        previous = (material.editorial_data or {}).get("model_fields", {})
        title, summary, topics = previous.get("zh_title"), previous.get("zh_summary"), previous.get("topics", [])
    material.editorial_revision, material.editorial_scope = material.revision, analysis.scope
    material.editorial_data = {
        "reason": analysis.reason, "tags": list(analysis.tags), "entities": list(analysis.entities),
        "fact": analysis.fact, "label": analysis.label, "prefilter": analysis.prefilter, "scores": list(analysis.scores),
        "content_type": analysis.content_type, "input_chars": analysis.input_chars,
        "copy_version": COPY_VERSION,
        "input_truncated": analysis.input_truncated,
        "model_fields": {"zh_title": title, "zh_summary": summary, "topics": topics, "relevant": base_relevant},
    }
    material.zh_title = override.get("zh_title", title)
    material.zh_summary = override.get("zh_summary", summary)
    material.topics = override.get("topics", topics)
    material.relevant = override.get("relevant", base_relevant)
    material.importance_score = analysis.score or 0
    material.featured_candidate = bool(material.relevant and len(analysis.scores) == 2 and
                                       (analysis.candidate or override.get("selected") is True) and
                                       override.get("selected") is not False)
    material.selection_status = ("blocked" if analysis.label == "BLOCK" else
                                 "relevance_uncertain" if analysis.label == "UNKNOWN" else
                                 "uncalibrated" if material.source.selection_threshold is None else
                                 "qualified" if analysis.candidate else "below_threshold")
    material.judged_at = now
    material.grouping_status = "pending"
    material.grouping_value = None
    material.selected_at = None
    project_visibility(material, now)
    session.execute(delete(MaterialTopic).where(MaterialTopic.material_id == material.id))
    session.add_all(MaterialTopic(material_id=material.id, topic_slug=topic) for topic in material.topics)


SHIELD = re.compile(r"`{1,3}[\s\S]+?`{1,3}|https?://[^\s<>]+|⟦[0-9]+⟧|\r?\n")
TOKEN = re.compile(r"⟦([0-9]+)⟧")
MAX_TRANSLATION_CHARS = 60_000


def translate(original: str, step) -> tuple[str, bool]:
    text = original[:MAX_TRANSLATION_CHARS]
    blocks = re.split(r"(\n[ \t]*\n+)", text)
    for position, block in enumerate(blocks):
        if position % 2 or not block.strip():
            continue
        tokens = []

        def shield(match):
            tokens.append(match[0])
            return f"⟦{len(tokens) - 1}⟧"

        safe = SHIELD.sub(shield, block)
        chunks = re.findall(r"(?:[^⟦]|⟦[0-9]+⟧){1,1600}", safe)
        if "".join(chunks) != safe:
            raise ValueError("translation_block_split")
        translated = []
        for index, chunk in enumerate(chunks):
            result, _ = step("translate", f"translate:{position}:{index}", TRANSLATE, {"blocks": [chunk]}, 2400)
            output = result.get("blocks")
            if not isinstance(output, list) or len(output) != 1 or not _text(output[0], 16_000):
                raise ValueError("invalid_translation")
            if sorted(TOKEN.findall(chunk)) != sorted(TOKEN.findall(output[0])):
                raise ValueError("translation_tokens")
            translated.append(TOKEN.sub(lambda match: tokens[int(match[1])], output[0]))
        blocks[position] = "".join(translated)
    return "".join(blocks), len(text) == len(original)
