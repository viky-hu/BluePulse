from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bluepulse_backend.db import create_database_engine
from bluepulse_backend.editorial import featured_article_condition, public_article_conditions
from bluepulse_backend.ingestion.adapters import FetchedArticle, fetch_source
from bluepulse_backend.ingestion.entities import link_article_entities
from bluepulse_backend.ingestion.lease import (
    LeaseGuard, LeaseLost, acquire_ingestion, interrupt_owned_run,
)
from bluepulse_backend.ingestion.llm import (
    MAX_TRANSLATION_CHARS, ModelAnalysisError, load_model_config, translate_source_body,
)
from bluepulse_backend.ingestion.model_adapter import model_adapter_from_config
from bluepulse_backend.ingestion.processing import has_explicit_technology, process_source_article
from bluepulse_backend.models import (
    Article,
    ArticleMedia,
    ArticleTopic,
    Entity,
    FeaturedEdition,
    FeaturedSlot,
    IngestionRun,
    Source,
    SourceRun,
    Topic,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
RATE_LIMIT_COOLDOWN = timedelta(minutes=15)
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
    entity_rows = _load_json_config("entities.json")
    if len({row["slug"] for row in entity_rows}) != len(entity_rows):
        raise ValueError("实体配置包含重复 slug。")
    for row in entity_rows:
        if row["entity_type"] not in {"vendor", "model", "organization"} or not row["aliases"]:
            raise ValueError(f"实体配置无效：{row['slug']}")
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
            for item in entity_rows:
                entity = session.scalar(select(Entity).where(Entity.slug == item["slug"]))
                values = {key: item[key] for key in ("entity_type", "name", "aliases", "region")}
                if entity is None:
                    session.add(Entity(slug=item["slug"], enabled=True, **values))
                else:
                    for key, value in values.items():
                        setattr(entity, key, value)
                    entity.enabled = True
        return {"sources": len(source_rows), "topics": len(topic_rows), "entities": len(entity_rows)}
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
    if item.topic_slugs:
        return list(dict.fromkeys(item.topic_slugs))[:4]
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
    chinese_title = item.zh_title or (item.title if item.language.lower().startswith("zh") else None)
    return Article(
        source_id=source.id,
        source_url=item.url,
        canonical_url=canonicalize_url(item.url),
        source_title=item.title[:20_000],
        zh_title=chinese_title,
        source_body=item.body,
        zh_summary=item.zh_summary,
        zh_body=item.zh_body,
        language=item.language[:12],
        region=_region(country_code, source),
        country_code=country_code,
        author=(item.author[:500] if item.author else None),
        published_at=_as_utc(item.published_at) if item.published_at else None,
        content_fingerprint=_fingerprint(item),
        importance_score=item.importance_score,
        relevance=item.relevance,
        featured_candidate=item.featured_candidate,
        featured_reason=item.featured_reason,
        processing_status=item.processing_status,
        parse_status=item.parse_status,
        translation_status=item.translation_status,
        quality_status=(
            "irrelevant" if item.processing_status == "irrelevant" else
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
                *public_article_conditions(),
                featured_article_condition(),
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


def reprocess_pending(
    source_slug: str | None = None, limit: int = 10, editorial_only: bool = False,
) -> dict[str, object]:
    if not 1 <= limit <= 30:
        raise ValueError("limit must be between 1 and 30")
    model_config = load_model_config()
    if model_config is None:
        raise RuntimeError("模型服务未配置，不能重处理历史文章。")
    engine = create_database_engine()
    counts: dict[str, object] = {
        "examined": 0, "processed": 0, "irrelevant": 0,
        "model_failures": 0, "translation_failures": 0,
        "last_error": None, "rejected_existing": 0, "manual_conflicts": 0,
    }
    try:
        with Session(engine) as session:
            query = (
                select(Article)
                .join(Source)
                .where(
                    Article.deleted_at.is_(None),
                    Article.processing_status.in_(("pending_model", "model_failed")),
                    Article.parse_status != "metadata_only",
                    Article.source_body.is_not(None),
                    or_(Article.editorial_relevance.is_(None),
                        Article.editorial_relevance.notin_(("irrelevant", "uncertain"))),
                    Source.enabled.is_(True),
                    Source.adapter != "ccgp_html",
                )
                .order_by(
                    Article.first_seen_at.desc(), Article.published_at.desc(), Article.id.asc(),
                )
                .limit(limit)
            )
            if source_slug is not None:
                query = query.where(Source.slug == source_slug)
            if editorial_only:
                query = query.where(Article.editorial_relevance.in_(("direct", "potential")))
            articles = list(session.scalars(query))
            topics = {topic.slug: topic for topic in session.scalars(
                select(Topic).where(Topic.enabled.is_(True))
            )}
            entities = list(session.scalars(select(Entity).where(Entity.enabled.is_(True))))
            for article in articles:
                counts["examined"] += 1
                item = FetchedArticle(
                    url=article.source_url,
                    title=article.source_title,
                    body=article.source_body,
                    published_at=article.published_at,
                    language=article.language,
                    country_code=article.country_code,
                    author=article.author,
                    parse_status=article.parse_status,
                )

                def record_error(exc: Exception) -> None:
                    counts["last_error"] = str(exc)[:200]

                def record_translation_error(exc: Exception) -> None:
                    counts["translation_failures"] += 1
                    counts["last_error"] = str(exc)[:200]

                processed = process_source_article(
                    item, article.source, model_config, on_error=record_error,
                    on_translation_error=record_translation_error,
                )
                if processed.processing_status == "model_failed":
                    counts["model_failures"] += 1
                    break
                article.zh_title = processed.zh_title
                article.zh_summary = processed.zh_summary
                article.zh_body = processed.zh_body
                article.translation_status = processed.translation_status
                article.importance_score = processed.importance_score
                article.relevance = processed.relevance
                article.featured_candidate = processed.featured_candidate
                article.featured_reason = processed.featured_reason
                article.processing_status = processed.processing_status
                if processed.processing_status == "irrelevant":
                    if article.editorial_relevance in {"direct", "potential"}:
                        counts["manual_conflicts"] += 1
                    article.quality_status = "irrelevant"
                    article.topics = []
                    counts["irrelevant"] += 1
                else:
                    article.topics = [topics[slug] for slug in _topic_slugs(processed, article.source)
                                      if slug in topics]
                    counts["processed"] += 1
                link_article_entities(session, article, entities)
                session.commit()
            audit_query = (
                select(Article)
                .join(Source)
                .where(
                    *public_article_conditions(),
                    Source.adapter.in_(("rss", "gdelt")),
                )
            )
            if source_slug is not None:
                audit_query = audit_query.where(Source.slug == source_slug)
            for article in session.scalars(audit_query):
                if article.editorial_relevance in {"direct", "potential"}:
                    continue
                if has_explicit_technology(FetchedArticle(
                    url=article.source_url, title=article.source_title, body=article.source_body,
                )):
                    continue
                article.processing_status = "irrelevant"
                article.quality_status = "irrelevant"
                article.relevance = 0
                article.importance_score = 0
                article.featured_candidate = False
                article.featured_reason = None
                article.topics = []
                link_article_entities(session, article, entities)
                counts["rejected_existing"] += 1
            refresh_featured(session)
            session.commit()
        return counts
    finally:
        engine.dispose()


def translate_pending(source_slug: str | None = None, limit: int = 3) -> dict[str, object]:
    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")
    model_config = load_model_config()
    if model_config is None:
        raise RuntimeError("模型服务未配置，不能翻译历史文章。")
    model_adapter = model_adapter_from_config(model_config, body_translator=translate_source_body)
    engine = create_database_engine()
    counts: dict[str, object] = {"examined": 0, "translated": 0, "failed": 0, "last_error": None}
    try:
        with Session(engine) as session:
            query = (
                select(Article).join(Source).where(
                    Article.deleted_at.is_(None),
                    Article.processing_status == "processed",
                    Article.language.like("en%"),
                    Article.parse_status == "full_text",
                    Article.source_body.is_not(None),
                    Article.zh_body.is_(None),
                    func.length(Article.source_body) <= MAX_TRANSLATION_CHARS,
                )
                .order_by(Article.first_seen_at.desc(), Article.id.asc())
                .limit(limit)
            )
            if source_slug is not None:
                query = query.where(Source.slug == source_slug)
            for article in session.scalars(query):
                counts["examined"] += 1
                try:
                    article.zh_body = model_adapter.translate_body(article.source_body)
                except ModelAnalysisError as exc:
                    article.translation_status = "failed"
                    session.commit()
                    counts["failed"] += 1
                    counts["last_error"] = str(exc)[:200]
                    break
                counts["translated"] += 1
                article.translation_status = "available"
                session.commit()
        return counts
    finally:
        engine.dispose()


def backfill_entities() -> dict[str, int]:
    engine = create_database_engine()
    try:
        with Session(engine) as session:
            catalog = list(session.scalars(select(Entity).where(Entity.enabled.is_(True))))
            article_ids = list(session.scalars(select(Article.id).where(
                Article.deleted_at.is_(None), Article.processing_status == "processed",
            ).order_by(Article.id.asc())))
            linked = 0
            for index, article_id in enumerate(article_ids, 1):
                article = session.get(Article, article_id)
                linked += link_article_entities(session, article, catalog)
                if index % 100 == 0:
                    session.commit()
            session.commit()
            return {"articles": len(article_ids), "links": linked, "entities": len(catalog)}
    finally:
        engine.dispose()


def run_ingestion(trigger_type: str = "manual", source_slug: str | None = None,
                  idempotency_key: str | None = None) -> dict[str, object]:
    engine = create_database_engine()
    guard: LeaseGuard | None = None
    try:
        with Session(engine) as session:
            source_query = select(Source).where(Source.enabled.is_(True))
            if source_slug is not None:
                source_query = source_query.where(Source.slug == source_slug)
            sources = list(session.scalars(source_query.order_by(Source.slug)))
            if source_slug is not None and not sources:
                raise ValueError(f"No enabled source with slug: {source_slug}")
        acquired = acquire_ingestion(engine, trigger_type, source_slug, idempotency_key)
        if isinstance(acquired, dict):
            return acquired
        guard = acquired
        run_id = guard.run_id

        totals = {
            "sources": len(sources), "source_failures": 0, "discovered": 0,
            "inserted": 0, "duplicates": 0, "irrelevant": 0, "deferred": 0,
            "model_failures": 0, "model_calls": 0, "source_partials": 0,
            "source_skipped": 0, "translated": 0, "translation_failures": 0,
            "detail_parse_failed": 0,
            "metadata_skipped": 0,
        }
        failures: list[dict[str, str]] = []
        skips: list[dict[str, str]] = []
        for source in sources:
            guard.check()
            source_run = SourceRun(run_id=run_id, source_id=source.id, status="running",
                                   started_at=datetime.now(UTC))
            with Session(engine) as session, session.begin():
                guard.fence(session)
                session.add(source_run)
                session.flush()
                source_run_id = source_run.id
            if source.adapter == "gdelt":
                with Session(engine) as session:
                    previous = session.scalar(
                        select(SourceRun)
                        .where(SourceRun.source_id == source.id, SourceRun.id != source_run_id,
                               SourceRun.status != "skipped")
                        .order_by(SourceRun.finished_at.desc(), SourceRun.id.desc())
                        .limit(1)
                    )
                    cooldown_until = (
                        _as_utc(previous.finished_at) + RATE_LIMIT_COOLDOWN
                        if previous and previous.error_class == "SourceRateLimited"
                        and previous.finished_at else None
                    )
                if cooldown_until and cooldown_until > datetime.now(UTC):
                    with Session(engine) as session, session.begin():
                        guard.fence(session)
                        skipped_run = session.get(SourceRun, source_run_id)
                        skipped_run.status = "skipped"
                        skipped_run.error_class = "RateLimitCooldown"
                        skipped_run.error_message = "GDELT rate-limit cooldown is active."
                        skipped_run.finished_at = datetime.now(UTC)
                    totals["source_skipped"] += 1
                    skips.append({"source": source.slug, "reason": "rate_limit_cooldown"})
                    continue
            try:
                guard.check()
                known_urls = None
                if source.adapter in {"rss", "gdelt", "govuk_api", "ccgp_html", "nij_html", "jiangsu_police_html", "npcc_html"}:
                    with Session(engine) as lookup_session:
                        known_urls = set(lookup_session.scalars(
                            select(Article.canonical_url)
                        ))
                source_diagnostics: dict[str, int] = {}
                fetched = fetch_source(source, known_urls=known_urls,
                                       diagnostics=source_diagnostics)
                detail_parse_failed = source_diagnostics.get("detail_parse_failed", 0)
                with Session(engine) as lookup_session:
                    urls = {canonicalize_url(item.url) for item in fetched}
                    existing_urls = set(lookup_session.scalars(
                        select(Article.canonical_url).where(Article.canonical_url.in_(urls))
                    )) if urls else set()

                prepared: list[FetchedArticle] = []
                inserted = 0
                duplicates = 0
                irrelevant = 0
                deferred = 0
                model_failures = 0
                model_calls = 0
                translated = 0
                metadata_skipped = 0
                translation_failures = 0
                model_error: str | None = None
                model_config = load_model_config() if source.adapter != "ccgp_html" else None
                analysis_limit = min(max(int(source.config.get("max_analysis_candidates", 8)), 1), 30)
                for item in fetched:
                    canonical_url = canonicalize_url(item.url)
                    if canonical_url in existing_urls:
                        duplicates += 1
                        continue
                    if (item.parse_status == "metadata_only"
                            and source.config.get("store_metadata_only") is False):
                        metadata_skipped += 1
                        continue
                    existing_urls.add(canonical_url)
                    if source.adapter != "ccgp_html":
                        if len(prepared) >= analysis_limit:
                            deferred += 1
                            continue
                        if model_config is not None and item.parse_status != "metadata_only" and item.body:
                            model_calls += 1

                        def record_error(exc: Exception) -> None:
                            nonlocal model_error
                            model_error = str(exc)[:200]

                        def record_translation_error(exc: Exception) -> None:
                            nonlocal translation_failures
                            translation_failures += 1

                        item = process_source_article(
                            item, source, model_config, on_error=record_error,
                            on_translation_error=record_translation_error,
                        )
                        if item.zh_body:
                            translated += 1
                    if item.processing_status == "irrelevant":
                        irrelevant += 1
                    elif item.processing_status == "model_failed":
                        model_failures += 1
                        model_config = None
                    prepared.append(item)
                with Session(engine, expire_on_commit=False) as session, session.begin():
                    guard.fence(session)
                    topic_map = {
                        topic.slug: topic
                        for topic in session.scalars(select(Topic).where(Topic.enabled.is_(True)))
                    }
                    entity_catalog = list(session.scalars(select(Entity).where(Entity.enabled.is_(True))))
                    for item in prepared:
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
                        for index, media in enumerate(item.media[:3]):
                            session.add(ArticleMedia(
                                article_id=article.id, kind=media.kind, url=media.url,
                                thumbnail_url=media.thumbnail_url,
                                caption=media.caption, alt_text=media.alt_text,
                                position=index, status="linked",
                            ))
                        link_article_entities(session, article, entity_catalog)
                        inserted += 1
                    source_row = session.get(Source, source.id)
                    if source_row:
                        source_row.last_success_at = datetime.now(UTC)
                    run_row = session.get(SourceRun, source_run_id)
                    if run_row:
                        run_row.status = "partial" if model_failures or detail_parse_failed else "succeeded"
                        if model_failures:
                            run_row.error_class = "ModelAnalysisError"
                            run_row.error_message = (
                                f"{model_failures} article(s) could not be analyzed; "
                                f"remaining candidates were kept pending. {model_error or ''}"
                            )
                        elif detail_parse_failed:
                            run_row.error_class = "DetailParsePartial"
                            run_row.error_message = (
                                f"{detail_parse_failed} candidate detail page(s) lacked usable content."
                            )
                        run_row.discovered_count = len(fetched)
                        run_row.inserted_count = inserted
                        run_row.duplicate_count = duplicates
                        run_row.finished_at = datetime.now(UTC)
                totals["discovered"] += len(fetched)
                totals["inserted"] += inserted
                totals["duplicates"] += duplicates
                totals["irrelevant"] += irrelevant
                totals["deferred"] += deferred
                totals["model_failures"] += model_failures
                totals["model_calls"] += model_calls
                totals["translated"] += translated
                totals["translation_failures"] += translation_failures
                totals["detail_parse_failed"] += detail_parse_failed
                totals["metadata_skipped"] += metadata_skipped
                if model_failures or detail_parse_failed:
                    totals["source_partials"] += 1
            except LeaseLost:
                raise
            except Exception as exc:  # A failed source must not stop the other configured sources.
                totals["source_failures"] += 1
                failures.append({
                    "source": source.slug,
                    "error_class": type(exc).__name__,
                    "message": str(exc)[:250],
                })
                with Session(engine) as session, session.begin():
                    guard.fence(session)
                    failed_run = session.get(SourceRun, source_run_id)
                    if failed_run:
                        failed_run.status = "failed"
                        failed_run.error_class = type(exc).__name__
                        failed_run.error_message = str(exc)[:1000]
                        failed_run.finished_at = datetime.now(UTC)

        final_status = "failed" if totals["source_failures"] == len(sources) and sources else (
            "partial" if totals["source_failures"] or totals["source_partials"]
            or totals["source_skipped"] else "succeeded"
        )
        with Session(engine) as session, session.begin():
            guard.fence(session)
            run_row = session.get(IngestionRun, run_id)
            if run_row:
                run_row.status = final_status
                run_row.counts = totals
                run_row.finished_at = datetime.now(UTC)
            if final_status in {"succeeded", "partial"}:
                refresh_featured(session)
        return {"run_id": str(run_id), "status": final_status, **totals,
                "failures": failures, "skips": skips}
    except BaseException as exc:
        if guard is not None:
            interrupt_owned_run(guard, type(exc).__name__)
        raise
    finally:
        try:
            if guard is not None:
                guard.release()
        finally:
            engine.dispose()
