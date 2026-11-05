"""Bounded HTX News discovery through the public listing endpoint used by its site."""
from __future__ import annotations

import json
import re
import time
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

from .ccgp_source import USER_AGENT
from .live_sources import BoundedHTTP, SourceFetchError
from .pipeline import Candidate, canonical_url


HOST = "www.htx.gov.sg"
ROOT = f"https://{HOST}"
LISTING = ROOT + "/HTXInterface/ArticleListing/GetNewsAndEventsListing"
ARTICLE_PATH = re.compile(r"/whats-happening/all-news---events/all-news/20\d{2}/[a-z0-9-]+")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "wbr"}
SKIP = {"script", "style", "noscript", "nav", "footer", "form", "aside"}


class _Article(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, set[str]]] = []
        self.title: list[str] = []
        self.body: list[str] = []
        self.description: str | None = None
        self.date: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta" and values.get("property") == "og:description":
            self.description = values.get("content")
        if tag not in VOID:
            self.stack.append((tag, set((values.get("class") or "").split())))
        if self._in("rte") and tag in {"p", "li", "h2", "h3", "br"}:
            self.body.append("\n")

    def handle_endtag(self, tag):
        if self._in("rte") and tag in {"p", "li", "h2", "h3"}:
            self.body.append("\n")
        for pos in range(len(self.stack) - 1, -1, -1):
            if self.stack[pos][0] == tag:
                del self.stack[pos:]
                break

    def handle_data(self, data):
        if any(tag in SKIP for tag, _ in self.stack):
            return
        if self._in("article-detail-banner") and any(tag == "h1" for tag, _ in self.stack):
            self.title.append(data)
        if self._in("detail__content") and self._in("rte"):
            self.body.append(data)
        if self._in("date-author") and self._in("date"):
            self.date.append(data)

    def _in(self, name: str) -> bool:
        return any(name in classes for _, classes in self.stack)

    @property
    def clean_body(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.body).splitlines() if line.strip()]
        if lines and lines[-1].casefold() == "photo gallery":
            lines.pop()
        return "\n".join(lines)[:100_000]

    @property
    def clean_title(self) -> str:
        return " ".join("".join(self.title).split())[:500]

    @property
    def published_date(self) -> date | None:
        raw = " ".join("".join(self.date).replace("Published on", "").split())
        try:
            return datetime.strptime(raw, "%d %B %Y").date()
        except ValueError:
            return None


class HtxNewsAdapter:
    def __init__(self, http: BoundedHTTP, *, max_items: int = 2, sleeper=time.sleep):
        if not 1 <= max_items <= 5:
            raise ValueError("max_items_must_be_1_to_5")
        self.http, self.max_items, self.sleeper = http, max_items, sleeper
        self.diagnostics: dict[str, int] = {}

    def candidates(self) -> list[Candidate]:
        self.diagnostics = {"listing_items": 0, "detail_attempts": 0,
                            "detail_full_text": 0, "detail_failed": 0}
        try:
            robots = self.http.get(ROOT + "/robots.txt", accept="text/plain")
        except SourceFetchError as exc:
            if exc.code != "http_404":
                raise
            robots = b""
        policy = RobotFileParser()
        policy.parse(robots.decode("utf-8", "replace").splitlines())
        delay = policy.crawl_delay(USER_AGENT) or 0
        if delay > 10 or not policy.can_fetch(USER_AGENT, LISTING):
            raise SourceFetchError("robots_disallowed_or_delayed")

        def fetch(url: str, *, params: dict | None = None, accept: str = "text/html") -> bytes:
            if not policy.can_fetch(USER_AGENT, url):
                raise SourceFetchError("robots_disallowed")
            self.sleeper(max(1.0, float(delay)))
            return self.http.get(url, params=params, accept=accept)

        raw = fetch(LISTING, params={"type": "News", "keyword": "", "topic": "all",
                                     "dateFrom": "", "dateTo": "", "page": 1},
                    accept="application/json")
        try:
            payload = json.loads(raw)
            entries = payload["data"]
            if not isinstance(entries, list):
                raise ValueError()
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceFetchError("invalid_listing_payload") from exc
        self.diagnostics["listing_items"] = len(entries)
        candidates: list[Candidate] = []
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("articleType") != "News":
                continue
            path = entry.get("url")
            if not isinstance(path, str) or not ARTICLE_PATH.fullmatch(path):
                continue
            url = urljoin(ROOT, path)
            try:
                canonical_url(url, [HOST])
            except ValueError:
                continue
            self.diagnostics["detail_attempts"] += 1
            try:
                detail = _Article()
                detail.feed(fetch(url).decode("utf-8"))
            except (SourceFetchError, UnicodeDecodeError) as exc:
                if isinstance(exc, SourceFetchError) and exc.code in {"http_403", "http_429", "robots_disallowed"}:
                    raise
                self.diagnostics["detail_failed"] += 1
                continue
            body = detail.clean_body
            if len(body) < 120:
                self.diagnostics["detail_failed"] += 1
                continue
            self.diagnostics["detail_full_text"] += 1
            candidates.append(Candidate(url=url, title=detail.clean_title or str(entry.get("title") or "").strip(),
                                        body=body, summary=detail.description,
                                        published_date=detail.published_date, language="en"))
            if len(candidates) >= self.max_items:
                break
        if not candidates and self.diagnostics["detail_failed"]:
            raise SourceFetchError("all_details_failed")
        return candidates
