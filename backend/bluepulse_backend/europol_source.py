"""Bounded Europol newsroom RSS and official article data extraction."""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from .ccgp_source import USER_AGENT
from .live_sources import BoundedHTTP, SourceFetchError, plain_text
from .pipeline import Candidate, canonical_url


HOST = "www.europol.europa.eu"
ROOT = f"https://{HOST}"
FEED = ROOT + "/cms/api/rss/news"
ARTICLE_PATH = re.compile(r"/media-press/newsroom/news/[a-z0-9-]+")
TOPIC = re.compile(
    r"\b(?:AI|digital|cyber|forensic|innovation|technology|quantum|drone|surveillance|"
    r"biometric|data|hackathon|software|online|crypto|e-evidence)\b",
    re.I,
)
DATA_MARKER = "window.SERVER_DATA="


def parse_article_html(html: str, url: str) -> tuple[str, str, datetime | None, str | None]:
    start = html.find(DATA_MARKER)
    if start < 0:
        raise SourceFetchError("detail_data_missing")
    start += len(DATA_MARKER)
    end = html.find(";</script>", start)
    if end < 0 or end - start > 1_000_000:
        raise SourceFetchError("detail_data_invalid")
    try:
        node = json.loads(html[start:end])["NodeLoader"]["node"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SourceFetchError("detail_data_invalid") from exc
    if not isinstance(node, dict) or node.get("alias") != urlsplit(url).path:
        raise SourceFetchError("detail_alias_mismatch")
    title = plain_text(str(node.get("title") or ""), max_chars=500)
    introduction = node.get("introduction") or ""
    body_html = node.get("body") or ""
    if not isinstance(introduction, str) or not isinstance(body_html, str):
        raise SourceFetchError("detail_body_invalid")
    body = plain_text(introduction + "\n" + body_html, max_chars=100_000)
    published = node.get("published")
    try:
        published_at = datetime.fromtimestamp(int(published), tz=UTC) if published is not None else None
    except (ValueError, TypeError, OverflowError):
        published_at = None
    summary = plain_text(str(node.get("summary") or ""), max_chars=1000) or None
    return title, body, published_at, summary


class EuropolNewsAdapter:
    def __init__(self, http: BoundedHTTP, *, max_items: int = 2, sleeper=time.sleep):
        if not 1 <= max_items <= 5 or http.allowed_hosts != {HOST}:
            raise ValueError("invalid_europol_configuration")
        self.http, self.max_items, self.sleeper = http, max_items, sleeper
        self.diagnostics: dict[str, int] = {}
        self.item_diagnostics: list[dict] = []

    def candidates(self) -> list[Candidate]:
        self.diagnostics = {"feed_items": 0, "topic_matches": 0, "detail_attempts": 0,
                            "detail_full_text": 0, "detail_failed": 0}
        self.item_diagnostics = []
        robots = self.http.get(ROOT + "/robots.txt", accept="text/plain")
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
        for item in items:
            url = (item.findtext("link") or "").strip()
            parts = urlsplit(url)
            if (parts.scheme != "https" or parts.hostname != HOST or parts.query or parts.fragment or
                    not ARTICLE_PATH.fullmatch(parts.path)):
                continue
            try:
                canonical_url(url, [HOST])
            except ValueError:
                continue
            if not TOPIC.search(" ".join((item.findtext("title") or "", item.findtext("description") or ""))):
                continue
            self.diagnostics["topic_matches"] += 1
            if self.diagnostics["detail_attempts"] >= self.max_items:
                continue
            self.diagnostics["detail_attempts"] += 1
            try:
                title, body, published_at, summary = parse_article_html(
                    fetch(url, "text/html").decode("utf-8-sig"), url)
            except (SourceFetchError, UnicodeDecodeError) as exc:
                if isinstance(exc, SourceFetchError) and exc.code in {"http_403", "http_429", "robots_disallowed"}:
                    raise
                self.diagnostics["detail_failed"] += 1
                self.item_diagnostics.append({"url": url, "status": getattr(exc, "code", "decode_error")})
                continue
            if not title or len(body) < 120 or published_at is None:
                self.diagnostics["detail_failed"] += 1
                self.item_diagnostics.append({"url": url, "status": "incomplete_article",
                                              "body_chars": len(body)})
                continue
            self.diagnostics["detail_full_text"] += 1
            self.item_diagnostics.append({"url": url, "status": "full_text", "body_chars": len(body)})
            candidates.append(Candidate(url=url, title=title, body=body, summary=summary,
                                        published_at=published_at, language="en"))
        if not candidates and self.diagnostics["detail_failed"]:
            raise SourceFetchError("all_details_failed")
        return candidates
