"""Small, bounded read-only adapters for official public sources."""
from __future__ import annotations

import csv
import io
import json
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from math import ceil
from typing import Callable
from urllib.parse import parse_qs, unquote, urlencode, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

import httpx

from .pipeline import Candidate, canonical_url


class SourceFetchError(Exception):
    def __init__(self, code: str, *, retry_after_seconds: int | None = None, release_at: datetime | None = None):
        super().__init__(code)
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        self.release_at = release_at


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
    if not isinstance(value, str) or not (value := value.strip()):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (ValueError, TypeError):
            return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def listing_evidence(dates, *, ordered=False, terminal=None, missing=0, local_zone=UTC):
    """Derive a page boundary from raw source dates before topic filtering."""
    values = list(dates)
    known = [value for value in values if value is not None]
    keys = [(value.astimezone(local_zone).date() if isinstance(value, datetime) else value,
             value.timestamp() if isinstance(value, datetime) else 0) for value in known]
    undated = len(values) - len(known) + missing
    return {
        "newest_at": known[max(range(len(keys)), key=keys.__getitem__)] if keys else None,
        "oldest_at": known[min(range(len(keys)), key=keys.__getitem__)] if keys else None,
        "undated": undated,
        "ordered": ordered and not undated and all(a >= b for a, b in zip(keys, keys[1:])),
        "terminal": terminal,
    }


