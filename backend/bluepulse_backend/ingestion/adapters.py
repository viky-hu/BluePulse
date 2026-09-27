from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from time import struct_time
from time import sleep
from urllib.parse import urlsplit

import feedparser
import httpx

from bluepulse_backend.models import Source

USER_AGENT = "BluePulseResearchBot/0.1 (+public-source-ingestion)"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


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


def _abstract_from_index(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    words: list[str] = []
    for word, positions in index.items():
        for position in positions:
            if position >= 0:
                if position >= len(words):
                    words.extend([""] * (position + 1 - len(words)))
                words[position] = word
    return " ".join(word for word in words if word)[:100_000] or None


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
                    if response.status_code == 202:
                        raise RuntimeError("Source returned HTTP 202 without a completed feed/API response.")
                    if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                        sleep(1)
                        continue
                    response.raise_for_status()
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


def fetch_rss(source: Source) -> list[FetchedArticle]:
    payload = _get_json_or_text(source)
    parsed = feedparser.parse(payload)
    max_items = min(max(int(source.config.get("max_items", 50)), 1), 100)
    results: list[FetchedArticle] = []
    for entry in parsed.entries[:max_items]:
        url = _safe_http_url(getattr(entry, "link", None))
        title = _plain_text(getattr(entry, "title", None))
        if not url or not title:
            continue
        body = _plain_text(getattr(entry, "summary", None))
        parse_status = "summary_only" if body else "metadata_only"
        if not body:
            contents = getattr(entry, "content", [])
            if contents:
                body = _plain_text(contents[0].get("value"))
                if body:
                    parse_status = "summary_only"
        results.append(
            FetchedArticle(
                url=url,
                title=title,
                published_at=_feed_date(
                    getattr(entry, "published_parsed", None)
                    or getattr(entry, "updated_parsed", None)
                ),
                body=body,
                language=source.language,
                author=_plain_text(getattr(entry, "author", None)),
                country_code=source.country_code,
                parse_status=parse_status,
            )
        )
    return results


def fetch_gdelt(source: Source) -> list[FetchedArticle]:
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
        seen_date = item.get("seendate")
        published_at = None
        if isinstance(seen_date, str):
            try:
                published_at = datetime.strptime(seen_date, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            except ValueError:
                pass
        country = (item.get("sourcecountry") or "").upper()[:2] or None
        results.append(
            FetchedArticle(
                url=url,
                title=title,
                published_at=published_at,
                language=(item.get("language") or "und").lower(),
                country_code=country,
                parse_status="metadata_only",
            )
        )
    return results


def fetch_openalex(source: Source) -> list[FetchedArticle]:
    params = {
        "search": source.config["search"],
        "per-page": min(max(int(source.config.get("per_page", 25)), 1), 100),
        "sort": "publication_date:desc",
        "select": "id,title,publication_date,authorships,abstract_inverted_index,primary_location,biblio",
    }
    payload = json.loads(_get_json_or_text(source, params))
    results: list[FetchedArticle] = []
    for item in payload.get("results", []):
        location = item.get("primary_location") or {}
        landing_page = location.get("landing_page_url")
        url = _safe_http_url(landing_page) or _safe_http_url(item.get("id"))
        title = _plain_text(item.get("title"))
        if not url or not title:
            continue
        institutions: list[str] = []
        for authorship in item.get("authorships", []):
            for institution in authorship.get("institutions", []):
                country = institution.get("country_code")
                if country:
                    institutions.append(country.upper())
        country_code = institutions[0] if institutions else None
        results.append(
            FetchedArticle(
                url=url,
                title=title,
                published_at=_parse_date(item.get("publication_date")),
                body=_abstract_from_index(item.get("abstract_inverted_index")),
                language="en",
                country_code=country_code,
                author=None,
                parse_status=(
                    "abstract_only"
                    if item.get("abstract_inverted_index")
                    else "metadata_only"
                ),
            )
        )
    return results


ADAPTERS = {"rss": fetch_rss, "gdelt": fetch_gdelt, "openalex": fetch_openalex}


def fetch_source(source: Source) -> list[FetchedArticle]:
    try:
        adapter = ADAPTERS[source.adapter]
    except KeyError as exc:
        raise ValueError(f"Unsupported source adapter: {source.adapter}") from exc
    return adapter(source)
