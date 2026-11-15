"""Bounded Europol newsroom RSS and official article data extraction."""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import urlsplit

from .live_sources import BoundedHTTP, SourceFetchError, listing_evidence, parse_time, plain_text
from .pipeline import Candidate, canonical_url
from .source_page import IncompleteArticle, SourcePageReader, bounded_details


HOST = "www.europol.europa.eu"
ROOT = f"https://{HOST}"
FEED = ROOT + "/cms/api/rss/news"
NEWSROOM = ROOT + "/media-press/newsroom"
ARTICLE_PATH = re.compile(r"/media-press/newsroom/news/[a-z0-9-]+")
TOPIC = re.compile(
    r"\b(?:AI|digital|cyber|forensic|innovation|technology|quantum|drone|surveillance|"
    r"biometric|data|hackathon|software|online|crypto|e-evidence)\b",
    re.I,
)
DATA_MARKER = "window.SERVER_DATA="


def _page_node(html: str, kind: str) -> dict:
    start = html.find(DATA_MARKER)
    if start < 0:
        raise SourceFetchError(kind + "_data_missing")
    start += len(DATA_MARKER)
    end = html.find(";</script>", start)
    if end < 0 or end - start > 1_000_000:
        raise SourceFetchError(kind + "_data_invalid")
    try:
        node = json.loads(html[start:end])["NodeLoader"]["node"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SourceFetchError(kind + "_data_invalid") from exc
    if not isinstance(node, dict):
        raise SourceFetchError(kind + "_data_invalid")
    return node


def _published(value):
    try:
        return datetime.fromtimestamp(int(value), tz=UTC) if value is not None else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def parse_article_html(html: str, url: str) -> tuple[str, str, datetime | None, str | None]:
    node = _page_node(html, "detail")
    if not isinstance(node, dict) or node.get("alias") != urlsplit(url).path:
        raise SourceFetchError("detail_alias_mismatch")
    title = plain_text(str(node.get("title") or ""), max_chars=500)
    introduction = node.get("introduction") or ""
    body_html = node.get("body") or ""
    if not isinstance(introduction, str) or not isinstance(body_html, str):
        raise SourceFetchError("detail_body_invalid")
    body = plain_text(introduction + "\n" + body_html, max_chars=100_000)
    published_at = _published(node.get("published"))
    summary = plain_text(str(node.get("summary") or ""), max_chars=1000) or None
    return title, body, published_at, summary


class EuropolNewsAdapter:
    listing_entries = {"newsroom": NEWSROOM}

    def __init__(self, http: BoundedHTTP, *, max_items: int = 2, sleeper=time.sleep):
        if not 1 <= max_items <= 5 or http.allowed_hosts != {HOST}:
            raise ValueError("invalid_europol_configuration")
        self.http, self.max_items, self.sleeper = http, max_items, sleeper
        self.reader = SourcePageReader(http, FEED, lambda delay: self.sleeper(delay))
        self.diagnostics: dict[str, int] = {}
        self.item_diagnostics: list[dict] = []

    def list_candidates(self, *, first_import: bool = False) -> list[Candidate]:
        self.diagnostics = {"feed_items": 0, "topic_matches": 0, "detail_attempts": 0,
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
        for item in items:
            url = (item.findtext("link") or "").strip()
            if not self._valid_article(url):
                continue
            title = item.findtext("title") or ""
            summary = item.findtext("description") or ""
            if not TOPIC.search(f"{title} {summary}"):
                continue
            self.diagnostics["topic_matches"] += 1
            candidates.append(Candidate(url=url, title=plain_text(title, max_chars=500),
                                        summary=plain_text(summary, max_chars=1000) or None,
                                        published_at=parse_time(item.findtext("pubDate")), language="en"))
        return candidates

    def iter_entry_pages(self, entry: str, *, start=0):
        if entry != "newsroom" or start < 0:
            raise SourceFetchError("invalid_listing_offset")
        page = start + 1
        while True:
            url = NEWSROOM if page == 1 else f"{NEWSROOM}?page={page}"
            html = self.reader.get(url, "text/html").decode("utf-8-sig", "replace")
            try:
                lists = _page_node(html, "listing")["lists"]
                archive = next(row for row in lists if row["id"] == "news")
                rows, returned_page = archive["items"], archive["page"]
                total, page_size = archive["totalItems"], archive["itemsPerPage"]
                if (not isinstance(rows, list) or returned_page != page or type(total) is not int
                        or type(page_size) is not int or page_size <= 0 or total < 0):
                    raise ValueError()
            except (KeyError, StopIteration, TypeError, ValueError) as exc:
                raise SourceFetchError("invalid_listing_payload") from exc
            following = page if page * page_size < total else None
            expected = min(page_size, max(0, total - (page - 1) * page_size))
            if len(rows) != expected:
                raise SourceFetchError("listing_pagination_stalled")
            candidates, dates = [], []
            for row in rows:
                if not isinstance(row, dict):
                    raise SourceFetchError("invalid_listing_payload")
                published = _published(row.get("published"))
                dates.append(published)
                alias = row.get("alias")
                if not isinstance(alias, str) or not ARTICLE_PATH.fullmatch(alias):
                    continue
                title = plain_text(str(row.get("title") or ""), max_chars=500)
                candidates.append(Candidate(url=ROOT + alias, title=title, published_at=published, language="en"))
            self.listing_page_evidence = listing_evidence(
                dates, ordered=True, terminal="exhausted" if following is None else None)
            yield candidates, following
            if following is None:
                return
            page += 1

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
        try:
            title, body, published_at, summary = parse_article_html(
                self.reader.get(url, "text/html").decode("utf-8-sig"), url)
        except UnicodeDecodeError as exc:
            raise SourceFetchError("decode_error") from exc
        published_at = published_at or candidate.published_at
        if not title or len(body) < 120 or published_at is None:
            raise IncompleteArticle(len(body))
        self.diagnostics["detail_full_text"] = self.diagnostics.get("detail_full_text", 0) + 1
        self.item_diagnostics.append({"url": url, "status": "full_text", "body_chars": len(body)})
        return replace(candidate, title=title, body=body, summary=summary or candidate.summary,
                       published_at=published_at)

    def candidates(self) -> list[Candidate]:
        rows = self.list_candidates()[:self.max_items]
        return bounded_details(rows, self.fetch_detail, self.diagnostics, self.item_diagnostics)
