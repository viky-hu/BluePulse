"""Collect dated articles from Suzhou Public Security's official news column."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import re
import time

from .ccgp_source import _Links, _decode
from .live_sources import SourceFetchError, listing_evidence
from .pipeline import Candidate
from .source_page import IncompleteArticle, SourcePageReader, bounded_details
from .top5_probe import _Region, _valid_detail


BASE = "https://gonganju.suzhou.gov.cn/gaj/jwdt/"
LISTING = f"{BASE}nav_list.shtml"
ARTICLE = re.compile(r"/gaj/jwdt/[0-9]{6}/[0-9a-f]{32}\.shtml")
PAGER = re.compile(
    r"""createPageHTML\(\s*['"]page_div['"]\s*,\s*(\d+)\s*,\s*(\d+)"""
    r"""\s*,\s*['"]nav_list['"]\s*,\s*['"]shtml['"]\s*,\s*\d+\s*\)"""
)
DAY = re.compile(r"(?<!\d)20\d{2}-\d{2}-\d{2}(?!\d)\s*$")
PUBLISHED = re.compile(r"发布日期\s*[:：]\s*(20\d{2}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?")
CHINA = timezone(timedelta(hours=8))


class SuzhouPoliceAdapter:
    listing_entries = {"default": LISTING}

    def __init__(self, http, *, max_items: int):
        self.max_items = max_items
        # The site returns this exact redirect for missing files, including robots.txt.
        self.reader = SourcePageReader(http, LISTING, time.sleep, allow_missing_robots=True,
                                       missing_robots_redirect="http://gonganju.suzhou.gov.cn")
        self.diagnostics = {"robots_unavailable": 0, "detail_failed": 0}

    def _read(self, url):
        html = _decode(self.reader.get(url, "text/html"))
        self.diagnostics["robots_unavailable"] = int(self.reader.robots_missing)
        return html

    def _page(self, index):
        page = index + 1
        url = LISTING if index == 0 else f"{BASE}nav_list_{page}.shtml"
        html = self._read(url)
        pager = PAGER.search(html)
        if not pager or int(pager[2]) != page or page > int(pager[1]):
            raise SourceFetchError("invalid_listing_pagination")

        parser = _Links()
        parser.feed(html)
        items = {}
        for href, title, context in parser.items:
            detail = _valid_detail(href, url, ARTICLE)
            if detail is None or detail in items:
                continue
            match = DAY.search(context)
            try:
                published = date.fromisoformat(match[0].strip()) if match else None
            except ValueError:
                published = None
            items[detail] = Candidate(detail, title[:500], published_date=published, language="zh")
        if not items:
            raise SourceFetchError("listing_records_missing")
        return list(items.values()), index + 1 if page < int(pager[1]) else None

    def iter_entry_pages(self, entry, *, start=0):
        if entry != "default" or start < 0:
            raise SourceFetchError("invalid_listing_offset")
        self.reader.refresh()
        index = start
        while index is not None:
            items, index = self._page(index)
            self.listing_page_evidence = listing_evidence(
                (item.published_date for item in items), ordered=True, local_zone=CHINA,
                terminal="exhausted" if index is None else None)
            yield items, index

    def list_candidates(self, *, first_import=False):
        items, _ = next(self.iter_entry_pages("default"))
        return items

    def fetch_detail(self, candidate):
        url = _valid_detail(candidate.url, LISTING, ARTICLE)
        if url is None:
            raise SourceFetchError("invalid_article_url")
        parser = _Region(body_class="article-content", title_class="article-title", date_class="date")
        parser.feed(self._read(url))
        body = parser.text("body", 100_000)
        if len(body) < 120:
            raise IncompleteArticle(len(body))
        match = PUBLISHED.search(parser.text("date", 150))
        instant, day = None, candidate.published_date
        if match:
            try:
                day = date.fromisoformat(match[1])
                if match[2]:
                    instant = datetime.fromisoformat(f"{day}T{match[2]}").replace(tzinfo=CHINA)
            except ValueError:
                pass
        return replace(candidate, title=parser.text("title", 500) or candidate.title,
                       body=body, published_at=instant, published_date=day)

    def candidates(self):
        return bounded_details(self.list_candidates()[:self.max_items], self.fetch_detail, self.diagnostics)
