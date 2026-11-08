"""Bounded StateScoop law-enforcement technology RSS and HTML extraction."""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import replace
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .live_sources import BoundedHTTP, SourceFetchError, parse_time, plain_text
from .pipeline import Candidate, canonical_url
from .source_page import IncompleteArticle, SourcePageReader, bounded_details


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
        self.reader = SourcePageReader(http, FEED, lambda delay: self.sleeper(delay), allow_missing_robots=True)
        self.diagnostics: dict[str, int] = {}
        self.item_diagnostics: list[dict] = []

    def _listing(self, limit: int | None = None) -> list[Candidate]:
        self.diagnostics = {"feed_items": 0, "detail_attempts": 0,
                            "detail_full_text": 0, "detail_failed": 0}
        self.item_diagnostics = []
        self.reader.refresh()
        try:
            root = ET.fromstring(self.reader.get(FEED, "application/rss+xml"))
        except ET.ParseError as exc:
            raise SourceFetchError("invalid_feed") from exc
        items = root.findall("./channel/item")
        self.diagnostics["feed_items"] = len(items)
        candidates: list[Candidate] = []
        for item in items[:limit]:
            url = (item.findtext("link") or "").strip()
            if not self._valid_article(url):
                continue
            candidates.append(Candidate(
                url=url, title=plain_text(item.findtext("title") or "", max_chars=500),
                summary=plain_text(item.findtext("description") or "", max_chars=1000) or None,
                published_at=parse_time(item.findtext("pubDate")), language="en",
            ))
        return candidates

    @staticmethod
    def _valid_article(url: str) -> bool:
        try:
            parts = urlsplit(url)
            canonical_url(url, [HOST])
            return (parts.scheme == "https" and not parts.query and not parts.fragment and
                    bool(ARTICLE_PATH.fullmatch(parts.path)))
        except ValueError:
            return False

    def list_candidates(self, *, first_import: bool = False) -> list[Candidate]:
        return self._listing()

    def fetch_detail(self, candidate: Candidate) -> Candidate:
        if not self._valid_article(candidate.url):
            raise SourceFetchError("invalid_article_url")
        self.diagnostics["detail_attempts"] = self.diagnostics.get("detail_attempts", 0) + 1
        detail = _Article()
        try:
            detail.feed(self.reader.get(candidate.url, "text/html").decode("utf-8-sig"))
        except UnicodeDecodeError as exc:
            raise SourceFetchError("decode_error") from exc
        body = detail.body
        if len(body) < 120 or not detail.title:
            raise IncompleteArticle(len(body))
        self.diagnostics["detail_full_text"] = self.diagnostics.get("detail_full_text", 0) + 1
        self.item_diagnostics.append({"url": candidate.url, "status": "full_text", "body_chars": len(body)})
        return replace(candidate, title=detail.title, body=body,
                       summary=candidate.summary or plain_text(detail.description or "", max_chars=1000) or None,
                       published_at=parse_time(detail.raw_date) or candidate.published_at)

    def candidates(self) -> list[Candidate]:
        return bounded_details(self._listing(self.max_items), self.fetch_detail,
                               self.diagnostics, self.item_diagnostics)
