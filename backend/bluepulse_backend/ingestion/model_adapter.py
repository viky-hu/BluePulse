"""Provider-neutral model operations used by the ingestion pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Protocol

from bluepulse_backend.ingestion.llm import (
    ModelAnalysisError,
    ModelConfig,
    NoticeAnalysis,
    analyze_notice,
    analyze_source_article,
    translate_source_body,
)

NoticeAnalyzer = Callable[[str, str, str, ModelConfig], NoticeAnalysis]
SourceAnalyzer = Callable[[str, str, str | None, str, str, ModelConfig], NoticeAnalysis]
BodyTranslator = Callable[[str, ModelConfig], str]


class ModelAdapter(Protocol):
    """Analyze supplied evidence and translate text without database access."""

    @property
    def model_id(self) -> str: ...

    def analyze_notice(self, url: str, title: str, body: str) -> NoticeAnalysis: ...

    def analyze_source_article(
        self, url: str, title: str, body: str | None, source_type: str, parse_status: str,
    ) -> NoticeAnalysis: ...

    def translate_body(self, body: str) -> str: ...


@dataclass(frozen=True)
class OpenAICompatibleAdapter:
    config: ModelConfig
    notice_analyzer: NoticeAnalyzer = analyze_notice
    source_analyzer: SourceAnalyzer = analyze_source_article
    body_translator: BodyTranslator = translate_source_body

    @property
    def model_id(self) -> str:
        return self.config.model_id

    def analyze_notice(self, url: str, title: str, body: str) -> NoticeAnalysis:
        return self.notice_analyzer(url, title, body, self.config)

    def analyze_source_article(
        self, url: str, title: str, body: str | None, source_type: str, parse_status: str,
    ) -> NoticeAnalysis:
        return self.source_analyzer(url, title, body, source_type, parse_status, self.config)

    def translate_body(self, body: str) -> str:
        return self.body_translator(body, self.config)


def model_adapter_from_config(
    config: ModelConfig,
    *,
    notice_analyzer: NoticeAnalyzer = analyze_notice,
    source_analyzer: SourceAnalyzer = analyze_source_article,
    body_translator: BodyTranslator = translate_source_body,
) -> ModelAdapter:
    provider = os.environ.get("BLUEPULSE_LLM_PROVIDER", "openai_compatible").strip().lower()
    if provider != "openai_compatible":
        raise ModelAnalysisError(f"不支持的模型提供方：{provider or '(empty)'}。")
    return OpenAICompatibleAdapter(config, notice_analyzer, source_analyzer, body_translator)
