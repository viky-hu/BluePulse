"""Bounded, read-only discovery probe for five candidate sources.

Run explicitly; never writes material or calls a model. The output is diagnostics,
not proof that an article body is complete or licensed for publication.
"""
from __future__ import annotations

import argparse
import json
import re
from urllib.parse import urlencode
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from .ccgp_source import USER_AGENT
from .htx_source import HOST as HTX_HOST, HtxNewsAdapter
from .live_sources import BoundedHTTP, NistRssAdapter, SourceFetchError


LISTINGS = {
    "police-science": ("science.police.uk", "https://science.police.uk/news-and-events/news/", r"/news-and-events/news/[^/]+/"),
    "govtech-public-safety": ("www.govtech.com", "https://www.govtech.com/public-safety", r"/public-safety/[^/]+"),
}


class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.href: str | None = None
        self.words: list[str] = []
        self.items: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.words = []

    def handle_data(self, data):
        if self.href:
            self.words.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.items.append((self.href, " ".join("".join(self.words).split())[:160]))
            self.href = None


def get(client: httpx.Client, url: str, host: str, *, limit: int = 1_000_000) -> tuple[int, bytes, str | None]:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != host or parts.port not in (None, 443) or parts.username or parts.password:
        raise ValueError("host_not_allowed")
    with client.stream("GET", url, follow_redirects=False) as response:
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError("response_too_large")
        return response.status_code, bytes(data), response.headers.get("location")


def html_probe(client: httpx.Client, kind: str) -> dict:
    host, listing, pattern = LISTINGS[kind]
    result: dict = {"source": kind, "listing": listing}
    try:
        status, robots, location = get(client, f"https://{host}/robots.txt", host, limit=200_000)
    except (httpx.HTTPError, ValueError) as exc:
        return {**result, "blocked_at": "robots_request", "error": type(exc).__name__}
    result["robots"] = {"status": status, "redirect": location}
    if status not in (200, 404):
        result["blocked_at"] = "robots"
        return result
    policy = RobotFileParser()
    policy.parse(robots.decode("utf-8", "replace").splitlines() if status == 200 else [])
    if not policy.can_fetch(USER_AGENT, listing):
        result["blocked_at"] = "robots_disallow_listing"
        return result
    delay = policy.crawl_delay(USER_AGENT) or 0
    if delay > 10:
        result["blocked_at"] = "robots_delay_exceeds_budget"
        return result
    try:
        status, body, location = get(client, listing, host)
    except (httpx.HTTPError, ValueError) as exc:
        return {**result, "blocked_at": "listing_request", "error": type(exc).__name__}
    result["listing_response"] = {"status": status, "bytes": len(body), "redirect": location}
    if status != 200:
        result["blocked_at"] = "listing"
        return result
    parser = Links()
    parser.feed(body.decode("utf-8", "replace"))
    matches: dict[str, str] = {}
    for href, title in parser.items:
        url = urljoin(listing, href)
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.hostname == host and re.fullmatch(pattern, parts.path) and parts.path != urlsplit(listing).path and not parts.fragment:
            matches.setdefault(url, title)
    result["links_total"] = len(parser.items)
    result["candidate_links"] = len(matches)
    result["samples"] = [{"url": url, "title": title} for url, title in list(matches.items())[:5]]
    return result


def nist_probe(client: httpx.Client) -> dict:
    feed = "https://www.nist.gov/news-events/forensic%20science/rss.xml"
    adapter = NistRssAdapter(BoundedHTTP(client, allowed_hosts={"www.nist.gov"},
                                         max_bytes=1_000_000), max_items=3, feed=feed)
    result: dict = {"source": "nist-forensic", "feed": feed}
    try:
        rows = adapter.candidates()
        result["metrics"] = adapter.diagnostics
        result["samples"] = [{"url": row.url, "title": row.title,
                              "body_chars": len(row.body or ""),
                              "summary_chars": len(row.summary or ""),
                              "published_at": row.published_at.isoformat() if row.published_at else None}
                             for row in rows]
    except SourceFetchError as exc:
        result["metrics"] = adapter.diagnostics
        result["blocked_at"] = exc.code
    return result


def htx_probe(client: httpx.Client) -> dict:
    adapter = HtxNewsAdapter(BoundedHTTP(client, allowed_hosts={HTX_HOST},
                                        max_bytes=1_000_000), max_items=2)
    result: dict = {"source": "htx"}
    try:
        rows = adapter.candidates()
        result["metrics"] = adapter.diagnostics
        result["samples"] = [{"url": row.url, "title": row.title,
                              "body_chars": len(row.body or ""),
                              "published_at": row.published_at.isoformat() if row.published_at else None}
                             for row in rows]
    except SourceFetchError as exc:
        result["metrics"] = adapter.diagnostics
        result["blocked_at"] = exc.code
    return result


def openalex_probe(client: httpx.Client) -> dict:
    params = {"search.title_and_abstract": "police artificial intelligence",
              "filter": "from_publication_date:2026-01-01", "sort": "publication_date:desc",
              "per-page": "5", "select": "id,display_name,publication_date,abstract_inverted_index,primary_location"}
    url = "https://api.openalex.org/works?" + urlencode(params)
    result: dict = {"source": "openalex", "query": params["search.title_and_abstract"]}
    status, body, location = get(client, url, "api.openalex.org")
    result["response"] = {"status": status, "bytes": len(body), "redirect": location}
    if status != 200:
        result["blocked_at"] = "api"
        return result
    payload = json.loads(body)
    works = payload.get("results")
    if not isinstance(works, list):
        result["blocked_at"] = "invalid_payload"
        return result
    result["results"] = len(works)
    result["samples"] = []
    for work in works:
        index = work.get("abstract_inverted_index")
        word_count = sum(len(places) for places in index.values()) if isinstance(index, dict) else 0
        location = work.get("primary_location") or {}
        result["samples"].append({"id": work.get("id"), "title": work.get("display_name"),
                                  "publication_date": work.get("publication_date"),
                                  "abstract_words": word_count,
                                  "landing_page_url": location.get("landing_page_url")})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=[*LISTINGS, "htx", "nist-forensic", "openalex"], required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("pass --execute for bounded public network reads")
    with httpx.Client(timeout=httpx.Timeout(15, connect=8), follow_redirects=False,
                      headers={"User-Agent": USER_AGENT}) as client:
        try:
            if args.source in LISTINGS:
                result = html_probe(client, args.source)
            elif args.source == "htx":
                result = htx_probe(client)
            elif args.source == "nist-forensic":
                result = nist_probe(client)
            else:
                result = openalex_probe(client)
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            result = {"source": args.source, "blocked_at": "transport_or_policy", "error": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
