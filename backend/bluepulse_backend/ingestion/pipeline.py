from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bluepulse_backend.db import create_database_engine
from bluepulse_backend.ingestion.adapters import FetchedArticle, fetch_source
from bluepulse_backend.models import (
    Article,
    ArticleTopic,
    FeaturedEdition,
    FeaturedSlot,
    IngestionRun,
    Source,
    SourceRun,
    Topic,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
TOPIC_TERMS: dict[str, tuple[str, ...]] = {
    "policing": ("police", "policing", "law enforcement", "警务", "公安"),
    "artificial-intelligence": (
        "artificial intelligence", " ai ", "llm", "large language model", "大模型", "人工智能"
    ),
    "public-safety-tech": (
        "body camera", "bodycam", "drone", "robot", "surveillance", "公共安全", "无人机"
    ),
    "cybersecurity": ("cybersecurity", "cyber security", "data security", "网络安全"),
    "policy-standards": ("regulation", "policy", "standard", "法规", "政策", "标准"),
    "procurement-projects": ("procurement", "tender", "contract", "招标", "采购", "中标"),
    "research": ("research", "study", "journal", "研究", "论文"),
}


def _load_json_config(name: str) -> list[dict[str, object]]:
    path = BACKEND_ROOT / "config" / name
    return json.loads(path.read_text(encoding="utf-8"))


def sync_reference_data() -> dict[str, int]:
    source_rows = _load_json_config("sources.json")
    topic_rows = _load_json_config("taxonomy.json")
    engine = create_database_engine()
    try:
        with Session(engine) as session, session.begin():
            for item in source_rows:
                source = session.scalar(select(Source).where(Source.slug == item["slug"]))
                values = {
                    key: item[key]
                    for key in (
                        "name", "base_url", "adapter", "region", "country_code", "language",
                        "source_type", "topics", "config", "trust_level", "enabled",
                    )
                }
                if source is None:
                    session.add(Source(slug=item["slug"], **values))
                else:
                    for key, value in values.items():
                        setattr(source, key, value)
            for item in topic_rows:
                topic = session.scalar(select(Topic).where(Topic.slug == item["slug"]))
                if topic is None:
                    session.add(Topic(**item))
                else:
                    topic.name_zh = item["name_zh"]
                    topic.name_en = item["name_en"]
                    topic.enabled = True
        return {"sources": len(source_rows), "topics": len(topic_rows)}
    finally:
        engine.dispose()


def canonicalize_url(value: str) -> str:
    parsed = urlsplit(value)
    kept_query = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"fbclid", "gclid", "mc_cid", "mc_eid"}
    ]
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), urlencode(kept_query), "")
    )


def _fingerprint(item: FetchedArticle) -> str:
    text = " ".join(f"{item.title} {item.body or ''}".casefold().split())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _topic_slugs(item: FetchedArticle, source: Source) -> list[str]:
    if source.source_type == "academic":
        return ["research"]
    text = f" {item.title} {item.body or ''} ".casefold()
    matches = [
        slug for slug, terms in TOPIC_TERMS.items()
        if any(term.casefold() in text for term in terms)
    ]
    return matches[:4]


def _region(country_code: str | None, source: Source) -> str | None:
    if country_code:
        return "domestic" if country_code.upper() == "CN" else "foreign"
    return source.region


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _article_from_item(item: FetchedArticle, source: Source) -> Article:
    country_code = item.country_code or source.country_code
    chinese_title = item.title if item.language.lower().startswith("zh") else None
    return Article(
        source_id=source.id,
        source_url=item.url,
        canonical_url=canonicalize_url(item.url),
        source_title=item.title[:20_000],
        zh_title=chinese_title,
        source_body=item.body,
        language=item.language[:12],
        region=_region(country_code, source),
        country_code=country_code,
        author=(item.author[:500] if item.author else None),
        published_at=item.published_at,
        content_fingerprint=_fingerprint(item),
        importance_score=0,
        processing_status="pending_model",
        parse_status=item.parse_status,
        quality_status=(
            "body_unavailable" if not item.body else
            "region_unclassified" if not _region(country_code, source) else
            "unreviewed"
        ),
    )