def _retry_after(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    if value.isascii() and value.isdigit() and len(value) <= 9:
        return int(value)
    parsed = parse_time(value)
    return max(0, ceil((parsed - datetime.now(UTC)).total_seconds())) if parsed else None


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
        return self._request("GET", url, params, accept)

    def get_with_headers(self, url: str, *, params: dict | None = None, accept: str = "application/json"):
        return self._request_with_headers("GET", url, params, accept)

    def post_json(self, url: str, payload: dict) -> bytes:
        return self._request("POST", url, None, "application/json", payload)

    def _request(self, method, url, params, accept, payload=None):
        return self._request_with_headers(method, url, params, accept, payload)[0]

    def _request_with_headers(self, method, url, params, accept, payload=None):
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.hostname not in self.allowed_hosts or
                parts.port not in {None, 443} or parts.username or parts.password):
            raise SourceFetchError("host_not_allowed")
        pace = getattr(self.client, "pulse_host_pace", None)
        if pace:
            with pace(parts.hostname, self.delay_seconds):
                return self._read(method, url, params, accept, payload)
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        return self._read(method, url, params, accept, payload)

    def _read(self, method, url, params, accept, payload):
        try:
            with self.client.stream(method, url, params=params, json=payload, follow_redirects=False,
                                    headers={"Accept": accept}) as response:
                if response.status_code != 200:
                    delay = (_retry_after(response.headers.get("retry-after"))
                             if response.status_code in {429, 503} else None)
                    raise SourceFetchError(f"http_{response.status_code}", retry_after_seconds=delay)
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > self.max_bytes:
                        raise SourceFetchError("response_too_large")
                payload = bytes(data)
                if self.on_body is not None:
                    self.on_body(url, payload)
                return payload, response.headers
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
    ARCHIVE_PARAMS = {"filter_organisations": "home-office", "order": "-public_timestamp",
                      "fields": "link,title,description,public_timestamp"}
    listing_entries = {"default": SEARCH + "?" + urlencode(ARCHIVE_PARAMS)}

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
        self._reset_diagnostics()

    def _reset_diagnostics(self) -> None:
        self.diagnostics = {"search_results": 0, "detail_attempts": 0,
                            "detail_parsed": 0, "detail_failed": 0,
                            "attachment_attempts": 0, "attachment_parsed": 0,
                            "attachment_failed": 0, "csv_attempts": 0,
                            "csv_parsed": 0, "csv_failed": 0,
                            "csv_matched_html": 0, "csv_mismatched_html": 0}
        self.item_diagnostics = []

    @staticmethod
    def _article_path(raw: object) -> str | None:
        if not isinstance(raw, str) or not raw.startswith("/government/"):
            return None
        parts = urlsplit(raw)
        decoded = unquote(parts.path)
        if parts.query or parts.fragment or ".." in decoded or "\\" in decoded or any(
            ord(char) < 32 for char in decoded
        ):
            return None
        return parts.path

    @classmethod
    def _listing_item(cls, result: object, *, archive: bool = False) -> Candidate | None:
        if not isinstance(result, dict) or (path := cls._article_path(result.get("link"))) is None:
            return None
        title = result.get("title")
        description = result.get("description")
        timestamp = parse_time(result.get("public_timestamp"))
        return Candidate(
            url="https://www.gov.uk" + path,
            title=plain_text(title, max_chars=1000) if isinstance(title, str) else "",
            summary=plain_text(description, max_chars=1000) if isinstance(description, str) else None,
            published_at=None if archive else timestamp,
            source_updated_at=timestamp if archive else None,
            language="en",
        )

    def _search_page(self, count: int, start: int | None = None, *, archive=False) -> tuple[list, int | None]:
        params = ({"count": count, **self.ARCHIVE_PARAMS} if archive
                  else {"q": self.query, "count": count, "filter_organisations": "home-office"})
        if start is not None:
            params["start"] = start
            params["fields"] = "link,title,description,public_timestamp"
        try:
            data = json.loads(self.http.get(self.SEARCH, params=params))
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise SourceFetchError("invalid_search_payload") from exc
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise SourceFetchError("invalid_search_payload")
        returned_start = data.get("start")
        if start is not None and type(returned_start) is int and returned_start != start:
            raise SourceFetchError("invalid_search_offset")
        self.diagnostics["search_results"] += len(results)
        total = data.get("total")
        return results, total if type(total) is int and total >= 0 else None

    def iter_listing_pages(self, *, start: int = 0) -> Iterator[tuple[list[Candidate], int | None]]:
        """Yield each listing page with a checkpoint for the next search offset."""
        yield from self._iter_search_pages(start, archive=False)

    def iter_entry_pages(self, entry: str, *, start: int = 0):
        if entry != "default":
            raise SourceFetchError("unknown_listing_entry")
        yield from self._iter_search_pages(start, archive=True)

    def _iter_search_pages(self, start: int, *, archive: bool):
        if start < 0:
            raise SourceFetchError("invalid_search_offset")
        self._reset_diagnostics()
        while True:
            results, total = self._search_page(30, start, archive=archive)
            next_offset = start + len(results)
            following = next_offset if total is not None and next_offset < total else None
            if following is not None and not results:
                raise SourceFetchError("search_pagination_stalled")
            self.listing_page_evidence = listing_evidence(
                (parse_time(row.get("public_timestamp")) if isinstance(row, dict) else None for row in results),
                ordered=archive, terminal="exhausted" if total is not None and following is None else
                "truncated" if following is None else None,
            )
            yield [item for result in results if (item := self._listing_item(result, archive=archive)) is not None], following
            if following is None:
                return
            start = following

    def list_candidates(self, *, first_import: bool = False) -> list[Candidate]:
        return [item for page, _ in self.iter_listing_pages() for item in page]

    def candidates(self) -> list[Candidate]:
        self._reset_diagnostics()
        results, _ = self._search_page(min(5, self.max_items + 2))
        candidates = []
        for result in results:
            candidate = self._listing_item(result)
            if candidate is None:
                continue
            try:
                candidates.append(self.fetch_detail(candidate))
            except SourceFetchError as exc:
                if exc.code != "detail_title_missing":
                    raise
            if len(candidates) >= self.max_items:
                break
        return candidates

    def fetch_detail(self, candidate: Candidate) -> Candidate:
        parts = urlsplit(candidate.url)
        if (parts.scheme != "https" or parts.netloc != "www.gov.uk" or parts.query or parts.fragment
                or (path := self._article_path(parts.path)) is None):
            raise SourceFetchError("host_not_allowed")
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
            raise SourceFetchError("detail_title_missing")
        description = plain_text(detail.get("description") or "", max_chars=1000)
        original_description_chars = len(description)
        details = detail.get("details") or {}
        if not isinstance(details, dict):
            self.diagnostics["detail_failed"] += 1
            raise SourceFetchError("invalid_detail_payload")
        release_at = parse_time(details.get("release_timestamp"))
        if (path.startswith("/government/statistics/announcements/") and release_at
                and release_at > datetime.now(UTC)):
            raise SourceFetchError("statistics_not_yet_released", release_at=release_at)
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
        self.diagnostics["detail_parsed"] += 1
        return replace(
            candidate, title=title, body=body or None, summary=description or candidate.summary,
            body_source_url=body_source_url,
            published_at=parse_time(detail.get("first_published_at")) or candidate.published_at,
            source_updated_at=parse_time(detail.get("public_updated_at")) or candidate.source_updated_at,
        )


