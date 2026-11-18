"""Dated listing and article extraction for Nanjing Public Security."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import re
import time

from .ccgp_source import _Links, _decode
from .live_sources import SourceFetchError, listing_evidence
from .pipeline import Candidate
from .source_page import IncompleteArticle, SourcePageReader, bounded_details
from .top5_probe import _Region, _valid_detail


LISTING = "https://gaj.nanjing.gov.cn/jwdt/"
ARTICLE = re.compile(r"/jwdt/[0-9]{6}/t[0-9]{8}_[0-9]+\.html")
PAGES = re.compile(r""">\s*createPageHTML\(\s*(\d+)\s*,\s*(\d+)\s*,\s*['"]index['"]\s*,\s*['"]html['"]\s*\)""", re.I)
DAY = re.compile(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)")
PUBLISHED = re.compile(r"发布时间\s*[:：]\s*(20\d{2}-\d{2}-\d{2})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?")
CHINA = timezone(timedelta(hours=8))


class NanjingPoliceAdapter:
    listing_entries = {"default": LISTING}

    def __init__(self, http, *, max_items: int):
        self.http, self.max_items = http, max_items
        self.reader = SourcePageReader(http, LISTING, time.sleep, allow_missing_robots=True)
        self.diagnostics = {}

    def _read(self, url):
        return _decode(self.reader.get(url, "text/html"))

    def _page(self, index):
        url = LISTING if index == 0 else f"{LISTING}index_{index}.html"
        html = self._read(url)
        pager = PAGES.search(html)
        if not pager or int(pager[2]) != index or not index < int(pager[1]):
            raise SourceFetchError("invalid_listing_pagination")
        parser = _Links()
        parser.feed(html)
        items = {}
        for href, title, context in parser.items:
            detail = _valid_detail(href, url, ARTICLE)
            if detail is None or not title.strip() or detail in items:
                continue
            match = DAY.search(context)
            try:
                published = date.fromisoformat(match[1]) if match else None
            except ValueError:
                published = None
            items[detail] = Candidate(detail, title[:500], published_date=published, language="zh")
        if not items:
            raise SourceFetchError("listing_records_missing")
        next_index = index + 1 if index + 1 < int(pager[1]) else None
        return list(items.values()), next_index

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
        parser = _Region(body_class="doccontent", title_class="doctitle", date_class="field_con1")
        parser.feed(self._read(url))
        body = parser.text("body", 100_000)
        if len(body) < 120:
            raise IncompleteArticle(len(body))
        match = PUBLISHED.search(parser.text("date", 200))
        instant, day = None, candidate.published_date
        if match:
            try:
                day = date.fromisoformat(match[1])
                if match[2]:
                    instant = datetime.fromisoformat(f"{day}T{match[2].zfill(5)}").replace(tzinfo=CHINA)
            except ValueError:
                pass
        return replace(candidate, title=parser.text("title", 500) or candidate.title,
                       body=body, published_at=instant, published_date=day)

    def candidates(self):
        return bounded_details(self.list_candidates()[:self.max_items], self.fetch_detail, self.diagnostics)
