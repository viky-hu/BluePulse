"""Replay one archived day across all 15 sources into an isolated, nonpublic audit DB."""
from __future__ import annotations

import argparse
import csv
import html
import json
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .api import create_app
from .cli import TOPICS, sync_taxonomy
from .db import Base, make_engine
from .models import AnalysisAttempt, Material, MaterialTopic, Source
from .pipeline import (AnalysisResult, Candidate, MockAnalyzer, MockSourceAdapter,
                       PUBLIC_TOPIC_SLUGS, canonical_url, ingest, process_pending)
from .source_collection import SOURCES, collect
from .source_validation import _migrate


BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = BACKEND / "data/source-validation"
DEFAULT_CATEGORIES = BACKEND / "config/full-day-2026-11-01-categories.json"
DEFAULT_OUTPUT = BACKEND / "data/full-day-pilot/2026-11-01"
DECISIONS = ("ready_for_review", "hold", "reject")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
                    encoding="utf-8")


def _candidate(slug: str, item: dict) -> Candidate:
    return Candidate(url=item["url"], title=item["title"], body=item.get("body"),
                     summary=item.get("summary"),
                     published_at=datetime.fromisoformat(item["published_at"])
                     if item.get("published_at") else None,
                     published_date=date.fromisoformat(item["published_date"])
                     if item.get("published_date") else None,
                     language=SOURCES[slug].language)


def _sample(input_dir: Path, categories_file: Path) -> tuple[date, list[dict]]:
    seed = _read(input_dir / "observation-seed.json")
    categories = _read(categories_file)
    sample_day = date.fromisoformat(categories["sample_day"])
    if len(seed["sources"]) != len(SOURCES) or {row["source"] for row in seed["sources"]} != set(SOURCES):
        raise ValueError("sample_must_cover_all_15_sources")
    category_map = {}
    for row in categories["items"]:
        slug = row["source"]
        url = canonical_url(row["url"], [SOURCES[slug].host])
        key = slug, url
        if key in category_map or row["primary_topic"] not in PUBLIC_TOPIC_SLUGS:
            raise ValueError("category_manifest_invalid")
        category_map[key] = row
    review = _read(input_dir / "review-2026-11-01Tmanual+0800.json")
    reviews = {(row["source"], canonical_url(row["url"], [SOURCES[row["source"]].host])): row
               for row in review["items"]}
    selected = []
    global_urls = set()
    for source_record in seed["sources"]:
        slug = source_record["source"]
        baseline = _read(input_dir / source_record["baseline_file"])
        if baseline["run_at"][:10] != sample_day.isoformat():
            raise ValueError("sample_day_mismatch")
        source_rows = [row for row in baseline["sources"] if row["source"] == slug]
        if len(source_rows) != 1 or source_rows[0]["error_code"] is not None or len(source_rows[0]["items"]) != 2:
            raise ValueError(f"source_sample_not_two:{slug}")
        for item in source_rows[0]["items"]:
            url = canonical_url(item["url"], [SOURCES[slug].host])
            if url in global_urls:
                raise ValueError(f"cross_source_duplicate:{url}")
            global_urls.add(url)
            key = slug, url
            label = reviews.get(key)
            if label is None or label.get("topic_fit") not in {"direct", "adjacent", "off"} or type(label.get("evidence_sufficient")) is not bool or type(label.get("editorial_fit")) is not bool:
                raise ValueError(f"manual_review_missing:{url}")
            category = category_map.get(key)
            if (label["topic_fit"] == "direct") != (category is not None):
                raise ValueError(f"direct_category_mismatch:{url}")
            raw_date = item.get("published_date") or (item.get("published_at") or "")[:10]
            future = bool(raw_date and date.fromisoformat(raw_date) > sample_day)
            if label["topic_fit"] == "off":
                disposition, reason = "reject", "当前正文足以确认偏离警务科技主题。"
            elif label["topic_fit"] == "adjacent":
                disposition, reason = "hold", "与领域相邻，但当前正文缺明确警务科技应用。"
            elif not label["evidence_sufficient"]:
                disposition, reason = "hold", "主题直接相关，但关键事实证据未进入当前正文。"
            elif future:
                disposition, reason = "hold", "原始发布日期晚于本次样本日，不能计为当日新稿。"
            elif label["editorial_fit"]:
                disposition, reason = "ready_for_review", "主题与证据初筛通过，等待最终人工选稿及许可核对。"
            else:
                disposition, reason = "hold", "主题相关且证据可判断，但本次选稿价值或时效不足。"
            selected.append({"source": slug, "url": url, "item": item,
                             "baseline": source_record["baseline_file"],
                             "topic_fit": label["topic_fit"],
                             "evidence_sufficient": label["evidence_sufficient"],
                             "editorial_fit": label["editorial_fit"],
                             "primary_topic": category["primary_topic"] if category else None,
                             "category_reason": category["reason"] if category else None,
                             "future_on_sample_day": future,
                             "disposition": disposition, "reason": reason})
    if len(selected) != 30 or set(category_map) != {(row["source"], row["url"]) for row in selected
                                                if row["topic_fit"] == "direct"}:
        raise ValueError("sample_or_categories_incomplete")
    return sample_day, selected


