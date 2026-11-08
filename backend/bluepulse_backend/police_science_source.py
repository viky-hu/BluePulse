"""Bounded Police Science & Technology news discovery and text extraction."""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from .ccgp_source import USER_AGENT
from .live_sources import BoundedHTTP, SourceFetchError
from .pipeline import Candidate
from .source_images import ArticleImages


HOST = "science.police.uk"
ROOT = f"https://{HOST}"
ROBOTS = ROOT + "/robots.txt"
SITEMAP = ROOT + "/sitemap.xml"
NEWS_PATH = re.compile(r"/news-and-events/news/[a-z0-9-]+/")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "wbr"}


def _news_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        return bool(parts.scheme == "https" and parts.hostname == HOST and
                    parts.port in (None, 443) and not parts.username and not parts.password and
                    not parts.query and not parts.fragment and NEWS_PATH.fullmatch(parts.path))
    except ValueError:
        return False


def news_urls_from_sitemap(raw: bytes) -> list[str]:
    root = ET.fromstring(raw)
    urls: list[str] = []
    for item in root.findall(".//{*}url"):
        url = item.findtext("{*}loc")
        if url and _news_url(url):
            urls.append(url)
    return list(dict.fromkeys(urls))


@dataclass(frozen=True)
class PoliceScienceArticle:
    title: str
    body: str
    published_date: str | None
    description: str | None
    media: list[dict]


class _News(HTMLParser):
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, set[str]]] = []
        self.title: list[str] = []
        self.body: list[str] = []
        self.date: list[str] = []
        self.description: str | None = None
        self.images = ArticleImages(url, HOST)

    def _in(self, name: str) -> bool:
        return any(name in classes for _, classes in self.stack)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta" and values.get("name") == "description":
            self.description = values.get("content")
        if tag == "img" and self._in("article_copy"):
            self.images.add(values)
        if tag not in VOID:
            self.stack.append((tag, set((values.get("class") or "").split())))
        if self._in("article_copy") and tag in {"p", "li", "h2", "h3", "br"}:
            self.body.append("\n")

    def handle_endtag(self, tag):
        if self._in("article_copy") and tag in {"p", "li", "h2", "h3"}:
            self.body.append("\n")
        for pos in range(len(self.stack) - 1, -1, -1):
            if self.stack[pos][0] == tag:
                del self.stack[pos:]
                break

    def handle_data(self, data):
        if any(tag in {"script", "style", "noscript", "nav", "footer"} for tag, _ in self.stack):
            return
        if self._in("article_title"):
            self.title.append(data)
        if self._in("event_date"):
            self.date.append(data)
        if self._in("article_copy"):
            self.body.append(data)


def parse_news_html(html: str, url: str = ROOT) -> PoliceScienceArticle:
    parser = _News(url)
    parser.feed(html)
    raw_date = " ".join("".join(parser.date).replace("PUBLISHED:", "").split())
    try:
        date = datetime.strptime(raw_date, "%d %B %Y").date().isoformat()
    except ValueError:
        date = None
    body = "\n".join(" ".join(line.split()) for line in "".join(parser.body).splitlines() if line.strip())[:100_000]
    return PoliceScienceArticle(" ".join("".join(parser.title).split())[:500], body, date, parser.description,
                                list(parser.images.items.values()))


