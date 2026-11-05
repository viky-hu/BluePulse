"""Small, bounded read-only adapters for official public sources."""
from __future__ import annotations

import csv
import io
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import unquote, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

import httpx

from .pipeline import Candidate, canonical_url


class SourceFetchError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.table_depth = 0
        self.cell_index = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag == "table":
            self.table_depth += 1
            self.parts.append("\n")
        if self.table_depth:
            if tag == "tr":
                self.cell_index = 0
                self.parts.append("\n")
            elif tag in {"td", "th"}:
                if self.cell_index:
                    self.parts.append(" | ")
                self.cell_index += 1
            elif tag in {"p", "br"}:
                self.parts.append(" ")
            return
        if tag in {"p", "br", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
        if self.table_depth:
            if tag == "tr":
                self.parts.append("\n")
            elif tag == "table":
                self.parts.append("\n")
                self.table_depth -= 1
            return
        if tag in {"p", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip and (not self.table_depth or data.strip()):
            self.parts.append(data)


def plain_text(value: str, *, max_chars: int = 12000) -> str:
    parser = _Text()
    parser.feed(value)
    text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
    return re.sub(r"[ \t]*\n[ \t]*", "\n", re.sub(r"\n\s*\n+", "\n", text)).strip()[:max_chars]


class _NistBody(HTMLParser):
    """Extract only the NIST article text container, never the whole site chrome."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.started = False
        self.done = False
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.done:
            return
        classes = dict(attrs).get("class") or ""
        if not self.started and tag == "div" and "text-with-summary" in classes.split():
            self.started, self.depth = True, 1
            return
        if not self.started:
            return
        if tag == "div":
            self.depth += 1
        if tag in {"script", "style", "noscript", "figure", "figcaption"}:
            self.skip += 1
        if tag in {"p", "li", "br", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self.started or self.done:
            return
        if tag in {"script", "style", "noscript", "figure", "figcaption"} and self.skip:
            self.skip -= 1
        if tag in {"p", "li", "h2", "h3"}:
            self.parts.append("\n")
        if tag == "div":
            self.depth -= 1
            if self.depth == 0:
                self.done = True

    def handle_data(self, data: str) -> None:
        if self.started and not self.done and not self.skip:
            self.parts.append(data)


def nist_article_text(html: str, *, max_chars: int = 12000) -> str:
    parser = _NistBody()
    parser.feed(html)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", "".join(parser.parts))).strip()[:max_chars]


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (ValueError, TypeError):
            return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


class BoundedHTTP:
    def __init__(self, client: httpx.Client, *, allowed_hosts: set[str],
                 max_bytes: int = 300_000, delay_seconds: float = 0.3,
                 on_body: Callable[[str, bytes], None] | None = None):
        self.client = client
        self.allowed_hosts = allowed_hosts
        self.max_bytes = max_bytes
        self.delay_seconds = delay_seconds
        self.on_body = on_body

    def get(self, url: str, *, params: dict | None = None,
            accept: str = "application/json, application/rss+xml;q=0.9") -> bytes:
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.hostname not in self.allowed_hosts or
                parts.port not in {None, 443} or parts.username or parts.password):
            raise SourceFetchError("host_not_allowed")
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        try:
            with self.client.stream("GET", url, params=params, follow_redirects=False,
                                    headers={"Accept": accept}) as response:
                if response.status_code != 200:
                    raise SourceFetchError(f"http_{response.status_code}")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > self.max_bytes:
                        raise SourceFetchError("response_too_large")
                payload = bytes(data)
                if self.on_body is not None:
                    self.on_body(url, payload)
                return payload
        except httpx.TimeoutException as exc:
            raise SourceFetchError("timeout") from exc
        except httpx.TransportError as exc:
            raise SourceFetchError("transport_error") from exc


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _asset_get(url: str, *, user_agent: str, accept: str, max_bytes: int) -> bytes:
    """Bounded standard-library GET for the fixed GOV.UK asset host."""
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != "assets.publishing.service.gov.uk"
            or parts.port not in (None, 443) or parts.username or parts.password
            or parts.query or parts.fragment):
        raise SourceFetchError("asset_host_not_allowed")
    request = Request(url, headers={"User-Agent": user_agent, "Accept": accept})
    try:
        with build_opener(_NoRedirect()).open(request, timeout=20) as response:
            if response.status != 200:
                raise SourceFetchError(f"http_{response.status}")
            if accept == "text/csv" and response.headers.get_content_type() not in {
                "text/csv", "application/csv", "text/plain",
            }:
                raise SourceFetchError("invalid_content_type")
            payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise SourceFetchError("response_too_large")
            return payload
    except HTTPError as exc:
        raise SourceFetchError(f"http_{exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SourceFetchError("transport_error") from exc


def fetch_govuk_csv(url: str, user_agent: str) -> tuple[bytes, int]:
    """Check asset robots before CSV; retry one transport failure without redirecting."""
    for attempt in range(2):
        try:
            return _fetch_govuk_csv_once(url, user_agent)
        except SourceFetchError as exc:
            if exc.code != "transport_error" or attempt:
                raise
            time.sleep(0.5)
    raise AssertionError("unreachable")


def _fetch_govuk_csv_once(url: str, user_agent: str) -> tuple[bytes, int]:
    robot_url = "https://assets.publishing.service.gov.uk/robots.txt"
    try:
        raw_robots = _asset_get(robot_url, user_agent=user_agent, accept="text/plain", max_bytes=100_000)
        robot_status = 200
    except SourceFetchError as exc:
        if exc.code != "http_404":
            raise
        raw_robots, robot_status = b"", 404
    policy = RobotFileParser()
    policy.parse(raw_robots.decode("utf-8-sig", "replace").splitlines())
    delay = policy.crawl_delay(user_agent) or 0
    if delay > 10 or not policy.can_fetch(user_agent, url):
        raise SourceFetchError("robots_disallowed_or_delayed")
    return _asset_get(url, user_agent=user_agent, accept="text/csv", max_bytes=300_000), robot_status


def csv_table_text(payload: bytes) -> tuple[str, list[list[str]]]:
    """Render a small CSV as row-preserving text; retain raw cells for HTML comparison."""
    try:
        rows = list(csv.reader(io.StringIO(payload.decode("utf-8-sig")), strict=True))
    except (UnicodeError, csv.Error) as exc:
        raise SourceFetchError("invalid_csv") from exc
    if not rows or len(rows) > 500 or max(map(len, rows)) > 40:
        raise SourceFetchError("invalid_csv_shape")
    width = max(map(len, rows))
    rows = [[cell.strip() for cell in row] + [""] * (width - len(row)) for row in rows]
    keep = [index for index in range(width) if any(row[index] for row in rows)]
    rows = [[row[index] for index in keep] for row in rows]
    if not rows or len(rows) < 2:
        raise SourceFetchError("csv_rows_missing")
    # GOV.UK sometimes splits grouped table headings over two CSV rows.
    grouped_header = len(rows) > 2 and not rows[1][0] and any(rows[1][1:])
    data_start = 2 if grouped_header else 1
    headers = rows[0][:]
    if grouped_header:
        group = ""
        for index, heading in enumerate(headers):
            group = heading or group
            subheading = rows[1][index]
            headers[index] = f"{group} {subheading}".strip() if subheading else heading
    data_rows = [row for row in rows[data_start:] if any(row)]
    if not data_rows:
        raise SourceFetchError("csv_rows_missing")
    text = "\n".join(" | ".join(row) for row in [headers, *data_rows])
    return text, data_rows


def _html_csv_rows_match(html_body: str, csv_rows: list[list[str]]) -> bool:
    html_rows = [line.split(" | ") for line in html_body.splitlines()[1:]]
    return len(html_rows) == len(csv_rows) and all(
        [cell.strip() for cell in html_row] == csv_row
        for html_row, csv_row in zip(html_rows, csv_rows)
    )


class GovUkAdapter:
    SEARCH = "https://www.gov.uk/api/search.json"
    CONTENT = "https://www.gov.uk/api/content"

    @staticmethod
    def _html_attachment_path(attachment: object) -> str | None:
        if not isinstance(attachment, dict) or attachment.get("attachment_type") != "html":
            return None
        path = attachment.get("url")
        if not isinstance(path, str) or not path.startswith("/government/") or path.startswith("//"):
            return None
        parts = urlsplit(path)
        decoded_path = unquote(path)
        if (parts.query or parts.fragment or ".." in decoded_path or "\\" in decoded_path
                or any(ord(char) < 32 for char in decoded_path)):
            return None
        # An accessible translation is a separate document, not extra evidence for the English item.
        label = f"{attachment.get('title') or ''} {path}".casefold()
        if attachment.get("locale") not in (None, "en") or "welsh" in label or "cymraeg" in label:
            return None
        return path

    @staticmethod
    def _csv_attachment_url(attachment: object) -> str | None:
        if not isinstance(attachment, dict) or attachment.get("attachment_type") != "file":
            return None
        if attachment.get("content_type") != "text/csv":
            return None
        url = attachment.get("url")
        if not isinstance(url, str):
            return None
        parts = urlsplit(url)
        decoded_path = unquote(parts.path)
        label = f"{attachment.get('title') or ''} {decoded_path}".casefold()
        if (parts.scheme != "https" or parts.hostname != "assets.publishing.service.gov.uk"
                or parts.port not in (None, 443) or parts.username or parts.password
                or parts.query or parts.fragment or not parts.path.startswith("/media/")
                or ".." in decoded_path or "\\" in decoded_path
                or any(ord(char) < 32 for char in decoded_path)
                or attachment.get("locale") not in (None, "en")
                or "welsh" in label or "cymraeg" in label):
            return None
        return url

    def __init__(self, http: BoundedHTTP, *, query: str = "live facial recognition",
                 max_items: int = 2,
                 csv_fetcher: Callable[[str, str], tuple[bytes, int]] = fetch_govuk_csv):
        if not 1 <= max_items <= 5:
            raise ValueError("max_items_must_be_1_to_5")
        self.http, self.query, self.max_items = http, query, max_items
        self.csv_fetcher = csv_fetcher
        self.diagnostics: dict[str, int] = {}
        self.item_diagnostics: list[dict] = []

    def candidates(self) -> list[Candidate]:
        self.diagnostics = {"search_results": 0, "detail_attempts": 0,
                            "detail_parsed": 0, "detail_failed": 0,
                            "attachment_attempts": 0, "attachment_parsed": 0,
                            "attachment_failed": 0, "csv_attempts": 0,
                            "csv_parsed": 0, "csv_failed": 0,
                            "csv_matched_html": 0, "csv_mismatched_html": 0}
        self.item_diagnostics = []
        data = json.loads(self.http.get(self.SEARCH, params={
            "q": self.query, "count": min(5, self.max_items + 2),
            "filter_organisations": "home-office",
        }))
        results = data.get("results")
        if not isinstance(results, list):
            raise SourceFetchError("invalid_search_payload")
        self.diagnostics["search_results"] = len(results)
        candidates: list[Candidate] = []
        for result in results:
            path = result.get("link") if isinstance(result, dict) else None
            if not isinstance(path, str) or not path.startswith("/government/") or path.startswith("//"):
                continue
            if urlsplit(path).query or ".." in path:
                continue
            self.diagnostics["detail_attempts"] += 1
            try:
                detail = json.loads(self.http.get(self.CONTENT + path))
            except Exception:
                self.diagnostics["detail_failed"] += 1
                raise
            if not isinstance(detail, dict):
                self.diagnostics["detail_failed"] += 1
                raise SourceFetchError("invalid_detail_payload")
            title = detail.get("title")
            if not isinstance(title, str) or not title.strip():
                self.diagnostics["detail_failed"] += 1
                continue
            description = plain_text(detail.get("description") or "", max_chars=1000)
            original_description_chars = len(description)
            details = detail.get("details") or {}
            raw_body = details.get("body") or ""
            body = plain_text(raw_body) if isinstance(raw_body, str) else ""
            page_body_chars = len(body)
            # A publication landing page may contain an introduction but not the attached document.
            if details.get("attachments") and page_body_chars < 1000:
                if page_body_chars >= 100:
                    description = plain_text(description + "\n" + body, max_chars=1000)
                body = ""
            attachments = details.get("attachments")
            if not isinstance(attachments, list):
                attachments = []
            html_paths = [item.get("url") for item in attachments
                          if isinstance(item, dict) and item.get("attachment_type") == "html"
                          and isinstance(item.get("url"), str)]
            other_text_attachments = [item for item in attachments
                                      if isinstance(item, dict) and item.get("attachment_type") == "file"
                                      and item.get("content_type") in {"text/csv", "text/plain"}]
            body_source_url = None
            attachment_error = None
            # Read at most one English HTML document through the same bounded client.
            # Content API details.body is the publication body without GOV.UK page chrome.
            for attachment in attachments:
                attachment_path = self._html_attachment_path(attachment)
                if attachment_path is None:
                    continue
                self.diagnostics["attachment_attempts"] += 1
                try:
                    attachment_detail = json.loads(self.http.get(self.CONTENT + attachment_path))
                    raw_attachment_body = (attachment_detail.get("details") or {}).get("body")
                    attachment_body = (plain_text(raw_attachment_body, max_chars=300_000)
                                       if isinstance(raw_attachment_body, str) else "")
                    if not attachment_body:
                        raise SourceFetchError("attachment_body_missing")
                except (SourceFetchError, ValueError, AttributeError, TypeError) as exc:
                    attachment_error = getattr(exc, "code", "invalid_attachment_payload")
                    self.diagnostics["attachment_failed"] += 1
                else:
                    body = attachment_body
                    body_source_url = "https://www.gov.uk" + attachment_path
                    self.diagnostics["attachment_parsed"] += 1
                break
            csv_url = next((url for attachment in attachments
                            if (url := self._csv_attachment_url(attachment)) is not None), None)
            csv_error = None
            csv_rows = 0
            csv_matches_html = None
            csv_robots_status = None
            if csv_url is not None:
                self.diagnostics["csv_attempts"] += 1
                try:
                    user_agent = self.http.client.headers.get("User-Agent", "BluePulseResearch/0.1")
                    csv_payload, csv_robots_status = self.csv_fetcher(csv_url, user_agent)
                    csv_body, data_rows = csv_table_text(csv_payload)
                    csv_rows = len(data_rows)
                    if body_source_url is not None:
                        csv_matches_html = _html_csv_rows_match(body, data_rows)
                        self.diagnostics["csv_matched_html" if csv_matches_html
                                         else "csv_mismatched_html"] += 1
                    elif not body:
                        body, body_source_url = csv_body, csv_url
                except SourceFetchError as exc:
                    csv_error = exc.code
                    self.diagnostics["csv_failed"] += 1
                else:
                    self.diagnostics["csv_parsed"] += 1
            self.item_diagnostics.append({
                "url": "https://www.gov.uk" + path,
                "attachment_count": len(attachments),
                "html_attachment_count": len(html_paths),
                "html_attachment_paths": html_paths,
                "other_text_attachment_count": len(other_text_attachments),
                "page_body_chars": page_body_chars,
                "description_chars": original_description_chars,
                "body_source_url": body_source_url,
                "attachment_body_chars": len(body) if body_source_url else 0,
                "attachment_error": attachment_error,
                "csv_url": csv_url,
                "csv_rows": csv_rows,
                "csv_matches_html": csv_matches_html,
                "csv_robots_status": csv_robots_status,
                "csv_error": csv_error,
            })
            candidates.append(Candidate(
                url="https://www.gov.uk" + path, title=title,
                body=body or None, summary=description or None,
                body_source_url=body_source_url,
                published_at=parse_time(detail.get("first_published_at") or result.get("public_timestamp")),
                language="en",
            ))
            self.diagnostics["detail_parsed"] += 1
            if len(candidates) >= self.max_items:
                break
        return candidates


class NistRssAdapter:
    FEED = "https://www.nist.gov/news-events/Public%20safety/rss.xml"
    FOCUSED_TERMS = ("public safety", "first responder", "law enforcement", "police",
                     "forensic", "emergency communication", "digital evidence",
                     "biometric", "firefighter")

    def __init__(self, http: BoundedHTTP, *, max_items: int = 2, fetch_details: bool = True,
                 feed: str | None = None, focused: bool = False):
        if not 1 <= max_items <= 5:
            raise ValueError("max_items_must_be_1_to_5")
        self.http, self.max_items, self.fetch_details = http, max_items, fetch_details
        self.feed = feed or self.FEED
        self.focused = focused
        self.diagnostics: dict[str, int] = {}
        self.discovered_urls: list[str] = []

    def candidates(self) -> list[Candidate]:
        self.diagnostics = {"feed_items": 0, "feed_skipped": 0, "topic_filtered": 0, "detail_attempts": 0,
                            "detail_body": 0, "detail_failed": 0}
        root = ET.fromstring(self.http.get(self.feed))
        candidates: list[Candidate] = []
        items = root.findall("./channel/item")
        self.diagnostics["feed_items"] = len(items)
        self.discovered_urls = [url for item in items
                                if (url := item.findtext("link")) and
                                urlsplit(url).hostname == "www.nist.gov" and
                                not urlsplit(url).path.startswith("/news-events/events/")]
        for item in items:
            url, title = item.findtext("link"), item.findtext("title")
            if not url or not title:
                self.diagnostics["feed_skipped"] += 1
                continue
            try:
                canonical_url(url, ["www.nist.gov"])
            except ValueError:
                self.diagnostics["feed_skipped"] += 1
                continue
            # The public-safety feed also carries event pages; they are not articles.
            if urlsplit(url).path.startswith("/news-events/events/"):
                self.diagnostics["feed_skipped"] += 1
                continue
            if self.focused and not any(term in (title + " " + (item.findtext("description") or "")).lower()
                                        for term in self.FOCUSED_TERMS):
                self.diagnostics["topic_filtered"] += 1
                continue
            body = ""
            if self.fetch_details:
                self.diagnostics["detail_attempts"] += 1
                try:
                    body = nist_article_text(self.http.get(url).decode("utf-8", errors="replace"))
                except Exception:
                    self.diagnostics["detail_failed"] += 1
                    raise
                self.diagnostics["detail_body"] += bool(body)
            candidates.append(Candidate(
                url=url, title=title.strip(),
                body=body or None,
                summary=plain_text(item.findtext("description") or "", max_chars=1000) or None,
                published_at=parse_time(item.findtext("pubDate")), language="en",
            ))
            if len(candidates) >= self.max_items:
                break
        return candidates