def _synthetic_api_contract(output_dir: Path) -> dict:
    """Exercise the actual public endpoints using a separate example.test fixture."""
    database = output_dir / "synthetic-api.db"
    address = f"sqlite:///{database.as_posix()}"
    engine = make_engine(address)
    Base.metadata.create_all(engine)
    sync_taxonomy(address)
    try:
        with Session(engine) as session:
            source = Source(slug="synthetic-permitted", name="Synthetic Permitted Fixture",
                            region="foreign", country_code="ZZ", language="en",
                            allowed_hosts=["example.test"], topics=["practice"],
                            excerpt_allowed=True, full_text_allowed=False)
            session.add(source)
            session.commit()
            item = Candidate(url="https://example.test/police-technology-fixture",
                             title="Synthetic police technology fixture",
                             body="Synthetic evidence for API contract only. " * 12,
                             published_at=datetime.now(UTC) - timedelta(hours=1), language="en")
            run = ingest(session, source, MockSourceAdapter([item]))
            run_status = run.status
            analyzer = MockAnalyzer({item.url: AnalysisResult(
                relevant=True, title_zh="合成接口样本", summary_zh="仅用于验证公开接口的测试数据。",
                topics=("practice",), importance_score=60)})
            processed = process_pending(session, analyzer)
            material_id = session.scalar(select(Material.id).where(Material.source_id == source.id))
        app = create_app(address)
        with TestClient(app) as client:
            taxonomy = client.get("/api/v1/taxonomy")
            matched = client.get("/api/v1/articles", params={"period": "all", "topic": "practice"})
            unmatched = client.get("/api/v1/articles", params={"period": "all", "topic": "law"})
            detail = client.get(f"/api/v1/articles/{material_id}")
        app.state.engine.dispose()
        if (run_status != "completed" or processed["applied"] != 1 or taxonomy.status_code != 200
                or {row["slug"] for row in taxonomy.json()["items"]} != {row[0] for row in TOPICS}
                or matched.status_code != 200 or len(matched.json()["items"]) != 1
                or unmatched.status_code != 200 or unmatched.json()["items"]
                or detail.status_code != 200 or detail.json()["source_body"] is not None):
            raise ValueError("synthetic_api_contract_failed")
        return {"database": str(database), "taxonomy_slugs": [row[0] for row in TOPICS],
                "practice_items": 1, "law_items": 0, "detail_status": 200,
                "full_text_exposed": False, "synthetic_only": True}
    finally:
        engine.dispose()


def _review_html(rows: list[dict], sample_day: date) -> str:
    cards = []
    for row in rows:
        body = row["body"] or row["summary"] or ""
        values = {key: html.escape(str(row.get(key) or "")) for key in
                  ("source", "title", "url", "published_date", "primary_topic", "disposition",
                   "reason", "category_reason")}
        cards.append(
            f'<article><header><strong>{values["source"]}</strong> '
            f'<span>{values["disposition"]}</span> <span>{values["primary_topic"]}</span></header>'
            f'<h2>{values["title"]}</h2><p><a href="{values["url"]}" rel="noreferrer">原文</a> '
            f'· 原始日期 {values["published_date"]} · 正文 {row["body_chars"]} 字</p>'
            f'<p>{values["reason"]} {values["category_reason"]}</p>'
            f'<details><summary>提取正文（内部核对）</summary><pre>{html.escape(body)}</pre></details></article>')
    return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>15源单日内部审阅</title>"
            "<style>body{font:16px/1.7 'Microsoft YaHei',sans-serif;max-width:1000px;margin:auto;padding:2rem;"
            "background:#f6f7f4;color:#172221}article{background:white;border:1px solid #d7dfda;border-radius:10px;"
            "padding:1.2rem;margin:1rem 0}h2{font-size:1.2rem}span{margin-left:.6rem;color:#39554d}"
            "a{color:#245f65}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f2;padding:1rem}"
            "</style><h1>15源单日内部审阅</h1><p>采集样本日 " + sample_day.isoformat() +
            "；每入口两篇。仅本地证据检查，未公开、未调用模型。</p>" + "".join(cards) + "</html>")


