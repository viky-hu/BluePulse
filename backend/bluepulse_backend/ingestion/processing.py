from __future__ import annotations

from dataclasses import replace
from typing import Callable

from bluepulse_backend.ingestion.adapters import FetchedArticle
from bluepulse_backend.ingestion.llm import (
    MAX_TRANSLATION_CHARS,
    ModelAnalysisError,
    ModelConfig,
    analyze_source_article,
    translate_source_body,
)
from bluepulse_backend.ingestion.model_adapter import ModelAdapter, model_adapter_from_config
from bluepulse_backend.models import Source

TECH_SIGNALS = (
    "artificial intelligence", "machine learning", " ai ", "algorithm", "automated",
    "facial recognition", "biometric", "body camera", "bodycam", "dashcam",
    "alpr", "license plate reader", "camera", "video", "surveillance",
    "drone", "robot", "software", "platform", "database", "data breach",
    "data leak", "hack", "cyber", "digital", "network", "sensor", "technology",
    "人工智能", "大模型", "算法", "人脸识别", "生物识别", "执法记录仪",
    "车牌识别", "摄像", "视频", "监控", "无人机", "机器人", "软件", "平台",
    "数据库", "网络", "信息化", "技术",
)


def has_explicit_technology(item: FetchedArticle) -> bool:
    text = f" {item.title} {item.body or ''} ".casefold()
    return any(signal in text for signal in TECH_SIGNALS)


def process_source_article(
    item: FetchedArticle,
    source: Source,
    model_config: ModelConfig | None,
    on_error: Callable[[ModelAnalysisError], None] | None = None,
    on_translation_error: Callable[[ModelAnalysisError], None] | None = None,
    adapter: ModelAdapter | None = None,
) -> FetchedArticle:
    # A title and URL alone are not enough evidence for a publishable summary.
    # Keep the record for later enrichment instead of spending a model call on it.
    if item.parse_status == "metadata_only" or not (item.body or "").strip():
        return replace(item, processing_status="pending_model", featured_candidate=False)
    if model_config is None and adapter is None:
        return item
    active_adapter = adapter or model_adapter_from_config(
        model_config,
        source_analyzer=analyze_source_article,
        body_translator=translate_source_body,
    )
    try:
        analysis = active_adapter.analyze_source_article(
            item.url, item.title, item.body, source.source_type, item.parse_status,
        )
    except ModelAnalysisError as exc:
        if on_error is not None:
            on_error(exc)
        return replace(item, processing_status="model_failed")
    if not analysis.relevant or (
        source.adapter in {"rss", "gdelt", "govuk_api"} and not has_explicit_technology(item)
    ):
        return replace(
            item, processing_status="irrelevant", relevance=analysis.relevance,
            importance_score=0,
        )
    zh_body = item.zh_body
    translation_status = None
    if item.language.lower().startswith("en"):
        if zh_body:
            translation_status = "available"
        elif item.parse_status != "full_text" or not item.body:
            translation_status = "source_unavailable"
        elif len(item.body) > MAX_TRANSLATION_CHARS:
            translation_status = "too_long"
        else:
            translation_status = "pending"
    else:
        translation_status = "not_required"
    if (
        item.language.lower().startswith("en")
        and item.parse_status == "full_text"
        and item.body
        and len(item.body) <= MAX_TRANSLATION_CHARS
    ):
        try:
            zh_body = active_adapter.translate_body(item.body)
            translation_status = "available" if zh_body else "failed"
        except ModelAnalysisError as exc:
            translation_status = "failed"
            if on_translation_error is not None:
                on_translation_error(exc)
    return replace(
        item,
        zh_title=analysis.short_title,
        zh_summary=analysis.summary,
        zh_body=zh_body,
        translation_status=translation_status,
        topic_slugs=analysis.topics,
        importance_score=analysis.importance_score,
        relevance=analysis.relevance,
        featured_candidate=analysis.featured_candidate,
        featured_reason=analysis.featured_reason or None,
        processing_status="processed",
    )
