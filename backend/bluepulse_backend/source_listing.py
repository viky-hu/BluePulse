"""Pagination declared by public HTML listings."""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .live_sources import SourceFetchError


class _NextLink(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        href = values.get("href")
        if tag in {"a", "link"} and href and "next" in (values.get("rel") or "").lower().split():
            self.links.append(href)


def linked_pages(entry, fetch, parse, is_archive_page, *, start=0, extra_links=None):
    """Follow source-provided next links within the source's listing route."""
    url, seen, index = entry, set(), 0
    origin = urlsplit(entry)
    while url:
        if url in seen:
            raise SourceFetchError("listing_pagination_stalled")
        seen.add(url)
        html = fetch(url)
        parser = _NextLink()
        parser.feed(html)
        if extra_links:
            parser.links.extend(extra_links(html))
        next_url = None
        for href in parser.links:
            link = urljoin(url, href)
            parts = urlsplit(link)
            if (parts.scheme == "https" and parts.netloc == origin.netloc and not parts.fragment
                    and is_archive_page(parts)):
                next_url = link
                break
        if index >= start:
            yield parse(html, url), index + 1 if next_url else None
        url, index = next_url, index + 1
