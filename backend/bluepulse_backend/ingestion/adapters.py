from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from time import struct_time
from time import sleep
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import feedparser
import httpx
from bs4 import BeautifulSoup

from bluepulse_backend.models import Source

USER_AGENT = "BluePulseResearchBot/0.1 (+public-source-ingestion)"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
OPENALEX_DOMAIN = re.compile(r"\b(?:police|policing|law enforcement|public safety|criminal investigation)\b", re.I)
OPENALEX_TECH = re.compile(
    r"\b(?:artificial intelligence|machine learning|large language model|llm|drone|"
    r"computer vision|digital forensics?|robot(?:ics)?|surveillance|biometric|"
    r"cybersecurity|algorithm|facial recognition|autonomous systems?)\b", re.I,
)


class SourceAccessChallenge(RuntimeError):
    """The publisher requires an interactive access check; do not bypass it."""


class SourceRateLimited(RuntimeError):
    """The publisher asked clients to slow down; do not immediately retry."""


@dataclass(frozen=True)
class FetchedMedia:
    kind: str
    url: str
    thumbnail_url: str | None = None
    caption: str | None = None
    alt_text: str | None = None


@dataclass(frozen=True)
class FetchedArticle:
    url: str
    title: str
    published_at: datetime | None = None
    body: str | None = None
    language: str = "und"
    country_code: str | None = None
    author: str | None = None
    parse_status: str = "metadata_only"
    zh_title: str | None = None
    zh_summary: str | None = None
    zh_body: str | None = None
    topic_slugs: tuple[str, ...] = ()
    importance_score: int = 0
    relevance: float | None = None
    featured_candidate: bool = False
    featured_reason: str | None = None
    processing_status: str = "pending_model"
    translation_status: str | None = None
    media: tuple[FetchedMedia, ...] = ()


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            cleaned = " ".join(data.split())
            if cleaned:
                self.parts.append(cleaned)


def _plain_text(value: str | None) -> str | None:
    if not value:
        return None
    parser = _TextExtractor()
    parser.feed(value)
    result = " ".join(parser.parts)
    return html.unescape(result)[:100_000] or None


def _safe_http_url(value: str | None) -> str | None:
    if not value or len(value) > 2000:
        return None
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
        return None
    return value.strip()


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        except (TypeError, ValueError, OverflowError):
            return None


def _feed_date(value: struct_time | None) -> datetime | None:
    return datetime(*value[:6], tzinfo=UTC) if value else None


def _gdelt_language(value: object) -> str:
    if not isinstance(value, str):
        return "und"
    return {"english": "en", "chinese": "zh", "spanish": "es", "french": "fr"}.get(
        value.strip().lower(), value.strip().lower()[:12] or "und"
    )


