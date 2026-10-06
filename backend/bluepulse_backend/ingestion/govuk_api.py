"""GOV.UK Search + Content API ingestion; no HTML page scraping."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from time import sleep

import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlsplit

from bluepulse_backend.ingestion.adapters import (
    FetchedArticle, FetchedMedia, SourceRateLimited, USER_AGENT, _parse_date, _plain_text,
)
from bluepulse_backend.models import Source

SEARCH_URL = "https://www.gov.uk/api/search.json"
CONTENT_URL = "https://www.gov.uk/api/content"
MAX_JSON_BYTES = 2 * 1024 * 1024
CONTENT_PATH = re.compile(
    r"^/government/(?:news|publications|speeches|consultations|research)/[a-zA-Z0-9/_-]+$"
)
TECHNOLOGY = re.compile(
    r"\b(?:artificial intelligence|\bAI\b|machine learning|facial recognition|"
    r"biometric|drone|unmanned|robot|digital|cyber|algorithm|technology|"
    r"surveillance|camera|ANPR|data science|software|automation)\b", re.I,
)
POLICING = re.compile(
    r"\b(?:police|policing|law enforcement|crime|criminal|forensic|"
    r"public safety|security minister|home office)\b", re.I,
)
IMAGE_HOSTS = {"www.gov.uk", "assets.publishing.service.gov.uk"}


def _image_url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 1900:
        return None
    url = urljoin("https://www.gov.uk", value.strip())
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in IMAGE_HOSTS or parts.username or parts.password:
        return None
    return url


def _content_images(details: dict[str, object]) -> tuple[FetchedMedia, ...]:
    images: list[FetchedMedia] = []
    seen: set[str] = set()
    supplied = details.get("images")
    candidates = supplied if isinstance(supplied, list) else []
    lead = details.get("image")
    if isinstance(lead, dict):
        candidates = [lead, *candidates]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        url = _image_url(candidate.get("url") or candidate.get("src"))
        if not url or url in seen:
            continue
        seen.add(url)
        images.append(FetchedMedia(
            kind="image", url=url,
            alt_text=_text(candidate.get("alt_text") or candidate.get("alt")),
            caption=_text(candidate.get("caption")),
        ))
    body = details.get("body")
    if isinstance(body, str):
        soup = BeautifulSoup(body, "html.parser")
        for tag in soup.select("figure img, img"):
            url = _image_url(tag.get("src"))
            if not url or url in seen:
                continue
            seen.add(url)
            figure = tag.find_parent("figure")
            caption_tag = figure.find("figcaption") if figure else None
            images.append(FetchedMedia(
                kind="image", url=url,
                alt_text=_text(tag.get("alt")),
                caption=_text(caption_tag.get_text(" ", strip=True)) if caption_tag else None,
            ))
            if len(images) >= 3:
                break
    return tuple(images[:3])


def _json_get(
    client: httpx.Client, url: str, *, params: dict[str, object] | None = None,
    allow_missing: bool = False,
) -> dict:
    with client.stream("GET", url, params=params) as response:
        if response.is_redirect:
            raise RuntimeError("GOV.UK API redirected; redirect was not followed.")
        if response.status_code == 429:
            raise SourceRateLimited("GOV.UK API returned HTTP 429; wait before retrying.")
        if response.status_code == 404:
            if allow_missing:
                return {}
            raise RuntimeError("GOV.UK Search API returned HTTP 404.")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            raise RuntimeError(f"GOV.UK API returned HTTP {response.status_code}.") from None
        if "json" not in response.headers.get("content-type", "").lower():
            raise RuntimeError("GOV.UK API did not return JSON.")
        declared = response.headers.get("content-length")
        if declared and int(declared) > MAX_JSON_BYTES:
            raise RuntimeError("GOV.UK API response exceeded the size limit.")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_JSON_BYTES:
                raise RuntimeError("GOV.UK API response exceeded the size limit.")
            chunks.append(chunk)
    payload = httpx.Response(200, content=b"".join(chunks)).json()
    if not isinstance(payload, dict):
        raise RuntimeError("GOV.UK API returned an invalid JSON object.")
    return payload


def _candidate_path(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 500:
        return None
    return value if CONTENT_PATH.fullmatch(value) else None


def _text(value: object) -> str | None:
    return _plain_text(value) if isinstance(value, str) else None


def _date(value: object) -> datetime | None:
    return _parse_date(value) if isinstance(value, str) else None


def fetch_govuk_api(
    source: Source,
    known_urls: set[str] | None = None,
    diagnostics: dict[str, int] | None = None,
    client: httpx.Client | None = None,
    sleeper=sleep,
    now: datetime | None = None,
) -> list[FetchedArticle]:
    if source.base_url != SEARCH_URL or "www.gov.uk" not in source.config.get("allowed_hosts", []):
        raise ValueError("GOV.UK source must use its official HTTPS Search API endpoint.")
    queries = source.config.get("queries", [])
    if not isinstance(queries, list) or not 1 <= len(queries) <= 6 or not all(
        isinstance(query, str) and 2 <= len(query.strip()) <= 100 for query in queries
    ):
        raise ValueError("GOV.UK source needs 1–6 short search queries.")
    recent_days = min(max(int(source.config.get("recent_days", 180)), 1), 365)
    per_query = min(max(int(source.config.get("count_per_query", 30)), 1), 100)
    detail_limit = min(max(int(source.config.get("max_content_pages", 6)), 1), 20)
    delay = max(float(source.config.get("request_delay_seconds", 0.2)), 0.1)
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=recent_days)
    known_urls = known_urls or set()
    stats = diagnostics if diagnostics is not None else {}
    stats.update({"search_results": 0, "relevant_candidates": 0, "content_pages": 0,
                  "stale_content": 0, "detail_parse_failed": 0})

    def run(active_client: httpx.Client) -> list[FetchedArticle]:
        candidates: dict[str, tuple[datetime, str]] = {}
        for query in queries:
            sleeper(delay)
            payload = _json_get(active_client, SEARCH_URL, params={
                "q": query,
                "count": per_query,
                "filter_organisations": "home-office",
                "filter_public_timestamp": f"from:{cutoff.date().isoformat()}",
            })
            results = payload.get("results", [])
            if not isinstance(results, list):
                raise RuntimeError("GOV.UK Search API results are invalid.")
            stats["search_results"] += len(results)
            for result in results:
                if not isinstance(result, dict):
                    continue
                path = _candidate_path(result.get("link"))
                title = _text(result.get("title"))
                description = _text(result.get("description"))
                public_at = _date(result.get("public_timestamp"))
                if not path or not title or not public_at or public_at < cutoff:
                    continue
                evidence = f"{title} {description or ''}"
                if not TECHNOLOGY.search(evidence) or not POLICING.search(evidence):
                    continue
                url = f"https://www.gov.uk{path}"
                if url in known_urls or path in candidates:
                    continue
                candidates[path] = (public_at, title)
        stats["relevant_candidates"] = len(candidates)

        articles: list[FetchedArticle] = []
        for path, _ in sorted(candidates.items(), key=lambda pair: pair[1][0], reverse=True)[:detail_limit]:
            sleeper(delay)
            stats["content_pages"] += 1
            try:
                content = _json_get(active_client, f"{CONTENT_URL}{path}", allow_missing=True)
            except SourceRateLimited:
                raise
            except (httpx.HTTPError, RuntimeError, ValueError):
                stats["detail_parse_failed"] += 1
                continue
            if not content:
                stats["detail_parse_failed"] += 1
                continue
            title = _text(content.get("title"))
            published_at = _date(content.get("first_published_at"))
            if published_at is not None and published_at < cutoff:
                stats["stale_content"] += 1
                continue
            if not title or published_at is None:
                stats["detail_parse_failed"] += 1
                continue
            details = content.get("details") or {}
            if not isinstance(details, dict):
                details = {}
            full_body = _text(details.get("body"))
            description = _text(content.get("description"))
            substantive = bool(full_body and len(full_body) >= 600)
            body = full_body if full_body else description
            articles.append(FetchedArticle(
                url=f"https://www.gov.uk{path}", title=title,
                published_at=published_at, body=body,
                language="en", country_code="GB",
                parse_status="full_text" if substantive else (
                    "summary_only" if body else "metadata_only"
                ),
                media=_content_images(details),
            ))
        return articles

    if client is not None:
        return run(client)
    with httpx.Client(
        timeout=httpx.Timeout(connect=20, read=45, write=10, pool=8),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    ) as active_client:
        return run(active_client)
