"""Bounded Singapore Police Force Police Life technology articles."""
from __future__ import annotations

import json
import re
import time
from dataclasses import replace
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .ccgp_source import USER_AGENT
from .live_sources import BoundedHTTP, SourceFetchError, plain_text
from .pipeline import Candidate, canonical_url
from .source_images import ArticleImages
from .source_page import IncompleteArticle, SourcePageReader, bounded_details


HOST = "www.police.gov.sg"
ROOT = f"https://{HOST}"
LISTING = ROOT + "/Media-Hub/Police-Life"
ARCHIVE = ROOT + "/api/GetLifeArticles"
ARTICLE_PATH = re.compile(r"/Media-Hub/Police-Life/20\d{2}/\d{2}/[A-Za-z0-9-]+", re.I)
TOPIC = re.compile(r"digital|cyber|crypto|technology|\bAI\b|artificial|blockchain|drone|robot|data|"
                   r"forensic|scam|innovation", re.I)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "wbr"}
SKIP = {"script", "style", "noscript", "nav", "footer", "aside", "figure", "form"}
TEXT_TAGS = {"p", "li", "h2", "h3", "blockquote"}


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.href: str | None = None
        self.words: list[str] = []
        self.latest = False
        self.stack: list[tuple[str, set[str]]] = []
        self.items: list[tuple[str, str, bool]] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a":
            self.href = values.get("href")
            self.words = []
            self.latest = any("latest-articles__listing" in classes for _, classes in self.stack)
        if tag not in VOID:
            self.stack.append((tag, set((values.get("class") or "").split())))

    def handle_data(self, data):
        if self.href:
            self.words.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.items.append((self.href, " ".join("".join(self.words).split()), self.latest))
            self.href = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


class _Article(HTMLParser):
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, set[str]]] = []
        self.title_parts: list[str] = []
        self.date_parts: list[str] = []
        self.body_parts: list[str] = []
        self.description: str | None = None
        self.images = ArticleImages(url, HOST)

    def _in(self, name: str) -> bool:
        return any(name in classes for _, classes in self.stack)

    def _skip(self) -> bool:
        return any(tag in SKIP for tag, _ in self.stack)

    def _body(self) -> bool:
        return self._in("content-block--custom-max-width") and self._in("rte") and not self._skip()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta" and values.get("name") == "description":
            self.description = values.get("content")
        if tag == "img" and self._body():
            self.images.add(values)
        if tag not in VOID:
            self.stack.append((tag, set((values.get("class") or "").split())))
        if self._body() and tag in TEXT_TAGS | {"br"}:
            self.body_parts.append("\n")

    def handle_endtag(self, tag):
        if self._body() and tag in TEXT_TAGS:
            self.body_parts.append("\n")
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self._skip():
            return
        if self._in("lp-banner__text") and self._in("h1"):
            self.title_parts.append(data)
        if self._in("published-date"):
            self.date_parts.append(data)
        if self._body() and any(tag in TEXT_TAGS for tag, _ in self.stack):
            self.body_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join("".join(self.title_parts).split())[:500]

    @property
    def body(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.body_parts).splitlines() if line.strip()]
        if "Cyber Command Series" in lines:
            lines = lines[:lines.index("Cyber Command Series")]
        return "\n".join(lines)[:100_000]

    @property
    def published_date(self) -> date | None:
        raw = " ".join("".join(self.date_parts).split())
        try:
            return datetime.strptime(raw, "%d %b %Y").date()
        except ValueError:
            return None


