"""Bounded Singapore Police Force Police Life technology articles."""
from __future__ import annotations

import re
import time
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from .ccgp_source import USER_AGENT
from .live_sources import BoundedHTTP, SourceFetchError
from .pipeline import Candidate, canonical_url


HOST = "www.police.gov.sg"
ROOT = f"https://{HOST}"
LISTING = ROOT + "/Media-Hub/Police-Life"
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
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, set[str]]] = []
        self.title_parts: list[str] = []
        self.date_parts: list[str] = []
        self.body_parts: list[str] = []
        self.description: str | None = None

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
        self.diagnostics: dict[str, int] = {}
        self.item_diagnostics: list[dict] = []

    def candidates(self) -> list[Candidate]:
        self.diagnostics = {"listing_links": 0, "topic_matches": 0, "detail_attempts": 0,
                            "detail_full_text": 0, "detail_failed": 0}
        self.item_diagnostics = []
        robots = self.http.get(ROOT + "/robots.txt", accept="text/plain")
        policy = RobotFileParser()
        policy.parse(robots.decode("utf-8-sig", "replace").splitlines())
        delay = policy.crawl_delay(USER_AGENT) or 0
        if delay > 10 or not policy.can_fetch(USER_AGENT, LISTING):
            raise SourceFetchError("robots_disallowed_or_delayed")

        def fetch(url: str) -> bytes:
            if not policy.can_fetch(USER_AGENT, url):
                raise SourceFetchError("robots_disallowed")
            self.sleeper(max(1.0, float(delay)))
            return self.http.get(url, accept="text/html")

        links = _Links()
        links.feed(fetch(LISTING).decode("utf-8-sig", "replace"))
        selected: dict[str, tuple[str, bool, int]] = {}
        for position, (href, title, latest) in enumerate(links.items):
            url = urljoin(LISTING, href)
            parts = urlsplit(url)
            if (parts.scheme != "https" or parts.hostname != HOST or parts.query or parts.fragment or
                    not ARTICLE_PATH.fullmatch(parts.path)):
                continue
            try:
                canonical_url(url, [HOST])
            except ValueError:
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
            if self.diagnostics["detail_attempts"] >= self.max_items:
                continue
            self.diagnostics["detail_attempts"] += 1
            try:
                detail = _Article()
                detail.feed(fetch(url).decode("utf-8-sig", "replace"))
            except SourceFetchError as exc:
                if exc.code in {"http_403", "http_429", "robots_disallowed"}:
                    raise
                self.diagnostics["detail_failed"] += 1
                self.item_diagnostics.append({"url": url, "status": exc.code})
                continue
            if not detail.title or len(detail.body) < 120 or detail.published_date is None:
                self.diagnostics["detail_failed"] += 1
                self.item_diagnostics.append({"url": url, "status": "incomplete_article",
                                              "body_chars": len(detail.body)})
                continue
            self.diagnostics["detail_full_text"] += 1
            self.item_diagnostics.append({"url": url, "status": "full_text",
                                          "body_chars": len(detail.body),
                                          "published_date": detail.published_date.isoformat()})
            candidates.append(Candidate(url=url, title=detail.title, body=detail.body,
                                        summary=detail.description, published_date=detail.published_date,
                                        language="en"))
        if not candidates and self.diagnostics["detail_failed"]:
            raise SourceFetchError("all_details_failed")
        return candidates
