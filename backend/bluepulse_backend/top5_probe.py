"""Read-only, bounded evidence probes for the first five public sources."""
from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx

from .ccgp_source import CcgpAdapter, USER_AGENT, _Links, _decode
from .live_sources import BoundedHTTP, GovUkAdapter, NistRssAdapter, SourceFetchError, listing_evidence
from .pipeline import Candidate
from .source_listing import linked_pages
from .source_page import IncompleteArticle, SourcePageReader, bounded_details


NPCC_LIST = "https://news.npcc.police.uk/releases"
JIANGSU_LIST = "https://gat.jiangsu.gov.cn/col/col6372/index.html"
JIANGSU_RECORD = re.compile(r"<record>\s*<!\[CDATA\[(.*?)\]\]>\s*</record>", re.I | re.S)
JIANGSU_NEXT = re.compile(r'<nextgroup>\s*<!\[CDATA\[\s*<a href="([^"]+)"', re.I)
JIANGSU_DAY = re.compile(r"(?<!\d)20\d{2}-\d{2}-\d{2}(?!\d)")
NPCC_DAY = re.compile(r"(?<!\d)\d{1,2} [A-Z][a-z]{2} 20\d{2}(?!\d)")
JIANGSU_ARTICLE = re.compile(r"/art/\d{4}/\d{1,2}/\d{1,2}/art_6372_\d+\.html")
NPCC_ARTICLE = re.compile(r"/releases/[a-z0-9-]+")
TECH = re.compile(r"人工智能|大模型|智能|数智|无人机|机器人|科技|数字|算法|数据|视频|信息化|AI|drone|facial|digital|technology|cyber", re.I)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "wbr"}


class _Region(HTMLParser):
    def __init__(self, *, body_class: str, title_class: str, date_class: str | None = None):
        super().__init__(convert_charrefs=True)
        self.classes = {"body": body_class, "title": title_class, "date": date_class}
        self.depth = {key: 0 for key in self.classes}
        self.parts: dict[str, list[str]] = {key: [] for key in self.classes}
        self.skip = 0
        self.pubdate: str | None = None
        self.content_source: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        if tag == "meta" and data.get("name", "").lower() == "pubdate":
            self.pubdate = data.get("content")
        if tag == "meta" and data.get("name", "").lower() == "contentsource":
            self.content_source = data.get("content")
        if tag in {"script", "style", "noscript", "nav", "footer", "form"}:
            self.skip += 1
        classes = (data.get("class") or "").split()
        for key, target in self.classes.items():
            if self.depth[key]:
                if tag not in VOID:
                    self.depth[key] += 1
                if tag in {"p", "li", "div", "h2", "h3", "br"}:
                    self.parts[key].append("\n")
            elif target and target in classes:
                self.depth[key] = 1

    def handle_endtag(self, tag: str) -> None:
        for key in self.classes:
            if self.depth[key]:
                if tag in {"p", "li", "div", "h2", "h3"}:
                    self.parts[key].append("\n")
                self.depth[key] -= 1
        if tag in {"script", "style", "noscript", "nav", "footer", "form"} and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip:
            for key in self.classes:
                if self.depth[key]:
                    self.parts[key].append(data + " ")

    def text(self, key: str, limit: int) -> str:
        return "\n".join(" ".join(line.split()) for line in "".join(self.parts[key]).splitlines() if line.strip())[:limit].strip()


def _valid_detail(raw: str, listing: str, pattern: re.Pattern[str]) -> str | None:
    url = urljoin(listing, raw)
    parts = urlsplit(url)
    base = urlsplit(listing)
    if (parts.scheme != "https" or parts.hostname != base.hostname
            or parts.port not in (None, 443) or parts.username or parts.password
            or parts.query or parts.fragment or not pattern.fullmatch(parts.path)):
        return None
    return url


def _date(kind: str, parser: _Region) -> datetime | None:
    raw = parser.pubdate if kind == "jiangsu" else parser.text("date", 100)
    if not raw:
        return None
    try:
        if kind == "jiangsu":
            return datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(
                tzinfo=timezone(timedelta(hours=8))).astimezone(UTC)
        parsed = datetime.strptime(raw, "%d %b %Y")
        return parsed.replace(tzinfo=UTC) if parsed != datetime.min else None
    except ValueError:
        return None


