"""Bounded HTML parsers for source-expansion experiments."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from .ccgp_source import USER_AGENT, _decode
from .live_sources import BoundedHTTP, SourceFetchError
from .pipeline import Candidate, canonical_url


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "wbr"}
SKIP = {"script", "style", "noscript", "nav", "footer", "form", "aside"}


@dataclass(frozen=True)
class HtmlSourceConfig:
    host: str
    listing: str
    article_path: re.Pattern[str]
    body_class: str
    link_mode: str
    date_mode: str


SITES = {
    "pds": HtmlSourceConfig(
        "pds.police.uk", "https://pds.police.uk/welcome/blog/",
        re.compile(r"/[a-z0-9-]+/"), "entry-content", "post_h2", "time"),
    "biometric": HtmlSourceConfig(
        "www.biometricupdate.com", "https://www.biometricupdate.com/biometric-news/law-enforcement",
        re.compile(r"/20\d{4}/[a-z0-9-]+"), "thecontent", "h2", "meta"),
    "nij": HtmlSourceConfig(
        # Kept to reproduce the isolated pilot; not registered as an active source.
        "nij.ojp.gov", "https://nij.ojp.gov/topics/equipment-and-technology",
        re.compile(r"/topics/articles/[a-z0-9-]+"), "field--name-body", "all", "field"),
}


class _ArticleLinks(HTMLParser):
    def __init__(self, config: HtmlSourceConfig):
        super().__init__(convert_charrefs=True)
        self.config = config
        self.heading: str | None = None
        self.heading_classes: list[str] = []
        self.anchor: str | None = None
        self.words: list[str] = []
        self.items: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in {"h2", "h3"}:
            self.heading = tag
            self.heading_classes = (values.get("class") or "").split()
        if tag == "a":
            allowed = (self.config.link_mode == "all" or
                       self.heading == "h2" and self.config.link_mode == "h2" or
                       self.heading == "h2" and self.config.link_mode == "post_h2" and
                       "post-title" in self.heading_classes)
            self.anchor = values.get("href") if allowed else None
            self.words = []

    def handle_data(self, data: str) -> None:
        if self.anchor:
            self.words.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.anchor:
            title = " ".join("".join(self.words).split())
            if title:
                self.items.append((self.anchor, title))
            self.anchor = None
        if tag == self.heading:
            self.heading = None
            self.heading_classes = []


class _Detail(HTMLParser):
    def __init__(self, config: HtmlSourceConfig):
        super().__init__(convert_charrefs=True)
        self.config = config
        self.body_depth = 0
        self.body_seen = False
        self.body_stopped = False
        self.title_depth = 0
        self.date_depth = 0
        self.skip_depth = 0
        self.body_parts: list[str] = []
        self.title_parts: list[str] = []
        self.date_parts: list[str] = []
        self.raw_date: str | None = None
        self.description: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        if tag == "meta":
            if values.get("property") == "article:published_time":
                self.raw_date = values.get("content")
            if values.get("name") == "description":
                self.description = values.get("content")
        if tag == "time" and not self.raw_date and values.get("datetime"):
            self.raw_date = values["datetime"]
        if tag in SKIP or self.skip_depth:
            if tag not in VOID:
                self.skip_depth += 1
            return
        if self.body_depth:
            if self.config.link_mode == "h2" and "rp4wp-related-posts" in classes:
                self.body_stopped = True
            if tag not in VOID:
                self.body_depth += 1
            if not self.body_stopped and tag in {"p", "li", "h2", "h3", "br"}:
                self.body_parts.append("\n")
        elif not self.body_seen and self.config.body_class in classes:
            self.body_depth = 1
            self.body_seen = True
        if tag == "h1" and not self.title_parts:
            self.title_depth = 1
        elif self.title_depth and tag not in VOID:
            self.title_depth += 1
        if self.config.date_mode == "field" and "field--name-field-date-published" in classes:
            self.date_depth = 1
        elif self.date_depth and tag not in VOID:
            self.date_depth += 1

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.body_depth and not self.body_stopped:
            self.body_parts.append(data)
        if self.title_depth:
            self.title_parts.append(data)
        if self.date_depth:
            self.date_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if self.body_depth:
            if not self.body_stopped and tag in {"p", "li", "h2", "h3"}:
                self.body_parts.append("\n")
            self.body_depth -= 1
        if self.title_depth:
            self.title_depth -= 1
        if self.date_depth:
            self.date_depth -= 1

    @property
    def body(self) -> str:
        return "\n".join(" ".join(line.split()) for line in "".join(self.body_parts).splitlines()
                         if line.strip())[:100000]

    @property
    def title(self) -> str:
        return " ".join("".join(self.title_parts).split())[:500]

    @property
    def published_at(self) -> datetime | None:
        raw = self.raw_date or " ".join("".join(self.date_parts).split()).replace("Date Published", "").strip()
        if not raw:
            return None
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) or self.config.date_mode == "field":
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            try:
                return datetime.strptime(raw, "%B %d, %Y").replace(tzinfo=UTC)
            except ValueError:
                return None

    @property
    def published_date(self) -> date | None:
        raw = self.raw_date or " ".join("".join(self.date_parts).split()).replace("Date Published", "").strip()
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                return date.fromisoformat(raw)
            if self.config.date_mode == "field":
                return datetime.strptime(raw, "%B %d, %Y").date()
        except ValueError:
            pass
        return None


class BoundedHtmlSourceAdapter:
    def __init__(self, http: BoundedHTTP, *, kind: str, max_items: int = 2,
                 sleeper=time.sleep):
        if kind not in SITES or not 1 <= max_items <= 5:
            raise ValueError("invalid_html_source_configuration")
        self.http, self.config, self.max_items, self.sleeper = http, SITES[kind], max_items, sleeper
        self.diagnostics: dict[str, int] = {}

    def candidates(self) -> list[Candidate]:
        config = self.config
        self.diagnostics = {"robots_unavailable": 0, "listing_links": 0, "detail_attempts": 0,
                            "detail_full_text": 0, "detail_abstract_only": 0, "detail_failed": 0}
        try:
            robots = self.http.get(f"https://{config.host}/robots.txt", accept="text/plain")
        except SourceFetchError as exc:
            if exc.code != "http_404":
                raise
            robots = b""
            self.diagnostics["robots_unavailable"] = 1
        policy = RobotFileParser()
        policy.parse(_decode(robots).splitlines())
        delay = policy.crawl_delay(USER_AGENT) or 0
        if delay > 10:
            raise SourceFetchError("robots_delay_exceeds_budget")

        def fetch(url: str) -> str:
            if not policy.can_fetch(USER_AGENT, url):
                raise SourceFetchError("robots_disallowed")
            self.sleeper(max(1.0, float(delay)))
            return _decode(self.http.get(url, accept="text/html,application/xhtml+xml;q=0.9"))

        links = _ArticleLinks(config)
        links.feed(fetch(config.listing))
        selected: dict[str, str] = {}
        for raw_url, title in links.items:
            url = urljoin(config.listing, raw_url)
            parts = urlsplit(url)
            if parts.query or parts.fragment or not config.article_path.fullmatch(parts.path):
                continue
            try:
                canonical_url(url, [config.host])
            except ValueError:
                continue
            selected.setdefault(url, title)
        self.diagnostics["listing_links"] = len(selected)
        if not selected:
            raise SourceFetchError("listing_links_missing")
        candidates: list[Candidate] = []
        for url, listed_title in list(selected.items())[:self.max_items]:
            self.diagnostics["detail_attempts"] += 1
            try:
                detail = _Detail(config)
                detail.feed(fetch(url))
            except SourceFetchError as exc:
                if exc.code in {"http_403", "http_429", "robots_disallowed"}:
                    raise
                self.diagnostics["detail_failed"] += 1
                continue
            body = detail.body
            summary = (detail.description or "").strip()[:1000] or None
            if len(body) >= 120:
                self.diagnostics["detail_full_text"] += 1
            elif summary:
                self.diagnostics["detail_abstract_only"] += 1
                body = ""
            else:
                self.diagnostics["detail_failed"] += 1
                continue
            candidates.append(Candidate(url=url, title=detail.title or listed_title,
                                        body=body or None, summary=summary,
                                        published_at=detail.published_at,
                                        published_date=detail.published_date, language="en"))
        if not candidates and self.diagnostics["detail_failed"]:
            raise SourceFetchError("all_details_failed")
        return candidates
