"""Resume only uncalled materials in an existing isolated pilot DB."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import make_engine
from .live_model import LiveAnalyzer, load_local_credentials, model_listed
from .models import AnalysisAttempt, Material, Source
from .pipeline import process_pending


def resume(env_path: Path, db_path: Path, report_path: Path, model: str | None = None) -> Path:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    resolved = db_path.resolve()
    if not resolved.is_relative_to(data_dir.resolve()) or not resolved.name.startswith("live-pilot-") or resolved.suffix != ".db":
        raise ValueError("not_an_isolated_pilot_database")
    if not resolved.exists():
        raise ValueError("pilot_database_missing")
    base_url, api_key, configured_model = load_local_credentials(env_path)
    model = model or configured_model
    with httpx.Client(timeout=httpx.Timeout(45, connect=10), follow_redirects=False) as client:
        if not model_listed(client, base_url, api_key, model):
            raise ValueError("selected_model_not_listed")
        analyzer = LiveAnalyzer(client, base_url, api_key, model)
        engine = make_engine(f"sqlite:///{resolved.as_posix()}")
        details = []
        with Session(engine) as session:
            for slug in ("govuk", "nist-public-safety"):
                source = session.scalar(select(Source).where(Source.slug == slug))
                if source is None:
                    continue
                counts = process_pending(session, analyzer, source_id=source.id, max_items=1)
                details.append((slug, counts))
                stopped = session.scalar(select(AnalysisAttempt.error_code).where(
                    AnalysisAttempt.input_version == analyzer.input_version,
                    AnalysisAttempt.error_code.in_(["provider_http_401", "provider_http_402", "provider_http_403", "provider_http_429"])
                ).limit(1))
                if stopped:
                    break
            rows = session.scalars(select(Material).where(Material.state != "analysis_pending").order_by(Material.source_id, Material.id)).all()
            new_attempts = session.scalars(select(AnalysisAttempt).where(
                AnalysisAttempt.input_version == analyzer.input_version
            )).all()
            by_material = {item.material_id: item for item in new_attempts}
            lines = ["", f"## 续测：{datetime.now(UTC).isoformat()}", "",
                     f"- 使用 `/models` 已列出的 `{model}`；仅处理上轮未调用的材料，每源最多一次。先前 `receipt_unknown` 保持原状。",
                     f"- 处理计数：{details}。", ""]
            for material in rows:
                attempt = by_material.get(material.id)
                if attempt is None:
                    continue
                meta = ((attempt.result or {}).get("provider_meta") or {})
                lines.extend([f"- {material.source.name}｜{material.source_title}：`{attempt.status}` / `{attempt.error_code or '无错误'}`；相关 `{material.relevant}`；主题 `{', '.join(material.topics or [])}`；摘要 `{(material.zh_summary or '无')[:180]}`；输入/输出 tokens `{meta.get('prompt_tokens', '未知')}/{meta.get('completion_tokens', '未知')}`。"])
            lines.append("")
        engine.dispose()
    with report_path.open("a", encoding="utf-8") as report:
        report.write("\n".join(lines))
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume uncalled materials in a bounded pilot")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--model", help="optional explicit override; defaults to .env llm_id")
    parser.add_argument("--env", type=Path, default=Path(__file__).resolve().parents[3] / ".env")
    parser.add_argument("--report", type=Path, default=Path(__file__).resolve().parents[3] / "真实采集试验.md")
    args = parser.parse_args()
    if not args.execute:
        parser.error("use --execute to explicitly enable paid model calls")
    print(f"pilot_report={resume(args.env, args.db, args.report, args.model)}")


if __name__ == "__main__":
    main()
