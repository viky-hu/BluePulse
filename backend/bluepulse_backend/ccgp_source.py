"""Bounded CCGP listing/detail collection. Analysis belongs to the pipeline."""
from __future__ import annotations

import re
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from .live_sources import BoundedHTTP, SourceFetchError, plain_text
from .pipeline import Candidate
from .source_listing import linked_pages


HOST = "www.ccgp.gov.cn"
LISTING = "https://www.ccgp.gov.cn/cggg/zygg/gkzb/"
LOCAL_LISTING = "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/"
USER_AGENT = "BluePulseResearch/0.1"
ARTICLE_PATH = re.compile(r"^/cggg/(?:zygg|dfgg)/gkzb/\d{6}/t\d{8}_\d+\.htm$")
PAGER = re.compile(r"Pager\(\{\s*size:\s*(\d+),\s*current:\s*(\d+),\s*prefix:\s*'index',\s*suffix:\s*'htm'\s*\}\)")
DATE = re.compile(r"(?<!\d)(20\d{2})(?:年|-)[ \t]*(\d{1,2})(?:月|-)[ \t]*(\d{1,2})(?:日\s*|\s+)(\d{1,2}):(\d{2})")
POLICE = ("公安", "警务", "交警", "刑侦", "治安", "边境管理", "警察", "公共安全")
TECH = ("人工智能", "大模型", "智能", "信息化", "视频", "监控", "数据", "网络", "软件",
        "平台", "系统", "通信", "无人机", "机器人", "电子物证", "科技", "vpn")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "wbr"}


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _valid_article_url(raw: str, base: str = LISTING) -> str | None:
    url = urljoin(base, raw)
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != HOST or parts.port not in (None, 443)
            or parts.username or parts.password or parts.query or parts.fragment
            or not ARTICLE_PATH.fullmatch(parts.path)):
        return None
    return url


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, str, str]] = []
        self.li_text: list[str] | None = None
        self.li_links: list[tuple[str, str]] = []
        self.anchor_url: str | None = None
        self.anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "li":
            self.li_text, self.li_links = [], []
        if tag == "a":
            self.anchor_url = dict(attrs).get("href")
            self.anchor_text = []

    def handle_data(self, data: str) -> None:
        if self.li_text is not None:
            self.li_text.append(data)
        if self.anchor_url is not None:
            self.anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.anchor_url is not None:
            title = " ".join("".join(self.anchor_text).split())
            if title:
                if self.li_text is None:
                    self.items.append((self.anchor_url, title, title))
                else:
                    self.li_links.append((self.anchor_url, title))
            self.anchor_url, self.anchor_text = None, []
        if tag == "li" and self.li_text is not None:
            context = " ".join("".join(self.li_text).split())[:500]
            self.items.extend((url, title, context) for url, title in self.li_links)
            self.li_text, self.li_links = None, []


