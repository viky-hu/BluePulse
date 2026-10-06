from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from bluepulse_backend.ingestion.adapters import FetchedArticle
from bluepulse_backend.ingestion.llm import ModelAnalysisError, ModelConfig, NoticeAnalysis
from bluepulse_backend.ingestion.model_adapter import model_adapter_from_config
from bluepulse_backend.ingestion.processing import process_source_article
from bluepulse_backend.models import Source


class ModelAdapterTests(unittest.TestCase):
    def test_compatible_adapter_forwards_analysis_and_translation(self) -> None:
        config = ModelConfig("https://example.test/v1", "secret", "test-model")
        result = NoticeAnalysis(True, 0.9, "警务技术", "报道警务技术。", ("policing",), 70)
        analyze = Mock(return_value=result)
        translate = Mock(return_value="中文正文")
        adapter = model_adapter_from_config(
            config, source_analyzer=analyze, body_translator=translate,
        )
        self.assertEqual(adapter.model_id, "test-model")
        self.assertIs(
            adapter.analyze_source_article(
                "https://example.org/item", "Police technology", "Body", "government", "full_text",
            ),
            result,
        )
        self.assertEqual(adapter.translate_body("English body"), "中文正文")
        analyze.assert_called_once_with(
            "https://example.org/item", "Police technology", "Body", "government", "full_text", config,
        )
        translate.assert_called_once_with("English body", config)

    def test_processor_accepts_offline_adapter_without_provider_config(self) -> None:
        class OfflineAdapter:
            model_id = "offline-test"

            def analyze_notice(self, _url: str, _title: str, _body: str) -> NoticeAnalysis:
                raise AssertionError("notice path was not requested")

            def analyze_source_article(
                self, _url: str, _title: str, _body: str | None,
                _source_type: str, _parse_status: str,
            ) -> NoticeAnalysis:
                return NoticeAnalysis(True, 0.85, "音频鉴伪研究", "研究音频鉴伪方法。", ("research",), 67)

            def translate_body(self, _body: str) -> str:
                return "中文正文"

        source = Source(slug="nij", name="NIJ", adapter="nij_html", source_type="government")
        item = FetchedArticle(
            url="https://example.org/study", title="Audio forensics study", body="English body",
            language="en", parse_status="full_text",
        )
        processed = process_source_article(item, source, None, adapter=OfflineAdapter())
        self.assertEqual(processed.processing_status, "processed")
        self.assertEqual(processed.zh_title, "音频鉴伪研究")
        self.assertEqual(processed.zh_body, "中文正文")

    def test_unknown_provider_is_rejected_before_request(self) -> None:
        with patch.dict("os.environ", {"BLUEPULSE_LLM_PROVIDER": "unsupported"}):
            with self.assertRaisesRegex(ModelAnalysisError, "不支持的模型提供方"):
                model_adapter_from_config(ModelConfig("https://example.test/v1", "secret", "model"))


if __name__ == "__main__":
    unittest.main()