class PoliceScienceAdapter:
    def __init__(self, http: BoundedHTTP, *, max_items: int = 2, sleeper=time.sleep):
        if not 1 <= max_items <= 5:
            raise ValueError("max_items_must_be_1_to_5")
        if http.allowed_hosts != {HOST}:
            raise ValueError("police_science_host_policy_mismatch")
        self.http, self.max_items, self.sleeper = http, max_items, sleeper
        self._policy: RobotFileParser | None = None
        self._delay = 0.0
        self._reset_diagnostics()

    def _robots(self) -> RobotFileParser:
        """Follow only same-URL robots redirects; network/server failures fail closed."""
        policy = RobotFileParser()
        for redirects in range(7):
            if self.http.delay_seconds:
                self.sleeper(self.http.delay_seconds)
            try:
                with self.http.client.stream("GET", ROBOTS, follow_redirects=False,
                                             headers={"Accept": "text/plain"}) as response:
                    status = response.status_code
                    location = response.headers.get("location")
                    if status == 200:
                        data = bytearray()
                        for chunk in response.iter_bytes():
                            data.extend(chunk)
                            if len(data) > 512 * 1024:
                                raise SourceFetchError("robots_too_large")
                        policy.parse(bytes(data).decode("utf-8-sig", "replace").splitlines())
                        self.diagnostics["robots_status"] = "parsed"
                        return policy
            except httpx.TimeoutException as exc:
                raise SourceFetchError("robots_timeout") from exc
            except httpx.TransportError as exc:
                raise SourceFetchError("robots_transport_error") from exc
            if status == 404:
                policy.parse([])
                self.diagnostics["robots_status"] = "404_unavailable"
                return policy
            if status in {301, 302, 303, 307, 308} and location and urljoin(ROBOTS, location) == ROBOTS:
                if redirects == 6:
                    # RFC 9309 §2.3.1.2 permits unavailable after >5 redirects.
                    policy.parse([])
                    self.diagnostics["robots_status"] = "self_redirect_unavailable"
                    return policy
                continue
            raise SourceFetchError(f"robots_http_{status}")
        raise SourceFetchError("robots_redirect_limit")

    def _reset_diagnostics(self) -> None:
        self.diagnostics = {"sitemap_news_urls": 0, "detail_attempts": 0,
                            "detail_full_text": 0, "detail_failed": 0,
                            "detail_date_only": 0}
        self.item_diagnostics = []

    def _load_robots(self) -> None:
        policy = self._robots()
        delay = policy.crawl_delay(USER_AGENT) or 0
        if delay > 10 or not policy.can_fetch(USER_AGENT, SITEMAP):
            raise SourceFetchError("robots_disallowed_or_delayed")
        self._policy, self._delay = policy, max(1.0, float(delay))

    def _fetch(self, url: str) -> bytes:
        if self._policy is None:
            self._load_robots()
        if not self._policy.can_fetch(USER_AGENT, url):
            raise SourceFetchError("robots_disallowed")
        if getattr(self.http.client, "pulse_host_pace", None):
            self.http.delay_seconds = max(self.http.delay_seconds, self._delay)
        else:
            self.sleeper(self._delay)
        return self.http.get(url, accept="text/html, application/xml;q=0.9")

    def list_candidates(self, *, first_import: bool = False) -> list[Candidate]:
        self._reset_diagnostics()
        self._policy = None
        try:
            urls = news_urls_from_sitemap(self._fetch(SITEMAP))
        except ET.ParseError as exc:
            raise SourceFetchError("invalid_sitemap") from exc
        self.diagnostics["sitemap_news_urls"] = len(urls)
        # A sitemap gives URL identity, not a headline or publication date.
        return [Candidate(url=url, title="", language="en") for url in urls]

    def _fetch_detail(self, candidate: Candidate, *, require_date: bool) -> Candidate:
        url = candidate.url
        if not _news_url(url):
            raise SourceFetchError("invalid_article_url")
        self.diagnostics["detail_attempts"] += 1
        try:
            article = parse_news_html(self._fetch(url).decode("utf-8-sig"), url)
        except (SourceFetchError, UnicodeDecodeError) as exc:
            self.diagnostics["detail_failed"] += 1
            self.item_diagnostics.append({"url": url, "status": getattr(exc, "code", "decode_error")})
            if isinstance(exc, UnicodeDecodeError):
                raise SourceFetchError("decode_error") from exc
            raise
        if not article.title or len(article.body) < 120 or require_date and not article.published_date:
            self.diagnostics["detail_failed"] += 1
            self.item_diagnostics.append({"url": url, "status": "incomplete_article",
                                          "body_chars": len(article.body),
                                          "published_date": article.published_date})
            raise SourceFetchError("incomplete_article")
        self.diagnostics["detail_full_text"] += 1
        self.diagnostics["detail_date_only"] += int(bool(article.published_date))
        self.item_diagnostics.append({"url": url, "status": "full_text",
                                      "body_chars": len(article.body),
                                      "published_date": article.published_date})
        images = [image for image in article.media if self._policy.can_fetch(USER_AGENT, image["url"])]
        return replace(candidate, title=article.title, body=article.body,
                       summary=article.description or candidate.summary,
                       published_date=date.fromisoformat(article.published_date) if article.published_date
                       else candidate.published_date, media=images or candidate.media)

    def fetch_detail(self, candidate: Candidate) -> Candidate:
        return self._fetch_detail(candidate, require_date=False)

    def candidates(self) -> list[Candidate]:
        candidates: list[Candidate] = []
        for listed in self.list_candidates()[:self.max_items]:
            try:
                candidates.append(self._fetch_detail(listed, require_date=True))
            except SourceFetchError as exc:
                if exc.code in {"http_403", "http_429", "robots_disallowed"}:
                    raise
        if not candidates and self.diagnostics["detail_failed"]:
            raise SourceFetchError("all_details_failed")
        return candidates