def _gdelt_country(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    country = value.strip().lower()
    if len(country) == 2 and country.isalpha():
        return country.upper()
    return {"united states": "US", "united kingdom": "GB", "china": "CN",
            "canada": "CA", "australia": "AU"}.get(country)


def _abstract_from_index(index: dict[str, list[int]] | None) -> str | None:
    if not isinstance(index, dict):
        return None
    positions_to_words: dict[int, str] = {}
    for word, positions in index.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and not isinstance(position, bool) and 0 <= position < 20_000:
                positions_to_words[position] = word
    return " ".join(positions_to_words[pos] for pos in sorted(positions_to_words))[:100_000] or None


def _check_endpoint(source: Source) -> None:
    parts = urlsplit(source.base_url)
    allowed = set(source.config.get("allowed_hosts", []))
    if parts.scheme != "https" or not parts.hostname or parts.hostname.lower() not in allowed:
        raise ValueError("Configured source endpoint is not an allowed HTTPS host.")


def _get_json_or_text(source: Source, params: dict[str, object] | None = None) -> bytes:
    _check_endpoint(source)
    timeout = httpx.Timeout(connect=20, read=45, write=10, pool=8)
    with httpx.Client(
        timeout=timeout,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/rss+xml, application/xml, text/xml"},
    ) as client:
        for attempt in range(2):
            try:
                with client.stream("GET", source.base_url, params=params) as response:
                    if response.is_redirect:
                        raise RuntimeError("Source redirected the request; redirect was not followed.")
                    if response.headers.get("x-amzn-waf-action", "").lower() in {
                        "challenge", "captcha", "block",
                    }:
                        raise SourceAccessChallenge(
                            "Source requires an interactive access challenge; RSS/API was not fetched."
                        )
                    if response.status_code == 202:
                        if attempt == 0:
                            sleep(1)
                            continue
                        raise RuntimeError("Source returned HTTP 202 without a completed feed/API response.")
                    if response.status_code == 429:
                        raise SourceRateLimited(
                            "Source returned HTTP 429; wait before retrying this source."
                        )
                    if response.status_code in {500, 502, 503, 504} and attempt == 0:
                        sleep(1)
                        continue
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError:
                        raise RuntimeError(
                            f"Source returned HTTP {response.status_code}."
                        ) from None
                    declared_size = response.headers.get("content-length")
                    if declared_size and int(declared_size) > MAX_RESPONSE_BYTES:
                        raise RuntimeError("Source response exceeded the configured size limit.")
                    chunks: list[bytes] = []
                    byte_count = 0
                    for chunk in response.iter_bytes():
                        byte_count += len(chunk)
                        if byte_count > MAX_RESPONSE_BYTES:
                            raise RuntimeError("Source response exceeded the configured size limit.")
                        chunks.append(chunk)
                    return b"".join(chunks)
            except httpx.TransportError:
                if attempt == 1:
                    raise
                sleep(1)
        raise RuntimeError("Source request did not complete.")


def _article_detail_text(raw: bytes) -> tuple[str | None, datetime | None]:
    soup = BeautifulSoup(raw, "html.parser")
    content = (soup.select_one('[itemprop="articleBody"]') or soup.select_one("article")
               or soup.select_one("main .article-content, main .article-body"))
    if content is None:
        return None, None
    for element in content.select("script, style, noscript, nav, footer, aside, form, figure, .related, .advertisement"):
        element.decompose()
    paragraphs = [" ".join(node.get_text(" ", strip=True).split())
                  for node in content.select("p, h2, h3, li")]
    body = "\n\n".join(part for part in paragraphs if len(part) >= 20)[:100_000]
    meta = (soup.select_one('meta[property="article:published_time"]')
            or soup.select_one('meta[name="date"]') or soup.select_one("time[datetime]"))
    date_value = meta.get("content") or meta.get("datetime") if meta else None
    return (body if len(body) >= 300 else None), _parse_date(date_value)


def _enrich_html_details(
    articles: list[FetchedArticle], known_urls: set[str],
    allowed_paths: dict[str, list[str]], limit: int, delay: float,
    client: httpx.Client, sleeper,
) -> list[FetchedArticle]:
    candidates: list[tuple[int, FetchedArticle]] = []
    for index, item in enumerate(articles):
        parsed = urlsplit(item.url)
        prefixes = allowed_paths.get(parsed.hostname or "", [])
        if (item.url not in known_urls and item.parse_status != "full_text"
                and parsed.scheme == "https" and any(parsed.path.startswith(prefix) for prefix in prefixes)
                and parsed.port in {None, 443} and not parsed.username and not parsed.password):
            candidates.append((index, item))
    if not candidates:
        return articles
    policies: dict[str, RobotFileParser | None] = {}
    enriched = list(articles)
    for index, item in candidates[:limit]:
        host = urlsplit(item.url).hostname
        if not host:
            continue
        if host not in policies:
            robots_url = f"https://{host}/robots.txt"
            try:
                with client.stream("GET", robots_url) as response:
                    if response.is_redirect or response.status_code not in {200, 404}:
                        policies[host] = None
                        continue
                    status = response.status_code
                    robots_parts: list[bytes] = []
                    robots_size = 0
                    for chunk in response.iter_bytes():
                        robots_size += len(chunk)
                        if robots_size > 256 * 1024:
                            break
                        robots_parts.append(chunk)
                    if robots_size > 256 * 1024:
                        policies[host] = None
                        continue
                    robots = b"".join(robots_parts)
                policy = RobotFileParser()
                policy.set_url(robots_url)
                policy.parse([] if status == 404 else robots.decode("utf-8", errors="replace").splitlines())
                policies[host] = policy
            except (httpx.HTTPError, ValueError):
                policies[host] = None
                continue
        policy = policies[host]
        if policy is None or not policy.can_fetch(USER_AGENT, item.url):
            continue
        sleeper(max(delay, float(policy.crawl_delay(USER_AGENT) or 0), 1.0))
        try:
            with client.stream("GET", item.url) as response:
                if (response.is_redirect or response.status_code != 200
                        or response.headers.get("x-amzn-waf-action", "").lower() in {"challenge", "captcha", "block"}
                        or "html" not in response.headers.get("content-type", "text/html").lower()):
                    continue
                declared = response.headers.get("content-length")
                if declared and int(declared) > 2 * 1024 * 1024:
                    continue
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 2 * 1024 * 1024:
                        break
                    chunks.append(chunk)
                if size > 2 * 1024 * 1024:
                    continue
            body, published_at = _article_detail_text(b"".join(chunks))
            if body:
                enriched[index] = replace(item, body=body, parse_status="full_text",
                                          published_at=item.published_at or published_at)
        except (httpx.HTTPError, ValueError):
            continue
    return enriched


def fetch_rss(
    source: Source, known_urls: set[str] | None = None,
    detail_client: httpx.Client | None = None, sleeper=sleep,
    now: datetime | None = None,
) -> list[FetchedArticle]:
    payload = _get_json_or_text(source)
    parsed = feedparser.parse(payload)
    if not parsed.version and not parsed.entries:
        raise SourceAccessChallenge("RSS response is not a feed; an access challenge or site change may be active.")
    max_items = min(max(int(source.config.get("max_items", 50)), 1), 100)
    allowed_entry_paths = source.config.get("allowed_entry_paths")
    if allowed_entry_paths is not None and (
        not isinstance(allowed_entry_paths, list)
        or not all(isinstance(path, str) and path.startswith("/") for path in allowed_entry_paths)
    ):
        raise ValueError("RSS allowed_entry_paths must be a list of absolute path prefixes.")
    allowed_entry_hosts = source.config.get("allowed_entry_hosts")
    if allowed_entry_hosts is not None and (
        not isinstance(allowed_entry_hosts, list)
        or not all(isinstance(host, str) and host for host in allowed_entry_hosts)
    ):
        raise ValueError("RSS allowed_entry_hosts must be a list of hostnames.")
    max_age_days = source.config.get("max_age_days")
    if max_age_days is not None:
        max_age_days = min(max(int(max_age_days), 1), 3650)
    now = now or datetime.now(UTC)
    results: list[FetchedArticle] = []
    for entry in parsed.entries[:max_items]:
        url = _safe_http_url(getattr(entry, "link", None))
        title = _plain_text(getattr(entry, "title", None))
        if not url or not title:
            continue
        if allowed_entry_hosts is not None and urlsplit(url).hostname not in allowed_entry_hosts:
            continue
        if allowed_entry_paths is not None and not any(
            urlsplit(url).path.startswith(path) for path in allowed_entry_paths
        ):
            continue
        published_at = _feed_date(
            getattr(entry, "published_parsed", None)
            or getattr(entry, "updated_parsed", None)
        )
        if max_age_days is not None and (
            published_at is None or published_at < now - timedelta(days=max_age_days)
        ):
            continue
        summary = _plain_text(getattr(entry, "summary", None))
        contents = getattr(entry, "content", [])
        content = _plain_text(contents[0].get("value")) if contents else None
        body = content if content and len(content) > len(summary or "") else summary
        # Feed content can itself be an excerpt; only a parsed article page is full_text.
        parse_status = "summary_only" if body else "metadata_only"
        results.append(
            FetchedArticle(
                url=url,
                title=title,
                published_at=published_at,
                body=body,
                language=source.language,
                author=_plain_text(getattr(entry, "author", None)),
                country_code=source.country_code,
                parse_status=parse_status,
            )
        )
    if not source.config.get("fetch_article_html"):
        return results
    feed_host = urlsplit(source.base_url).hostname
    if not feed_host or feed_host not in set(source.config.get("allowed_hosts", [])):
        return results
    allowed_paths = {feed_host: allowed_entry_paths or ["/"]}
    limit = min(max(int(source.config.get("max_detail_pages", 3)), 0), 8)
    delay = max(float(source.config.get("request_delay_seconds", 1)), 1.0)
    if detail_client is not None:
        return _enrich_html_details(results, known_urls or set(), allowed_paths,
                                    limit, delay, detail_client, sleeper)
    with httpx.Client(
        timeout=httpx.Timeout(connect=15, read=30, write=10, pool=5),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    ) as client:
        return _enrich_html_details(results, known_urls or set(), allowed_paths,
                                    limit, delay, client, sleeper)


def fetch_gdelt(
    source: Source, known_urls: set[str] | None = None,
    detail_client: httpx.Client | None = None, sleeper=sleep,
) -> list[FetchedArticle]:
    params = {
        "query": source.config["query"],
        "mode": "artlist",
        "format": "json",
        "sort": "datedesc",
        "timespan": source.config.get("timespan", "7d"),
        "maxrecords": min(max(int(source.config.get("maxrecords", 50)), 1), 250),
    }
    payload = json.loads(_get_json_or_text(source, params))
    results: list[FetchedArticle] = []
    for item in payload.get("articles", []):
        url = _safe_http_url(item.get("url"))
        title = _plain_text(item.get("title"))
        if not url or not title:
            continue
        # GDELT's seendate is when its index observed the URL, not the publisher's date.
        published_at = None
        country = _gdelt_country(item.get("sourcecountry"))
        results.append(
            FetchedArticle(
                url=url,
                title=title,
                published_at=published_at,
                language=_gdelt_language(item.get("language")),
                country_code=country,
                parse_status="metadata_only",
            )
        )
    paths = source.config.get("article_hosts", {})
    if not isinstance(paths, dict) or not paths:
        return results
    allowed_paths = {
        host: prefixes for host, prefixes in paths.items()
        if isinstance(host, str) and isinstance(prefixes, list)
        and all(isinstance(prefix, str) and prefix.startswith("/") for prefix in prefixes)
    }
    limit = min(max(int(source.config.get("max_detail_pages", 3)), 0), 8)
    delay = max(float(source.config.get("request_delay_seconds", 1)), 1.0)
    if detail_client is not None:
        return _enrich_html_details(results, known_urls or set(), allowed_paths,
                                    limit, delay, detail_client, sleeper)
    with httpx.Client(
        timeout=httpx.Timeout(connect=15, read=30, write=10, pool=5),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    ) as client:
        return _enrich_html_details(results, known_urls or set(), allowed_paths,
                                    limit, delay, client, sleeper)


def fetch_openalex(source: Source) -> list[FetchedArticle]:
    search_parameter = source.config.get("search_parameter", "search")
    if search_parameter not in {"search", "search.title_and_abstract"}:
        raise ValueError("Unsupported OpenAlex search parameter.")
    params = {
        search_parameter: source.config["search"],
        "per-page": min(max(int(source.config.get("per_page", 25)), 1), 100),
        "sort": "publication_date:desc",
        "select": "id,title,publication_date,authorships,abstract_inverted_index,primary_location,biblio",
    }
    payload = json.loads(_get_json_or_text(source, params))
    results: list[FetchedArticle] = []
    max_filtered = min(max(int(source.config.get("max_filtered_items", 25)), 1), 100)
    for item in payload.get("results", []):
        location = item.get("primary_location") or {}
        landing_page = location.get("landing_page_url")
        url = _safe_http_url(landing_page) or _safe_http_url(item.get("id"))
        title = _plain_text(item.get("title"))
        if not url or not title:
            continue
        abstract = _abstract_from_index(item.get("abstract_inverted_index"))
        evidence = f"{title} {(abstract or '')[:600]}"
        focused = bool(OPENALEX_DOMAIN.search(title)) or bool(
            OPENALEX_TECH.search(title) and OPENALEX_DOMAIN.search((abstract or "")[:500])
        )
        if not (focused and OPENALEX_TECH.search(evidence)):
            continue
        authors: list[str] = []
        for authorship in item.get("authorships") or []:
            author = authorship.get("author") or {}
            name = author.get("display_name") if isinstance(author, dict) else None
            if isinstance(name, str) and name.strip() and name not in authors:
                authors.append(name.strip())
        results.append(
            FetchedArticle(
                url=url,
                title=title,
                published_at=_parse_date(item.get("publication_date")),
                body=abstract,
                language="en",
                # Author affiliation is not the geography studied by a paper.
                country_code=None,
                author=", ".join(authors[:3])[:500] or None,
                parse_status=(
                    "abstract_only"
                    if abstract
                    else "metadata_only"
                ),
            )
        )
        if len(results) >= max_filtered:
            break
    return results


ADAPTERS = {"rss": fetch_rss, "gdelt": fetch_gdelt, "openalex": fetch_openalex}


def fetch_source(
    source: Source, known_urls: set[str] | None = None,
    diagnostics: dict[str, int] | None = None,
) -> list[FetchedArticle]:
    if source.adapter == "rss":
        return fetch_rss(source, known_urls=known_urls)
    if source.adapter == "gdelt":
        return fetch_gdelt(source, known_urls=known_urls)
    if source.adapter == "ccgp_html":
        from bluepulse_backend.ingestion.ccgp_html import fetch_ccgp_html

        return fetch_ccgp_html(source, known_urls=known_urls, diagnostics=diagnostics)
    if source.adapter == "nij_html":
        from bluepulse_backend.ingestion.nij_html import fetch_nij_html

        return fetch_nij_html(source, known_urls=known_urls, diagnostics=diagnostics)
    if source.adapter == "jiangsu_police_html":
        from bluepulse_backend.ingestion.jiangsu_police_html import fetch_jiangsu_police_html

        return fetch_jiangsu_police_html(source, known_urls=known_urls, diagnostics=diagnostics)
    if source.adapter == "npcc_html":
        from bluepulse_backend.ingestion.npcc_html import fetch_npcc_html

        return fetch_npcc_html(source, known_urls=known_urls, diagnostics=diagnostics)
    if source.adapter == "govuk_api":
        from bluepulse_backend.ingestion.govuk_api import fetch_govuk_api

        return fetch_govuk_api(source, known_urls=known_urls, diagnostics=diagnostics)
    try:
        adapter = ADAPTERS[source.adapter]
    except KeyError as exc:
        raise ValueError(f"Unsupported source adapter: {source.adapter}") from exc
    return adapter(source)
