from __future__ import annotations

import re
from datetime import UTC, datetime
from time import sleep
from typing import Callable
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from bluepulse_backend.ingestion.adapters import FetchedArticle, USER_AGENT
from bluepulse_backend.models import Source

MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_ROBOTS_BYTES = 256 * 1024
ARTICLE_PATH = re.compile(r"/topics/articles/[a-z0-9-]+")


def _check_url(url: str, source: Source, *, listing: bool) -> None:
    parsed = urlsplit(url)
    expected = urlsplit(source.base_url)
    allowed_hosts = set(source.config.get("allowed_hosts", []))
    if (
        parsed.scheme != "https" or parsed.hostname != expected.hostname
        or parsed.hostname not in allowed_hosts or parsed.username or parsed.password
        or parsed.port not in {None, 443} or parsed.fragment
    ):
        raise ValueError("NIJ URL 不在配置允许的 HTTPS 主机范围内。")
    if listing:
        query = parse_qs(parsed.query)
        if parsed.path != "/library/articles/list" or query.get("subtopic") != ["304581"]:
            raise ValueError("NIJ 列表 URL 不在允许的技术文章范围内。")
        if set(query) - {"subtopic", "page"} or any(
            not value.isdecimal() for value in query.get("page", ["0"])
        ):
            raise ValueError("NIJ 列表 URL 参数不受支持。")
    elif not ARTICLE_PATH.fullmatch(parsed.path) or parsed.query:
        raise ValueError("NIJ 文章 URL 不在允许的详情路径范围内。")


def _read_bytes(client: httpx.Client, url: str, limit: int) -> tuple[int, bytes]:
    with client.stream("GET", url) as response:
        if response.is_redirect:
            raise RuntimeError("NIJ 页面发生重定向，未继续访问目标。")
        if response.headers.get("x-amzn-waf-action", "").lower() in {
            "challenge", "captcha", "block",
        }:
            raise RuntimeError("NIJ 要求交互式访问验证，未尝试绕过。")
        if response.status_code == 429:
            raise RuntimeError("NIJ 返回 HTTP 429，未立即重试。")
        if response.status_code == 404:
            return 404, b""
        response.raise_for_status()
        declared_size = response.headers.get("content-length")
        if declared_size and int(declared_size) > limit:
            raise RuntimeError("NIJ 页面超过大小限制。")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > limit:
                raise RuntimeError("NIJ 页面超过大小限制。")
            chunks.append(chunk)
        return response.status_code, b"".join(chunks)


def _robots_policy(client: httpx.Client, source: Source) -> RobotFileParser:
    robots_url = f"https://{urlsplit(source.base_url).hostname}/robots.txt"
    status, body = _read_bytes(client, robots_url, MAX_ROBOTS_BYTES)
    policy = RobotFileParser()
    policy.set_url(robots_url)
    policy.parse([] if status == 404 else body.decode("utf-8", errors="replace").splitlines())
    return policy


def _listing_urls(raw_html: bytes, base_url: str, source: Source) -> list[str]:
    soup = BeautifulSoup(raw_html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()
    for anchor in soup.select("main .listing-item--article a[href]"):
        url = urljoin(base_url, anchor["href"])
        try:
            _check_url(url, source, listing=False)
        except ValueError:
            continue
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _article(raw_html: bytes, url: str) -> FetchedArticle:
    soup = BeautifulSoup(raw_html, "html.parser")
    heading = soup.select_one("main h1") or soup.select_one("h1")
    content = soup.select_one("main .field--name-body")
    if heading is None or content is None:
        raise RuntimeError("NIJ 文章标题或正文未找到，页面结构可能已变化。")
    for element in content.select("script, style, noscript, form"):
        element.decompose()
    title = " ".join(heading.get_text(" ", strip=True).split())[:500]
    body = "\n".join(
        line for line in (" ".join(part.split()) for part in content.get_text("\n", strip=True).splitlines())
        if line
    )[:100_000]
    if not title or len(body) < 100:
        raise RuntimeError("NIJ 文章正文过短，可能是异常页面。")
    date_field = soup.select_one(".field--name-field-date-published")
    published_at = None
    if date_field is not None:
        date_text = date_field.get_text(" ", strip=True).removeprefix("Date Published").strip()
        try:
            published_at = datetime.strptime(date_text, "%B %d, %Y").replace(tzinfo=UTC)
        except ValueError:
            pass
    return FetchedArticle(
        url=url, title=title, body=body, published_at=published_at,
        language="en", country_code="US", parse_status="full_text",
    )


def fetch_nij_html(
    source: Source,
    *,
    known_urls: set[str] | None = None,
    client: httpx.Client | None = None,
    sleeper: Callable[[float], None] = sleep,
    diagnostics: dict[str, int] | None = None,
) -> list[FetchedArticle]:
    _check_url(source.base_url, source, listing=True)
    max_pages = min(max(int(source.config.get("max_listing_pages", 1)), 1), 3)
    max_articles = min(max(int(source.config.get("max_articles", 4)), 1), 10)
    delay = max(float(source.config.get("request_delay_seconds", 1)), 1.0)
    stats = diagnostics if diagnostics is not None else {}
    stats.update({"listing_pages": 0, "listing_links": 0, "new_candidates": 0,
                  "detail_pages": 0, "detail_parse_failed": 0, "known_skipped": 0})

    def run(active_client: httpx.Client) -> list[FetchedArticle]:
        policy = _robots_policy(active_client, source)
        effective_delay = max(delay, float(policy.crawl_delay(USER_AGENT) or 0))
        request_count = 1

        def get_page(url: str) -> tuple[int, bytes]:
            nonlocal request_count
            if not policy.can_fetch(USER_AGENT, url):
                raise RuntimeError("robots.txt 不允许抓取该 NIJ 页面。")
            if request_count:
                sleeper(effective_delay)
            request_count += 1
            return _read_bytes(active_client, url, MAX_HTML_BYTES)

        candidates: list[str] = []
        seen: set[str] = set()
        base = urlsplit(source.base_url)
        for page_number in range(max_pages):
            listing_url = base._replace(query=urlencode({"subtopic": "304581", "page": page_number})).geturl()
            _check_url(listing_url, source, listing=True)
            status, raw = get_page(listing_url)
            if status == 404:
                if page_number == 0:
                    raise RuntimeError("NIJ 技术文章列表不存在。")
                break
            stats["listing_pages"] += 1
            for url in _listing_urls(raw, listing_url, source):
                if url not in seen:
                    seen.add(url)
                    candidates.append(url)
        if not candidates:
            raise RuntimeError("NIJ 列表未解析出文章链接，页面结构可能已变化。")
        stats["listing_links"] = len(candidates)
        fresh = [url for url in candidates if url not in (known_urls or set())]
        stats["known_skipped"] = len(candidates) - len(fresh)
        stats["new_candidates"] = len(fresh)
        results: list[FetchedArticle] = []
        for url in fresh[:max_articles]:
            status, raw = get_page(url)
            if status == 404:
                continue
            stats["detail_pages"] += 1
            try:
                results.append(_article(raw, url))
            except RuntimeError:
                stats["detail_parse_failed"] += 1
        if not results and stats["detail_parse_failed"]:
            raise RuntimeError("NIJ 候选详情均未解析出可用正文，页面结构可能已变化。")
        return results

    if client is not None:
        return run(client)
    with httpx.Client(
        timeout=httpx.Timeout(connect=20, read=45, write=10, pool=8),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html, text/plain"},
    ) as new_client:
        return run(new_client)
