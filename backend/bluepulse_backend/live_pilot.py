"""Explicit, tightly bounded real-source and real-model pilot in an isolated DB."""
from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .cli import migrate, sync_taxonomy
from .db import make_engine
from .live_model import LiveAnalyzer, load_local_credentials, model_listed
from .live_sources import BoundedHTTP, GovUkAdapter, NistRssAdapter
from .models import AnalysisAttempt, Material, Source
from .operations import source_funnel
from .pipeline import ingest, process_pending


def run(env_path: Path, report_path: Path, *, max_source_items: int = 2,
        max_model_calls: int = 2, model_override: str | None = None) -> Path:
    if not 1 <= max_source_items <= 2 or not 0 <= max_model_calls <= 2:
        raise ValueError("pilot_limits_exceeded")
    base_url, api_key, model = load_local_credentials(env_path)
    if model_override is not None:
        model = model_override
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    db_path = data_dir / f"live-pilot-{stamp}-{uuid4().hex[:8]}.db"
    address = f"sqlite:///{db_path.as_posix()}"
    previous = os.environ.get("BLUEPULSE_DATABASE_URL")
    os.environ["BLUEPULSE_DATABASE_URL"] = address
    try:
        migrate()
        sync_taxonomy()
    finally:
        if previous is None:
            os.environ.pop("BLUEPULSE_DATABASE_URL", None)
        else:
            os.environ["BLUEPULSE_DATABASE_URL"] = previous
    engine = make_engine(address)
    source_runs: list[tuple[str, dict]] = []
    with httpx.Client(timeout=httpx.Timeout(35, connect=10), follow_redirects=False) as client:
        listed = model_listed(client, base_url, api_key, model)
        adapters = [
            ("govuk", "GOV.UK Home Office", "www.gov.uk", GovUkAdapter(
                BoundedHTTP(client, allowed_hosts={"www.gov.uk"}), max_items=max_source_items)),
            ("nist-public-safety", "NIST Public Safety", "www.nist.gov", NistRssAdapter(
                BoundedHTTP(client, allowed_hosts={"www.nist.gov"}), max_items=max_source_items)),
        ]
        with Session(engine) as session:
            for slug, name, host, adapter in adapters:
                source = Source(slug=slug, name=name, region="foreign", country_code="GB" if slug == "govuk" else "US",
                                language="en", source_type="official", topics=["policing", "public-safety-tech"],
                                allowed_hosts=[host], enabled=True, excerpt_allowed=False,
                                full_text_allowed=False)
                session.add(source)
                session.commit()
                run_record = ingest(session, source, adapter)
                source_runs.append((slug, source_funnel(session, run_record.id)))
            analyzer = LiveAnalyzer(client=client, base_url=base_url, api_key=api_key, model=model)
            remaining = max_model_calls if listed else 0
            processing: dict[str, dict[str, int]] = {}
            for slug, _, _, _ in adapters:
                if remaining <= 0:
                    break
                source = session.scalar(select(Source).where(Source.slug == slug))
                if source is None:
                    continue
                before = session.scalar(select(AnalysisAttempt.id).where(AnalysisAttempt.material_id.in_(
                    select(Material.id).where(Material.source_id == source.id)
                )).limit(1))
                counts = process_pending(session, analyzer, max_items=1, source_id=source.id)
                processing[slug] = counts
                if before is None and sum(counts.values()):
                    remaining -= 1
                stopped = session.scalar(select(AnalysisAttempt.error_code).where(
                    AnalysisAttempt.error_code.in_(["provider_http_401", "provider_http_402", "provider_http_403", "provider_http_429"])
                ).limit(1))
                if stopped:
                    break
            rows = session.scalars(select(Material).order_by(Material.source_id, Material.id)).all()
            attempts = session.scalars(select(AnalysisAttempt)).all()
            attempt_by_material = {attempt.material_id: attempt for attempt in attempts}
            report_lines = [
                "# 真实信源与模型小样本试验", "",
                f"- 时间（UTC）：{datetime.now(UTC).isoformat()}",
                "- 范围：GOV.UK Home Office Search/Content API 与 NIST Public Safety RSS；每源最多 2 条，模型最多 2 次调用。",
                "- 数据隔离：独立试验库，来源 `excerpt_allowed=false`，无公开文章进入正式 API。",
                f"- 模型预检：配置 ID {'在' if listed else '不在'}服务端 `/models` 列表；本次模型调用上限 {max_model_calls if listed else 0}。",
                f"- 试验数据库：`{db_path.name}`（位于 `repo/backend/data/`，未纳入 Git）", "",
                "## 逐源结果", "",
            ]
            for slug, funnel in source_runs:
                report_lines.append(f"- `{slug}`：运行 `{funnel['status']}`；候选 {funnel['candidate_count']}；发现 {funnel['discoveries']}；拒绝 {funnel['rejections']}。")
            report_lines.extend(["", "## 材料与模型结果", ""])
            for material in rows:
                attempt = attempt_by_material.get(material.id)
                meta = ((attempt.result or {}).get("provider_meta") or {}) if attempt else {}
                report_lines.extend([
                    f"### {material.source.name}：{material.source_title}", "",
                    f"- 原站：{material.source_url}",
                    f"- 原始发布时间：{material.published_at.isoformat() if material.published_at else '待核/不可信'}；时间类别：`{material.timeline_kind}`；材料级别：`{material.body_status}`。",
                    f"- 处理：`{material.state}`；模型尝试：`{attempt.status if attempt else '未调用'}`；错误：`{attempt.error_code if attempt else '无'}`。",
                    f"- 模型判断：相关 `{material.relevant}`；主题 `{', '.join(material.topics or [])}`；重要性 `{material.importance_score}`。",
                    f"- 中文摘要：{(material.zh_summary or '无')[:240]}",
                    f"- 用量：输入 {meta.get('prompt_tokens', '未知')} tokens；输出 {meta.get('completion_tokens', '未知')} tokens。",
                    "",
                ])
            report_lines.extend(["## 限制", "",
                                 "- 本试验只验证少量官方入口、材料版本与真实模型调用；不能推断持续可用率或筛选准确率。",
                                 "- NIST 仅使用 RSS 摘要；GOV.UK 附件页面的短导语不作为附件全文。无 Fact/Story、精选确认、热点和日报结论。",
                                 "- 模型输出是待复核的初筛结果，不是官方事实或正式发布。", ""])
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("\n".join(report_lines), encoding="utf-8")
    engine.dispose()
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded real-source/model pilot; writes isolated local DB")
    parser.add_argument("--execute", action="store_true", help="required to allow network and paid model calls")
    parser.add_argument("--env", type=Path, default=Path(__file__).resolve().parents[3] / ".env")
    parser.add_argument("--report", type=Path, default=Path(__file__).resolve().parents[3] / "真实采集试验.md")
    parser.add_argument("--model", help="explicit model override; must appear in /models")
    args = parser.parse_args()
    if not args.execute:
        parser.error("use --execute to explicitly enable the bounded pilot")
    path = run(args.env, args.report, model_override=args.model)
    print(f"pilot_report={path}")


if __name__ == "__main__":
    main()