class HtmlEvidenceProbe:
    @property
    def listing_entries(self):
        return {"default": self.listing}

    def iter_entry_pages(self, entry, *, start=0):
        if entry != "default" or start < 0:
            raise SourceFetchError("invalid_listing_offset")
        for rows, following in self.iter_listing_pages(start=start):
            self.listing_page_evidence = listing_evidence(
                (row.published_at or row.published_date for row in rows), ordered=True,
                terminal="exhausted" if following is None else None)
            yield rows, following

    def __init__(self, http: BoundedHTTP, *, kind: str, max_items: int = 3,
                 sleeper: Callable[[float], None] = time.sleep):
        if kind not in {"npcc", "jiangsu"} or not 1 <= max_items <= 5:
            raise ValueError("invalid_probe_configuration")
        self.http, self.kind, self.max_items, self.sleeper = http, kind, max_items, sleeper
        self.listing = NPCC_LIST if kind == "npcc" else JIANGSU_LIST
        self.pattern = NPCC_ARTICLE if kind == "npcc" else JIANGSU_ARTICLE
        self.reader = SourcePageReader(http, self.listing, lambda delay: self.sleeper(delay),
                                       allow_missing_robots=True, denied_listing="robots_disallowed",
                                       excessive_delay="robots_delay_exceeds_budget")
        self.diagnostics: dict[str, int] = {}
        self.item_diagnostics: list[dict] = []
        self.stage = "not_started"

    def _start_listing(self):
        self.diagnostics = {"robots_unavailable": 0, "listing_links": 0,
                            "detail_attempts": 0, "detail_body": 0, "detail_failed": 0}
        self.item_diagnostics = []
        self.stage = "robots"
        self.reader.refresh()
        self.reader.prepare()
        self.diagnostics["robots_unavailable"] = int(self.reader.robots_missing)
        self.stage = "listing"

    def _read_listing(self, url):
        return _decode(self.reader.get(url, "text/html,application/xhtml+xml;q=0.9"))

    def _listing_candidates(self, html, page_url):
        fragments = JIANGSU_RECORD.findall(html) if self.kind == "jiangsu" else []
        if self.kind == "jiangsu" and not fragments:
            raise SourceFetchError("listing_records_missing")
        links: dict[str, Candidate] = {}
        language = "en" if self.kind == "npcc" else "zh"
        date_pattern, date_format = ((NPCC_DAY, "%d %b %Y") if self.kind == "npcc" else (JIANGSU_DAY, "%Y-%m-%d"))
        for fragment in fragments or [html]:
            parser = _Links()
            parser.feed(fragment)
            for raw_url, title, context in parser.items:
                url = _valid_detail(raw_url, page_url, self.pattern)
                if url and url not in links:
                    match = date_pattern.search(context)
                    day = None
                    if match:
                        try:
                            day = datetime.strptime(match[0], date_format).date()
                        except ValueError:
                            pass
                    links[url] = Candidate(url=url, title=title, language=language, published_date=day)
        self.diagnostics["listing_links"] += len(links)
        if not links:
            raise SourceFetchError("listing_links_missing")
        return list(links.values())

    def list_candidates(self, *, first_import: bool = False) -> list[Candidate]:
        self._start_listing()
        return self._listing_candidates(self._read_listing(self.listing), self.listing)

    def iter_listing_pages(self, *, start=0):
        self._start_listing()
        if self.kind == "npcc":
            yield from linked_pages(self.listing, self._read_listing, self._listing_candidates,
                                    lambda parts: parts.path == "/releases" and re.fullmatch(r"page=[1-9]\d*", parts.query),
                                    start=start)
        else:
            def is_archive_page(parts):
                query = parse_qs(parts.query)
                return (parts.path == "/module/web/jpage/dataproxy.jsp" and query.get("columnid") == ["6372"]
                        and query.get("webid") == ["29"] and query.get("unitid") == ["405595"]
                        and len(query.get("page", [])) == 1 and query["page"][0].isdigit())

            yield from linked_pages(self.listing, self._read_listing, self._listing_candidates, is_archive_page,
                                    start=start, extra_links=JIANGSU_NEXT.findall)

    def fetch_detail(self, candidate: Candidate) -> Candidate:
        url = candidate.url
        if not _valid_detail(url, self.listing, self.pattern):
            raise SourceFetchError("invalid_article_url")
        self.stage = "detail"
        self.diagnostics["detail_attempts"] = self.diagnostics.get("detail_attempts", 0) + 1
        parser = _Region(body_class="content-body" if self.kind == "npcc" else "wzzw-article",
                         title_class="content-title" if self.kind == "npcc" else "wzzw-title",
                         date_class="date" if self.kind == "npcc" else None)
        parser.feed(_decode(self.reader.get(url, "text/html,application/xhtml+xml;q=0.9")))
        body = parser.text("body", 12000)
        title = parser.text("title", 500) or candidate.title
        if len(body) < (120 if self.kind == "npcc" else 80):
            raise IncompleteArticle(len(body))
        self.item_diagnostics.append({"url": url, "body_chars": len(body),
                                      "content_source": parser.content_source})
        self.diagnostics["detail_body"] = self.diagnostics.get("detail_body", 0) + 1
        parsed_date = _date(self.kind, parser)
        return replace(candidate, title=title, body=body,
                       published_at=parsed_date if self.kind == "jiangsu" else None,
                       published_date=(parsed_date.date() if self.kind == "npcc" and parsed_date
                                       else candidate.published_date))

    def candidates(self) -> list[Candidate]:
        ranked = self.list_candidates()
        selected = ranked[:self.max_items]
        if len(ranked) > self.max_items and self.max_items >= 3:
            extra = next((item for item in ranked[self.max_items:] if TECH.search(item.title)), None)
            if extra and not any(TECH.search(item.title) for item in selected):
                selected[-1] = extra
        results = bounded_details(selected, self.fetch_detail, self.diagnostics)
        self.stage = "done"
        return results