class _NistNewsTeasers(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[Candidate] = []
        self.url: str | None = None
        self.day: date | None = None
        self.heading = False
        self.title: list[str] = []
        self.summary_depth = 0
        self.summary: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "article":
            path = values.get("about") or ""
            if re.fullmatch(r"/news-events/news/20\d{2}/\d{2}/[a-z0-9-]+", path):
                self.url = "https://www.nist.gov" + path
                self.day, self.title, self.summary = None, [], []
        if self.url and "nist-teaser__title" in (values.get("class") or "").split():
            self.heading = True
        if self.url and tag == "div":
            if self.summary_depth or values.get("property") == "schema:text":
                self.summary_depth += 1
        if self.url and tag == "time" and self.day is None:
            raw = values.get("datetime") or ""
            try:
                # Drupal's day-only content renders a synthetic time in the attribute.
                self.day = date.fromisoformat(raw.split("T", 1)[0])
            except ValueError:
                pass

    def handle_endtag(self, tag):
        if tag in {"h2", "h3", "h4"}:
            self.heading = False
        if tag == "div" and self.summary_depth:
            self.summary_depth -= 1
        if tag == "article" and self.url:
            self.rows.append(Candidate(url=self.url, title=" ".join("".join(self.title).split()),
                                       summary=" ".join("".join(self.summary).split()) or None,
                                       published_date=self.day, language="en"))
            self.url, self.heading = None, False

    def handle_data(self, data):
        if self.heading:
            self.title.append(data)
        if self.summary_depth:
            self.summary.append(data)


class NistRssAdapter:
    FEED = "https://www.nist.gov/news-events/Public%20safety/rss.xml"
    TOPIC_ARCHIVE = "https://www.nist.gov/news-events/news-updates/topic/"
    FOCUSED_TERMS = ("public safety", "first responder", "law enforcement", "police",
                     "forensic", "emergency communication", "digital evidence",
                     "biometric", "firefighter")

    def __init__(self, http: BoundedHTTP, *, max_items: int = 2, fetch_details: bool = True,
                 feed: str | None = None, focused: bool = False, topic_ids: tuple[str, ...] = ()):
        if not 1 <= max_items <= 5:
            raise ValueError("max_items_must_be_1_to_5")
        self.http, self.max_items, self.fetch_details = http, max_items, fetch_details
        self.feed = feed or self.FEED
        self.focused = focused
        self.topic_ids = topic_ids
        self._reset_diagnostics()

    @classmethod
    def configured_entries(cls, feed, topic_ids=()):
        return {**{f"news-{topic_id}": cls.TOPIC_ARCHIVE + topic_id for topic_id in topic_ids},
                "default": feed}

    @property
    def listing_entries(self):
        return self.configured_entries(self.feed, self.topic_ids)

    @property
    def supplemental_entries(self):
        return frozenset({"default"}) if self.topic_ids else frozenset()

    def iter_entry_pages(self, entry, *, start=0):
        if entry == "default" and start == 0:
            yield self.list_candidates(scheduled=True), None
        elif entry in self.listing_entries and start >= 0:
            yield from self._news_pages(self.listing_entries[entry], start)
        else:
            raise SourceFetchError("invalid_listing_offset")

    def _news_pages(self, entry_url, start):
        from .source_listing import linked_pages

        self._reset_diagnostics()

        def valid_page(parts):
            params = parse_qs(parts.query)
            return (parts.path == urlsplit(entry_url).path and params.keys() == {"page"}
                    and len(params["page"]) == 1
                    and params["page"][0].isdigit())

        def parse(html, _url):
            parser = _NistNewsTeasers()
            parser.feed(html)
            if not parser.rows and "The search returned no results" not in html and "No results found" not in html:
                raise SourceFetchError("listing_no_article_links")
            return parser.rows

        for rows, following in linked_pages(
            entry_url,
            lambda url: self.http.get(url, accept="text/html").decode("utf-8-sig", "replace"),
            parse, valid_page, start=start,
        ):
            self.listing_page_evidence = listing_evidence(
                (row.published_date for row in rows), ordered=True,
                terminal="exhausted" if following is None else None)
            self.diagnostics["listing_links"] = self.diagnostics.get("listing_links", 0) + len(rows)
            yield rows, following

    def _reset_diagnostics(self) -> None:
        self.diagnostics = {"feed_items": 0, "feed_skipped": 0, "topic_filtered": 0, "detail_attempts": 0,
                            "detail_body": 0, "detail_failed": 0}
        self.discovered_urls: list[str] = []

    def list_candidates(self, *, first_import: bool = False, scheduled: bool = False) -> list[Candidate]:
        self._reset_diagnostics()
        try:
            root = ET.fromstring(self.http.get(self.feed))
        except ET.ParseError as exc:
            raise SourceFetchError("invalid_feed") from exc
        channel = root.find("./channel")
        if channel is None:
            raise SourceFetchError("invalid_feed")
        candidates: list[Candidate] = []
        items = channel.findall("item")
        self.diagnostics["feed_items"] = len(items)
        self.discovered_urls = [url for item in items
                                if (url := item.findtext("link")) and
                                urlsplit(url).hostname == "www.nist.gov" and
                                not urlsplit(url).path.startswith("/news-events/events/")]
        dates = []
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
            raw_date = item.findtext("pubDate")
            # Some news notices append a closing date to the single RSS field.
            rss_day = re.split(r"\s+-\s+", raw_date, maxsplit=1)[0].strip() if raw_date else None
            published_at = parse_time(rss_day)
            published_date = None
            if scheduled and published_at and published_at.hour == 12 and not (
                    published_at.minute or published_at.second or published_at.microsecond):
                # NIST Drupal's date-only articles render as noon UTC.
                published_date, published_at = published_at.date(), None
            if published_at is None and rss_day:
                try:
                    published_date = date.fromisoformat(rss_day.strip())
                except ValueError:
                    pass
            dates.append(published_at or published_date)
            if self.focused and not scheduled and not any(
                    term in (title + " " + (item.findtext("description") or "")).lower()
                    for term in self.FOCUSED_TERMS):
                self.diagnostics["topic_filtered"] += 1
                continue
            candidates.append(Candidate(
                url=url, title=title.strip(),
                summary=plain_text(item.findtext("description") or "", max_chars=1000) or None,
                published_at=published_at, published_date=published_date, language="en",
            ))
        self.listing_page_evidence = listing_evidence(dates, ordered=True, terminal="truncated")
        return candidates

    def fetch_detail(self, candidate: Candidate) -> Candidate:
        self.diagnostics["detail_attempts"] += 1
        try:
            body = nist_article_text(self.http.get(candidate.url).decode("utf-8", errors="replace"))
        except Exception:
            self.diagnostics["detail_failed"] += 1
            raise
        self.diagnostics["detail_body"] += bool(body)
        return replace(candidate, body=body or None)

    def candidates(self) -> list[Candidate]:
        listed = self.list_candidates()[:self.max_items]
        return [self.fetch_detail(candidate) for candidate in listed] if self.fetch_details else listed
