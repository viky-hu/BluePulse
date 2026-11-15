"""Bounded HTML parsers for source-expansion experiments."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from .ccgp_source import USER_AGENT, _decode
from .live_sources import BoundedHTTP, SourceFetchError, listing_evidence, parse_time
from .pipeline import Candidate, canonical_url
from .source_listing import linked_pages


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
        self.dates: dict[str, str] = {}
        self.last_article: str | None = None
        self.card_date: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "time" and (raw_date := values.get("datetime")):
            if self.config.link_mode == "post_h2":
                self.card_date = raw_date
            elif self.last_article:
                self.dates.setdefault(self.last_article, raw_date)
                self.last_article = None
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
                self.last_article = self.anchor
                if self.card_date:
                    self.dates.setdefault(self.anchor, self.card_date)
                    self.card_date = None
            self.anchor = None
        if tag == self.heading:
            self.heading = None
            self.heading_classes = []
        if tag == "article":
            self.last_article = self.card_date = None


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
        if tag in VOID:
            return
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
    @property
    def listing_entries(self):
        return {"default": self.config.listing}

    def iter_entry_pages(self, entry, *, start=0):
        if entry != "default" or start < 0:
            raise SourceFetchError("invalid_listing_offset")
        for rows, following in self.iter_listing_pages(start=start):
            self.listing_page_evidence = listing_evidence(
                (row.published_at or row.published_date for row in rows), ordered=True,
                terminal="exhausted" if following is None else None)
            yield rows, following

    def __init__(self, http: BoundedHTTP, *, kind: str, max_items: int = 2,
                 sleeper=time.sleep):
        if kind not in SITES or not 1 <= max_items <= 5:
            raise ValueError("invalid_html_source_configuration")
        self.http, self.config, self.max_items, self.sleeper = http, SITES[kind], max_items, sleeper
        self.listing_newest_first = kind == "biometric"
        self._policy: RobotFileParser | None = None
        self._delay = 0.0
        self._reset_diagnostics()

    def _reset_diagnostics(self) -> None:
        self.diagnostics = {"robots_unavailable": 0, "listing_links": 0, "detail_attempts": 0,
                            "detail_full_text": 0, "detail_abstract_only": 0, "detail_failed": 0}

    def _load_robots(self) -> None:
        try:
            robots = self.http.get(f"https://{self.config.host}/robots.txt", accept="text/plain")
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
        self._policy, self._delay = policy, max(1.0, float(delay))

    def _fetch(self, url: str) -> str:
        if self._policy is None:
            self._load_robots()
        if not self._policy.can_fetch(USER_AGENT, url):
            raise SourceFetchError("robots_disallowed")
        if getattr(self.http.client, "pulse_host_pace", None):
            self.http.delay_seconds = max(self.http.delay_seconds, self._delay)
        else:
            self.sleeper(self._delay)
        return _decode(self.http.get(url, accept="text/html,application/xhtml+xml;q=0.9"))

    def _article_url(self, url: str) -> str | None:
        try:
            parts = urlsplit(url)
            if parts.query or parts.fragment or not self.config.article_path.fullmatch(parts.path):
                return None
            return canonical_url(url, [self.config.host])
        except ValueError:
            return None

    def _listing_candidates(self, html, page_url):
        config = self.config
        links = _ArticleLinks(config)
        links.feed(html)
        selected: dict[str, Candidate] = {}
        for raw_url, title in links.items:
            url = self._article_url(urljoin(page_url, raw_url))
            if url:
                raw = links.dates.get(raw_url, "")
                exact = parse_time(raw)
                try:
                    day = date.fromisoformat(raw) if not exact and len(raw) == 10 else None
                except ValueError:
                    day = None
                selected.setdefault(url, Candidate(url=url, title=title, language="en",
                                                   published_at=exact, published_date=day))
        self.diagnostics["listing_links"] += len(selected)
        return list(selected.values())

    def list_candidates(self, *, first_import: bool = False) -> list[Candidate]:
        self._reset_diagnostics()
        self._policy = None
        listing = self.config.listing
        items = self._listing_candidates(self._fetch(listing), listing)
        if not items:
            raise SourceFetchError("listing_links_missing")
        return items

    def iter_listing_pages(self, *, start=0):
        if self.config.link_mode == "h2":
            self._reset_diagnostics()
            self._policy = None
            listing = self.config.listing
            for items, offset in linked_pages(listing, self._fetch, self._listing_candidates,
                    lambda parts: not parts.query and re.fullmatch(
                        r"/biometric-news/law-enforcement/page/[1-9]\d*/?", parts.path), start=start):
                if not items:
                    raise SourceFetchError("listing_links_missing")
                yield items, offset
        elif self.config.link_mode == "post_h2":
            items = self.list_candidates()
            page, seen = 1, set()
            while items:
                signature = tuple(item.url for item in items)
                if signature in seen:
                    raise SourceFetchError("listing_pagination_stalled")
                seen.add(signature)
                if page > start:
                    yield items, page
                page += 1
                url = f"{self.config.listing}page/{page}/"
                try:
                    items = self._listing_candidates(self._fetch(url), url)
                except SourceFetchError as exc:
                    if exc.code != "http_404":
                        raise
                    break
            yield [], None
        else:
            yield self.list_candidates(), None

    def fetch_detail(self, candidate: Candidate) -> Candidate:
        if not self._article_url(candidate.url):
            raise SourceFetchError("invalid_article_url")
        self.diagnostics["detail_attempts"] += 1
        try:
            detail = _Detail(self.config)
            detail.feed(self._fetch(candidate.url))
            body = detail.body
            summary = (detail.description or "").strip()[:1000] or candidate.summary
            if len(body) >= 120:
                self.diagnostics["detail_full_text"] += 1
            elif summary:
                self.diagnostics["detail_abstract_only"] += 1
                body = ""
            else:
                raise SourceFetchError("incomplete_article")
        except SourceFetchError:
            self.diagnostics["detail_failed"] += 1
            raise
        return replace(candidate, title=detail.title or candidate.title,
                       body=body or candidate.body, summary=summary,
                       published_at=detail.published_at or candidate.published_at,
                       published_date=detail.published_date or candidate.published_date)

    def candidates(self) -> list[Candidate]:
        candidates: list[Candidate] = []
        for listed in self.list_candidates()[:self.max_items]:
            try:
                candidates.append(self.fetch_detail(listed))
            except SourceFetchError as exc:
                if exc.code in {"http_403", "http_429", "robots_disallowed"}:
                    raise
        if not candidates and self.diagnostics["detail_failed"]:
            raise SourceFetchError("all_details_failed")
        return candidates