def probe(source: str, client: httpx.Client, *, max_items: int = 3) -> dict:
    if source == "govuk":
        adapter = GovUkAdapter(BoundedHTTP(client, allowed_hosts={"www.gov.uk"}), max_items=max_items)
        discovery = "https://www.gov.uk/api/search.json → /api/content{link}"
    elif source == "ccgp":
        adapter = CcgpAdapter(BoundedHTTP(client, allowed_hosts={"www.ccgp.gov.cn"}), max_items=max_items)
        discovery = "https://www.ccgp.gov.cn/cggg/zygg/gkzb/ → 公告详情"
    elif source == "nist":
        adapter = NistRssAdapter(BoundedHTTP(client, allowed_hosts={"www.nist.gov"}), max_items=max_items)
        discovery = "https://www.nist.gov/news-events/Public%20safety/rss.xml → 官方详情正文容器"
    elif source in {"npcc", "jiangsu"}:
        host = "news.npcc.police.uk" if source == "npcc" else "gat.jiangsu.gov.cn"
        adapter = HtmlEvidenceProbe(BoundedHTTP(client, allowed_hosts={host}, max_bytes=1_000_000),
                                    kind=source, max_items=max_items)
        discovery = (NPCC_LIST if source == "npcc" else JIANGSU_LIST) + " → 官方详情正文容器"
    else:
        raise ValueError("unknown_probe_source")
    report = {"source": source, "discovery": discovery, "status": "ok", "error_code": None,
              "stage": None,
              "metrics": {}, "items": []}
    try:
        candidates = adapter.candidates()
        extra = {item["url"]: item for item in getattr(adapter, "item_diagnostics", [])}
        for row in candidates:
            body_chars = len(row.body or "")
            summary_chars = len(row.summary or "")
            diagnostics = extra.get(row.url, {})
            html_attachment = {}
            if source == "govuk":
                html_attachment = {
                    "html_attachment_url": row.body_source_url,
                    "html_attachment_body_chars": diagnostics.get("attachment_body_chars", 0),
                    "html_attachment_error": diagnostics.get("attachment_error"),
                }
            report["items"].append({
                "url": row.url, "title": row.title,
                "published_at": row.published_at.isoformat() if row.published_at else None,
                "body_chars": body_chars, "summary_chars": summary_chars,
                "evidence": "full_text" if body_chars else "abstract_only" if summary_chars else "metadata_only",
                **{key: value for key, value in diagnostics.items()
                   if key not in {"url", "html_attachment_paths"}},
                **html_attachment,
            })
        if not candidates:
            report["status"] = "empty"
        elif getattr(adapter, "diagnostics", {}).get("detail_failed"):
            report["status"] = "partial"
    except Exception as exc:
        report["status"] = "failed"
        report["error_code"] = getattr(exc, "code", type(exc).__name__)
    report["metrics"] = getattr(adapter, "diagnostics", {})
    report["stage"] = getattr(adapter, "stage", None)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded, read-only top-five source evidence probe")
    parser.add_argument("--source", choices=("govuk", "ccgp", "nist", "npcc", "jiangsu"), required=True)
    parser.add_argument("--max-items", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true", help="required for network requests")
    args = parser.parse_args()
    if not args.execute or not 1 <= args.max_items <= 3:
        parser.error("pass --execute and choose 1-3 max-items")
    if args.output and args.output.exists():
        parser.error("output file already exists")
    with httpx.Client(timeout=httpx.Timeout(35, connect=10), follow_redirects=False,
                      headers={"User-Agent": USER_AGENT}) as client:
        result = probe(args.source, client, max_items=args.max_items)
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