class SpfPoliceLifeAdapter:
    def __init__(self, http: BoundedHTTP, *, max_items: int = 2, sleeper=time.sleep):
        if not 1 <= max_items <= 5 or http.allowed_hosts != {HOST}:
            raise ValueError("invalid_spf_configuration")
        self.http, self.max_items, self.sleeper = http, max_items, sleeper
        self.reader = SourcePageReader(http, LISTING, lambda delay: self.sleeper(delay))
        self.diagnostics: dict[str, int] = {}
        self.item_diagnostics: list[dict] = []

    def list_candidates(self, *, first_import: bool = False) -> list[Candidate]:
        self.diagnostics = {"listing_links": 0, "topic_matches": 0, "detail_attempts": 0,
                            "detail_full_text": 0, "detail_failed": 0}
        self.item_diagnostics = []
        self.reader.refresh()
        links = _Links()
        links.feed(self.reader.get(LISTING, "text/html").decode("utf-8-sig", "replace"))
        selected: dict[str, tuple[str, bool, int]] = {}
        for position, (href, title, latest) in enumerate(links.items):
            url = urljoin(LISTING, href)
            if not self._valid_article(url):
                continue
            if url not in selected or latest and not selected[url][1]:
                selected[url] = (title, latest, position)
        self.diagnostics["listing_links"] = len(selected)
        candidates: list[Candidate] = []
        for url, (listed_title, _, _) in sorted(selected.items(),
                                                 key=lambda item: (not item[1][1], item[1][2])):
            if not TOPIC.search(listed_title + " " + urlsplit(url).path):
                continue
            self.diagnostics["topic_matches"] += 1
            candidates.append(Candidate(url=url, title=listed_title, language="en"))
        return candidates

    def iter_listing_pages(self, *, start=0):
        self.reader.refresh()
        try:
            data = json.loads(self.reader.post_json(ARCHIVE, {}))
            entries = data["items"]
            total = data["totalItems"]
            if not isinstance(entries, list) or type(total) is not int or total != len(entries):
                raise ValueError("incomplete_archive")
        except (ValueError, TypeError, KeyError) as exc:
            raise SourceFetchError("invalid_listing_payload") from exc
        candidates = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise SourceFetchError("invalid_listing_payload")
            href, raw_title = entry.get("url"), entry.get("title")
            if not isinstance(href, str) or not isinstance(raw_title, str):
                continue
            url = urljoin(LISTING, href)
            if not self._valid_article(url):
                continue
            title = plain_text(raw_title, max_chars=500)
            summary = entry.get("description")
            summary = plain_text(summary, max_chars=1000) if isinstance(summary, str) else None
            if not TOPIC.search(f"{title} {urlsplit(url).path} {summary or ''}"):
                continue
            try:
                day = datetime.strptime(entry.get("date"), "%d %b %Y").date()
            except (ValueError, TypeError):
                day = None
            candidates.append(Candidate(url=url, title=title, summary=summary, published_date=day, language="en"))
        self.diagnostics = {"listing_links": total, "topic_matches": len(candidates), "coverage": "archive"}
        yield candidates, None

    @staticmethod
    def _valid_article(url: str) -> bool:
        try:
            parts = urlsplit(url)
            canonical_url(url, [HOST])
            return (parts.scheme == "https" and not parts.query and not parts.fragment and
                    bool(ARTICLE_PATH.fullmatch(parts.path)))
        except ValueError:
            return False

    def fetch_detail(self, candidate: Candidate) -> Candidate:
        url = candidate.url
        if not self._valid_article(url):
            raise SourceFetchError("invalid_article_url")
        self.diagnostics["detail_attempts"] = self.diagnostics.get("detail_attempts", 0) + 1
        detail = _Article(url)
        detail.feed(self.reader.get(url, "text/html").decode("utf-8-sig", "replace"))
        body, published_date = detail.body, detail.published_date
        if not detail.title or len(body) < 120 or published_date is None:
            raise IncompleteArticle(len(body))
        self.diagnostics["detail_full_text"] = self.diagnostics.get("detail_full_text", 0) + 1
        self.item_diagnostics.append({"url": url, "status": "full_text", "body_chars": len(body),
                                      "published_date": published_date.isoformat()})
        return replace(candidate, title=detail.title, body=body, summary=detail.description,
                       published_date=published_date,
                       media=detail.images.permitted(self.reader.prepare(), USER_AGENT))

    def candidates(self) -> list[Candidate]:
        rows = self.list_candidates()[:self.max_items]
        return bounded_details(rows, self.fetch_detail, self.diagnostics, self.item_diagnostics)
