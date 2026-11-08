"""Bounded HTX News discovery through the public listing endpoint used by its site."""
from __future__ import annotations

import json
import re
import time
from dataclasses import replace
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from .ccgp_source import USER_AGENT
from .live_sources import BoundedHTTP, SourceFetchError
from .pipeline import Candidate, canonical_url
from .source_images import ArticleImages


HOST = "www.htx.gov.sg"
ROOT = f"https://{HOST}"
LISTING = ROOT + "/HTXInterface/ArticleListing/GetNewsAndEventsListing"
ARTICLE_PATH = re.compile(r"/whats-happening/all-news---events/all-news/20\d{2}/[a-z0-9-]+")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "wbr"}
SKIP = {"script", "style", "noscript", "nav", "footer", "form", "aside"}


def _date(raw: object) -> date | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw.strip(), "%d %B %Y").date()
    except ValueError:
        return None


def _article_url(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        if parts.query or parts.fragment or not ARTICLE_PATH.fullmatch(parts.path):
            return None
        return canonical_url(url, [HOST])
    except ValueError:
        return None


class _Article(HTMLParser):
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, set[str]]] = []
        self.title: list[str] = []
        self.body: list[str] = []
        self.description: str | None = None
        self.date: list[str] = []
        self.images = ArticleImages(url, HOST)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta" and values.get("property") == "og:description":
            self.description = values.get("content")
        if (tag == "img" and self._in("detail__content") and self._in("rte") and
                not any(parent in SKIP for parent, _ in self.stack)):
            self.images.add(values)
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
        return _date(raw)


class HtxNewsAdapter:
    def __init__(self, http: BoundedHTTP, *, max_items: int = 2, sleeper=time.sleep):
        if not 1 <= max_items <= 5:
            raise ValueError("max_items_must_be_1_to_5")
        self.http, self.max_items, self.sleeper = http, max_items, sleeper
        self._policy: RobotFileParser | None = None
        self._delay = 0.0
        self._reset_diagnostics()

    def _reset_diagnostics(self) -> None:
        self.diagnostics = {"listing_items": 0, "detail_attempts": 0,
                            "detail_full_text": 0, "detail_failed": 0}

    def _load_robots(self) -> None:
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
        self._policy, self._delay = policy, max(1.0, float(delay))

    def _fetch(self, url: str, *, params: dict | None = None, accept: str = "text/html") -> bytes:
        if self._policy is None:
            self._load_robots()
        if not self._policy.can_fetch(USER_AGENT, url):
            raise SourceFetchError("robots_disallowed")
        if getattr(self.http.client, "pulse_host_pace", None):
            self.http.delay_seconds = max(self.http.delay_seconds, self._delay)
        else:
            self.sleeper(self._delay)
        return self.http.get(url, params=params, accept=accept)

    def _listing_page(self, page: int) -> tuple[list, int | None]:
        raw = self._fetch(LISTING, params={"type": "News", "keyword": "", "topic": "all",
                                           "dateFrom": "", "dateTo": "", "page": page},
                          accept="application/json")
        try:
            payload = json.loads(raw)
            entries = payload["data"]
            if not isinstance(entries, list):
                raise ValueError()
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceFetchError("invalid_listing_payload") from exc
        total = payload.get("totalItems")
        return entries, total if type(total) is int and total >= 0 else None

    @staticmethod
    def _listed_candidates(entries: list) -> list[Candidate]:
        candidates = {}
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("articleType") != "News":
                continue
            path = entry.get("url")
            if not isinstance(path, str) or not ARTICLE_PATH.fullmatch(path):
                continue
            url = _article_url(urljoin(ROOT, path))
            if not url:
                continue
            title = entry.get("title")
            candidates.setdefault(url, Candidate(
                url=url, title=title.strip() if isinstance(title, str) else "",
                published_date=_date(entry.get("date")), language="en",
            ))
        return list(candidates.values())

    def iter_listing_pages(self, *, start: int = 0):
        """Yield listing pages with a restartable zero-based page cursor."""
        self._reset_diagnostics()
        self._policy = None
        entries, total = self._listing_page(1)
        page_size = len(entries)
        page = start + 1
        if start and not page_size:
            yield [], None
            return
        if start:
            entries, total = self._listing_page(page)
        seen_pages = set()
        while True:
            self.diagnostics["listing_items"] += len(entries)
            next_page = page if total is not None and (page - 1) * page_size + len(entries) < total else None
            signature = tuple(entry.get("url") for entry in entries
                              if isinstance(entry, dict) and isinstance(entry.get("url"), str))
            if next_page is not None and not entries or signature in seen_pages:
                raise SourceFetchError("listing_pagination_stalled")
            seen_pages.add(signature)
            yield self._listed_candidates(entries), next_page
            if next_page is None:
                return
            page += 1
            entries, total = self._listing_page(page)

    def list_candidates(self, *, first_import: bool = False) -> list[Candidate]:
        candidates = {}
        for page, _ in self.iter_listing_pages():
            for candidate in page:
                candidates.setdefault(candidate.url, candidate)
        return list(candidates.values())

    def fetch_detail(self, candidate: Candidate) -> Candidate:
        url = candidate.url
        if not _article_url(url):
            raise SourceFetchError("invalid_article_url")
        self.diagnostics["detail_attempts"] += 1
        try:
            detail = _Article(url)
            detail.feed(self._fetch(url).decode("utf-8"))
            body = detail.clean_body
            title = detail.clean_title or candidate.title
            if len(body) < 120 or not title:
                raise SourceFetchError("incomplete_article")
        except (SourceFetchError, UnicodeDecodeError) as exc:
            self.diagnostics["detail_failed"] += 1
            if isinstance(exc, UnicodeDecodeError):
                raise SourceFetchError("decode_error") from exc
            raise
        self.diagnostics["detail_full_text"] += 1
        return replace(candidate, title=title, body=body, summary=detail.description or candidate.summary,
                       published_date=detail.published_date or candidate.published_date,
                       media=detail.images.permitted(self._policy, USER_AGENT) or candidate.media)

    def candidates(self) -> list[Candidate]:
        candidates = []
        listed, _ = next(self.iter_listing_pages())
        for candidate in listed:
            try:
                candidates.append(self.fetch_detail(candidate))
            except SourceFetchError as exc:
                if exc.code in {"http_403", "http_429", "robots_disallowed"}:
                    raise
            if len(candidates) >= self.max_items:
                break
        if not candidates and self.diagnostics["detail_failed"]:
            raise SourceFetchError("all_details_failed")
        return candidates