class _Detail(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.done = False
        self.skip = 0
        self.parts: list[str] = []
        self.heading_depth = 0
        self.heading: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if not self.done and self.depth == 0 and (
            "vF_detail_content" in (attrs_map.get("class") or "").split()
            or attrs_map.get("id") in {"mycontent", "content", "Zoom"}
            or tag == "article"
        ):
            self.depth = 1
            return
        if self.depth:
            if tag not in VOID:
                self.depth += 1
            if tag in {"script", "style", "noscript", "nav", "footer", "form"}:
                self.skip += 1
            if tag in {"p", "br", "li", "h2", "h3", "div"}:
                self.parts.append("\n")
        elif not self.heading and tag in {"h1", "h2"}:
            self.heading_depth = 1
        elif self.heading_depth and tag not in VOID:
            self.heading_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self.depth:
            if tag in {"script", "style", "noscript", "nav", "footer", "form"} and self.skip:
                self.skip -= 1
            if tag in {"p", "li", "h2", "h3", "div"}:
                self.parts.append("\n")
            self.depth -= 1
            if self.depth == 0:
                self.done = True
        elif self.heading_depth:
            self.heading_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth and not self.skip:
            self.parts.append(data)
        elif self.heading_depth:
            self.heading.append(data)


def _published_at(text: str) -> datetime | None:
    match = DATE.search(text)
    if not match:
        return None
    try:
        return datetime(*map(int, match.groups()), tzinfo=timezone(timedelta(hours=8))).astimezone(UTC)
    except ValueError:
        return None


def _rank(context: str) -> int:
    police = any(word in context for word in POLICE)
    normalized = context.casefold()
    tech = any(word in normalized for word in TECH)
    return 0 if police and tech else 1 if police else 2 if tech else 3


class CcgpAdapter:
    def __init__(self, http: BoundedHTTP, *, max_items: int = 2,
                 request_delay_seconds: float = 1.0, sleeper: Callable[[float], None] = time.sleep):
        if not 1 <= max_items <= 5:
            raise ValueError("max_items_must_be_1_to_5")
        if request_delay_seconds < 0:
            raise ValueError("invalid_request_delay")
        self.http = http
        self.max_items = max_items
        self.request_delay_seconds = request_delay_seconds
        self.sleeper = sleeper
        self._policy: RobotFileParser | None = None
        self._delay = 0.0
        self._reset_diagnostics()

    def _reset_diagnostics(self) -> None:
        self.diagnostics = {"robots_unavailable": 0, "listing_links": 0, "topic_filtered": 0,
                            "detail_attempts": 0, "detail_parsed": 0,
                            "detail_failed": 0, "detail_skipped": 0}

    def _load_robots(self) -> None:
        try:
            robots = self.http.get(f"https://{HOST}/robots.txt", accept="text/plain")
        except SourceFetchError as exc:
            if exc.code != "http_404":
                raise
            # RFC 9309 treats a 4xx robots response as unavailable. Other errors fail closed.
            robots = b""
            self.diagnostics["robots_unavailable"] = 1
        policy = RobotFileParser()
        policy.parse(_decode(robots).splitlines())
        crawl_delay = policy.crawl_delay(USER_AGENT) or 0
        if crawl_delay > 10:
            raise SourceFetchError("robots_delay_exceeds_budget")
        self._policy, self._delay = policy, max(self.request_delay_seconds, float(crawl_delay))

    def _fetch(self, url: str) -> bytes:
        if self._policy is None:
            self._load_robots()
        if not self._policy.can_fetch(USER_AGENT, url):
            raise SourceFetchError("robots_disallowed")
        if getattr(self.http.client, "pulse_host_pace", None):
            self.http.delay_seconds = max(self.http.delay_seconds, self._delay)
        else:
            self.sleeper(self._delay)
        return self.http.get(url, accept="text/html,application/xhtml+xml;q=0.9")

    def _listing_candidates(self, html, page_url):
        links = _Links()
        links.feed(html)
        unique: dict[str, tuple[str, str]] = {}
        for raw_url, title, context in links.items:
            url = _valid_article_url(raw_url, page_url)
            if url and url not in unique:
                unique[url] = (title, context)
        self.diagnostics["listing_links"] += len(unique)
        if not unique:
            raise SourceFetchError("listing_no_article_links")
        # A broad technology word alone produced unrelated university and industry tenders.
        # Keep only listings that identify both a policing buyer/task and a technology.
        ranked = [item for item in unique.items() if _rank(" ".join(item[1])) == 0]
        self.diagnostics["topic_filtered"] += len(unique) - len(ranked)
        return [Candidate(url=url, title=title, published_at=_published_at(context), language="zh")
                for url, (title, context) in ranked]

    def list_candidates(self, *, first_import: bool = False) -> list[Candidate]:
        self._reset_diagnostics()
        self._policy = None
        return self._listing_candidates(_decode(self._fetch(LISTING)), LISTING)

    def iter_listing_pages(self, *, start=0):
        self._reset_diagnostics()
        self._policy = None

        def pager_links(html):
            if pager := PAGER.search(html):
                size, current = map(int, pager.groups())
                if current + 1 < size:
                    yield f"index_{current + 1}.htm"

        index = 0
        for entry in (LISTING, LOCAL_LISTING):
            archive = urlsplit(entry).path
            pages = linked_pages(entry, lambda url: _decode(self._fetch(url)), self._listing_candidates,
                                 lambda parts: not parts.query and re.fullmatch(
                                     re.escape(archive) + r"index_[1-9]\d*\.htm", parts.path),
                                 extra_links=pager_links)
            for items, following in pages:
                if index >= start:
                    checkpoint = index + 1 if following is not None or entry == LISTING else None
                    yield items, checkpoint
                index += 1

    def fetch_detail(self, candidate: Candidate) -> Candidate:
        if not _valid_article_url(candidate.url):
            raise SourceFetchError("invalid_article_url")
        self.diagnostics["detail_attempts"] += 1
        try:
            html = _decode(self._fetch(candidate.url))
            detail = _Detail()
            detail.feed(html)
            body = "\n".join(line.strip() for line in "".join(detail.parts).splitlines() if line.strip())[:12000]
            if len(body) < 100:
                raise SourceFetchError("incomplete_article")
        except SourceFetchError:
            self.diagnostics["detail_failed"] += 1
            raise
        self.diagnostics["detail_parsed"] += 1
        title = " ".join("".join(detail.heading).split())[:500] or candidate.title
        return replace(candidate, title=title, body=body,
                       published_at=_published_at(plain_text(html, max_chars=3000)) or candidate.published_at)

    def candidates(self) -> list[Candidate]:
        results: list[Candidate] = []
        for listed in self.list_candidates()[:self.max_items * 3]:
            if len(results) >= self.max_items:
                break
            try:
                results.append(self.fetch_detail(listed))
            except SourceFetchError as exc:
                if exc.code in {"http_403", "http_429", "robots_disallowed"}:
                    raise
        self.diagnostics["detail_skipped"] = self.diagnostics["listing_links"] - self.diagnostics["detail_attempts"]
        if not results and self.diagnostics["detail_failed"]:
            raise SourceFetchError("detail_parse_or_fetch_failed")
        return results
