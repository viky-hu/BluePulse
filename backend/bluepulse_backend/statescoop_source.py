"""Bounded StateScoop law-enforcement technology RSS and HTML extraction."""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from .ccgp_source import USER_AGENT
from .live_sources import BoundedHTTP, SourceFetchError, parse_time, plain_text
from .pipeline import Candidate, canonical_url


HOST = "statescoop.com"
ROOT = f"https://{HOST}"
FEED = ROOT + "/tag/law-enforcement-technology/feed/"
ARTICLE_PATH = re.compile(r"/[a-z0-9-]+/")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "wbr"}
SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "form", "aside", "figure"}
SKIP_CLASSES = {"ad", "ad__inner", "screen-reader-text", "newsletter", "related-posts"}
TEXT_TAGS = {"p", "li", "h2", "h3", "blockquote"}


class _Article(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, set[str]]] = []
        self.title_parts: list[str] = []
        self.body_parts: list[str] = []
        self.description: str | None = None
        self.raw_date: str | None = None

    def _inside(self, name: str) -> bool:
        return any(name in classes for _, classes in self.stack)

    def _skip(self) -> bool:
        return any(tag in SKIP_TAGS or classes & SKIP_CLASSES for tag, classes in self.stack)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta":
            if values.get("property") == "article:published_time":
                self.raw_date = values.get("content")
            if values.get("name") == "description":
                self.description = values.get("content")
        if tag not in VOID:
            self.stack.append((tag, set((values.get("class") or "").split())))
        if self._inside("single-article__content-inner") and not self._skip() and tag in TEXT_TAGS | {"br"}:
            self.body_parts.append("\n")

    def handle_endtag(self, tag):
        if self._inside("single-article__content-inner") and not self._skip() and tag in TEXT_TAGS:
            self.body_parts.append("\n")
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self._skip():
            return
        if self._inside("single-article__title"):
            self.title_parts.append(data)
        if self._inside("single-article__content-inner") and any(
                tag in TEXT_TAGS for tag, _ in self.stack):
            self.body_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join("".join(self.title_parts).split())[:500]

    @property
    def body(self) -> str:
        return "\n".join(" ".join(line.split()) for line in "".join(self.body_parts).splitlines()
                         if line.strip())[:100_000]


class StateScoopAdapter:
    def __init__(self, http: BoundedHTTP, *, max_items: int = 2, sleeper=time.sleep):
        if not 1 <= max_items <= 5 or http.allowed_hosts != {HOST}:
            raise ValueError("invalid_statescoop_configuration")
        self.http, self.max_items, self.sleeper = http, max_items, sleeper
        self.diagnostics: dict[str, int] = {}
        self.item_diagnostics: list[dict] = []

    def candidates(self) -> list[Candidate]:
        self.diagnostics = {"feed_items": 0, "detail_attempts": 0,
                            "detail_full_text": 0, "detail_failed": 0}
        self.item_diagnostics = []
        try:
            robots = self.http.get(ROOT + "/robots.txt", accept="text/plain")
        except SourceFetchError as exc:
            if exc.code != "http_404":
                raise
            robots = b""
        policy = RobotFileParser()
        policy.parse(robots.decode("utf-8-sig", "replace").splitlines())
        delay = policy.crawl_delay(USER_AGENT) or 0
        if delay > 10 or not policy.can_fetch(USER_AGENT, FEED):
            raise SourceFetchError("robots_disallowed_or_delayed")

        def fetch(url: str, accept: str) -> bytes:
            if not policy.can_fetch(USER_AGENT, url):
                raise SourceFetchError("robots_disallowed")
            self.sleeper(max(1.0, float(delay)))
            return self.http.get(url, accept=accept)

        try:
            root = ET.fromstring(fetch(FEED, "application/rss+xml"))
        except ET.ParseError as exc:
            raise SourceFetchError("invalid_feed") from exc
        items = root.findall("./channel/item")
        self.diagnostics["feed_items"] = len(items)
        candidates: list[Candidate] = []
        for item in items[:self.max_items]:
            url = (item.findtext("link") or "").strip()
            parts = urlsplit(url)
            if (parts.scheme != "https" or parts.hostname != HOST or parts.query or parts.fragment or
                    not ARTICLE_PATH.fullmatch(parts.path)):
                continue
            try:
                canonical_url(url, [HOST])
            except ValueError:
                continue
            self.diagnostics["detail_attempts"] += 1
            try:
                detail = _Article()
                detail.feed(fetch(url, "text/html").decode("utf-8-sig"))
            except (SourceFetchError, UnicodeDecodeError) as exc:
                if isinstance(exc, SourceFetchError) and exc.code in {"http_403", "http_429", "robots_disallowed"}:
                    raise
                self.diagnostics["detail_failed"] += 1
                self.item_diagnostics.append({"url": url, "status": getattr(exc, "code", "decode_error")})
                continue
            if len(detail.body) < 120 or not detail.title:
                self.diagnostics["detail_failed"] += 1
                self.item_diagnostics.append({"url": url, "status": "incomplete_article",
                                              "body_chars": len(detail.body)})
                continue
            self.diagnostics["detail_full_text"] += 1
            self.item_diagnostics.append({"url": url, "status": "full_text",
                                          "body_chars": len(detail.body)})
            candidates.append(Candidate(
                url=url, title=detail.title, body=detail.body,
                summary=plain_text(item.findtext("description") or detail.description or "", max_chars=1000) or None,
                published_at=parse_time(detail.raw_date or item.findtext("pubDate")), language="en",
            ))
        if not candidates and self.diagnostics["detail_failed"]:
            raise SourceFetchError("all_details_failed")
        return candidates