def run(input_dir: Path, categories_file: Path, output_dir: Path) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output_directory_must_be_empty")
    sample_day, selected = _sample(input_dir, categories_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    database = output_dir / "full-day.db"
    address = f"sqlite:///{database.as_posix()}"
    _migrate(address)
    sync_taxonomy(address)
    engine = make_engine(address)
    source_runs = []
    try:
        with Session(engine) as session:
            for slug in SOURCES:
                candidates = [_candidate(slug, row["item"]) for row in selected if row["source"] == slug]
                first = collect(session, SOURCES[slug], MockSourceAdapter(candidates))
                replay = collect(session, SOURCES[slug], MockSourceAdapter(candidates))
                source_runs.append({"source": slug, "first": first["discoveries"],
                                    "replay": replay["discoveries"]})
            answers = {}
            for row in selected:
                eligible_evidence = row["topic_fit"] == "direct" and row["evidence_sufficient"]
                answers[row["url"]] = AnalysisResult(
                    relevant=eligible_evidence, title_zh=None,
                    summary_zh=("内部分类试验标签，非对外摘要：" + row["category_reason"])
                    if eligible_evidence else None,
                    topics=(row["primary_topic"],) if eligible_evidence else (),
                    importance_score=0, featured_candidate=False, body_zh=None,
                    provider_meta={"kind": "manual_fixture", "sample_day": sample_day.isoformat()},
                )
            processed = process_pending(session, MockAnalyzer(
                answers, input_version="manual-full-day-2026-11-01-v1"), max_items=30)
            for row in selected:
                material = session.scalar(select(Material).where(Material.canonical_url == row["url"]))
                if material is None or material.public or material.source.excerpt_allowed or material.source.full_text_allowed:
                    raise ValueError("real_material_publication_gate_failed")
                row.update(material_id=material.id, revision=material.revision,
                           content_hash=material.content_hash, state=material.state,
                           relevant=material.relevant, applied_topics=material.topics,
                           public=material.public, title=material.source_title,
                           published_date=material.published_date.isoformat() if material.published_date
                           else material.published_at.date().isoformat() if material.published_at else None,
                           body=material.source_body, summary=material.source_summary,
                           body_chars=len(material.source_body or ""))
            counts = {"materials": session.scalar(select(func.count()).select_from(Material)),
                      "analysis_attempts": session.scalar(select(func.count()).select_from(AnalysisAttempt)),
                      "material_topics": session.scalar(select(func.count()).select_from(MaterialTopic)),
                      "public": session.scalar(select(func.count()).select_from(Material).where(Material.public.is_(True)))}
    finally:
        engine.dispose()
    if (processed != {"applied": 30, "failed": 0, "unknown": 0}
            or counts["materials"] != 30 or counts["analysis_attempts"] != 30 or counts["public"] != 0):
        raise ValueError("full_day_pipeline_incomplete")
    app = create_app(address)
    with TestClient(app) as client:
        taxonomy = client.get("/api/v1/taxonomy")
        sources = client.get("/api/v1/sources")
        listing = client.get("/api/v1/articles", params={"period": "all"})
        category_listings = {slug: len(client.get("/api/v1/articles", params={
            "period": "all", "topic": slug}).json()["items"]) for slug, _, _ in TOPICS}
        detail = client.get(f"/api/v1/articles/{selected[0]['material_id']}")
    app.state.engine.dispose()
    if (taxonomy.status_code != 200 or {row["slug"] for row in taxonomy.json()["items"]}
            != {row[0] for row in TOPICS} or sources.status_code != 200
            or len(sources.json()["items"]) != 15 or listing.status_code != 200
            or listing.json()["items"] or any(category_listings.values()) or detail.status_code != 404):
        raise ValueError("nonpublic_api_gate_failed")
    synthetic = _synthetic_api_contract(output_dir)
    by_source = {}
    for slug in SOURCES:
        items = [row for row in selected if row["source"] == slug]
        by_source[slug] = {"sampled": len(items), "direct": sum(row["topic_fit"] == "direct" for row in items),
                           "classified": sum(bool(row["applied_topics"]) for row in items),
                           **{key: sum(row["disposition"] == key for row in items) for key in DECISIONS}}
    report = {"sample_day": sample_day.isoformat(), "database": str(database),
              "source_count": len(by_source), "item_count": len(selected),
              "source_runs": source_runs, "processing": processed, "database_counts": counts,
              "topic_fit": dict(Counter(row["topic_fit"] for row in selected)),
              "dispositions": dict(Counter(row["disposition"] for row in selected)),
              "category_counts": dict(Counter(row["primary_topic"] for row in selected if row["applied_topics"])),
              "by_source": by_source,
              "real_api": {"taxonomy_slugs": [row["slug"] for row in taxonomy.json()["items"]],
                           "sources": 15, "articles": 0, "category_articles": category_listings,
                           "hidden_detail_status": detail.status_code},
              "synthetic_api": synthetic, "model_calls": 0, "production_writes": 0,
              "items": [{key: value for key, value in row.items() if key not in {"item", "body", "summary"}}
                        for row in selected]}
    _write(output_dir / "result.json", report)
    with (output_dir / "items.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["source", "title", "url", "published_date", "topic_fit", "evidence_sufficient",
                  "editorial_fit", "primary_topic", "applied_topics", "disposition", "reason", "state", "public"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in selected:
            writer.writerow({key: row.get(key) for key in fields})
    (output_dir / "review.html").write_text(_review_html(selected, sample_day), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--categories", type=Path, default=DEFAULT_CATEGORIES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run(args.input_dir, args.categories, args.output_dir)
    print(json.dumps({"sample_day": result["sample_day"], "sources": result["source_count"],
                      "items": result["item_count"], "processed": result["processing"],
                      "dispositions": result["dispositions"], "real_public": result["database_counts"]["public"],
                      "output_dir": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