def refresh_featured(session: Session, generated_at: datetime | None = None) -> FeaturedEdition:
    now = generated_at or datetime.now(UTC)
    effective_date = func.coalesce(Article.published_at, Article.first_seen_at)
    rows = list(
        session.scalars(
            select(Article)
            .where(
                Article.deleted_at.is_(None),
                effective_date >= now - timedelta(days=7),
            )
            .order_by(Article.importance_score.desc(), effective_date.desc(), Article.id.asc())
        )
    )
    recent = [
        article for article in rows
        if _as_utc(article.published_at or article.first_seen_at) >= now - timedelta(hours=24)
    ]
    selected = recent[:6]
    if len(selected) < 6:
        seen = {article.id for article in selected}
        selected.extend(article for article in rows if article.id not in seen)
        selected = selected[:6]

    edition = FeaturedEdition(generated_at=now, window_policy="24h_then_7d")
    session.add(edition)
    session.flush()
    for index, article in enumerate(selected):
        session.add(
            FeaturedSlot(
                edition_id=edition.id,
                article_id=article.id,
                slot=f"p{index}",
                importance_score=article.importance_score,
            )
        )
    return edition


def run_ingestion(trigger_type: str = "manual") -> dict[str, object]:
    engine = create_database_engine()
    try:
        with Session(engine, expire_on_commit=False) as session:
            run = IngestionRun(trigger_type=trigger_type, status="running", counts={})
            session.add(run)
            session.commit()
            run_id = run.id
            sources = list(
                session.scalars(select(Source).where(Source.enabled.is_(True)).order_by(Source.slug))
            )

        totals = {"sources": len(sources), "source_failures": 0, "discovered": 0, "inserted": 0, "duplicates": 0}
        for source in sources:
            source_run = SourceRun(run_id=run_id, source_id=source.id, status="running")
            with Session(engine) as session, session.begin():
                session.add(source_run)
                session.flush()
                source_run_id = source_run.id
            started = datetime.now(UTC)
            try:
                fetched = fetch_source(source)
                inserted = 0
                duplicates = 0
                with Session(engine, expire_on_commit=False) as session, session.begin():
                    topic_map = {
                        topic.slug: topic
                        for topic in session.scalars(select(Topic).where(Topic.enabled.is_(True)))
                    }
                    for item in fetched:
                        article = _article_from_item(item, source)
                        existing = session.scalar(
                            select(Article.id).where(Article.canonical_url == article.canonical_url)
                        )
                        if existing is not None:
                            duplicates += 1
                            continue
                        similar = session.scalar(
                            select(Article.id).where(
                                Article.content_fingerprint == article.content_fingerprint
                            ).limit(1)
                        )
                        if similar is not None:
                            article.quality_status = "duplicate_candidate"
                        try:
                            with session.begin_nested():
                                session.add(article)
                                session.flush()
                        except IntegrityError:
                            duplicates += 1
                            continue
                        matches = [topic_map[slug] for slug in _topic_slugs(item, source) if slug in topic_map]
                        for index, topic in enumerate(matches):
                            session.add(
                                ArticleTopic(
                                    article_id=article.id,
                                    topic_id=topic.id,
                                    is_primary=index == 0,
                                )
                            )
                        inserted += 1
                    source_row = session.get(Source, source.id)
                    if source_row:
                        source_row.last_success_at = datetime.now(UTC)
                    run_row = session.get(SourceRun, source_run_id)
                    if run_row:
                        run_row.status = "succeeded"
                        run_row.discovered_count = len(fetched)
                        run_row.inserted_count = inserted
                        run_row.duplicate_count = duplicates
                        run_row.finished_at = datetime.now(UTC)
                totals["discovered"] += len(fetched)
                totals["inserted"] += inserted
                totals["duplicates"] += duplicates
            except Exception as exc:  # A failed source must not stop the other configured sources.
                totals["source_failures"] += 1
                with Session(engine) as session, session.begin():
                    failed_run = session.get(SourceRun, source_run_id)
                    if failed_run:
                        failed_run.status = "failed"
                        failed_run.error_class = type(exc).__name__
                        failed_run.error_message = str(exc)[:1000]
                        failed_run.finished_at = datetime.now(UTC)

        final_status = "failed" if totals["source_failures"] == len(sources) and sources else (
            "partial" if totals["source_failures"] else "succeeded"
        )
        with Session(engine) as session, session.begin():
            run_row = session.get(IngestionRun, run_id)
            if run_row:
                run_row.status = final_status
                run_row.counts = totals
                run_row.finished_at = datetime.now(UTC)
            if final_status in {"succeeded", "partial"}:
                refresh_featured(session)
        return {"run_id": str(run_id), "status": final_status, **totals}
    finally:
        engine.dispose()
