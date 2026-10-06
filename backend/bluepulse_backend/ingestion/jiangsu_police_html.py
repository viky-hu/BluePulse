"""Read public Jiangsu Public Security Department news without browser challenges."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone
from time import sleep
from typing import Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from bluepulse_backend.ingestion.adapters import FetchedArticle, USER_AGENT
from bluepulse_backend.models import Source

HOST = "gat.jiangsu.gov.cn"
LIST_PATH = "/col/col6372/index.html"
ARTICLE_PATH = re.compile(r"/art/\d{4}/\d{1,2}/\d{1,2}/art_6372_\d+\.html")
RECORD = re.compile(r"<record>\s*<!\[CDATA\[(.*?)\]\]>\s*</record>", re.I | re.S)
TECH_TITLE = re.compile(r"人工智能|大模型|智能|数智|无人机|机器人|科技|数字|算法|数据|视频|信息化|低空|AI|网络", re.I)
CHINA_TZ = timezone(timedelta(hours=8))
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_ROBOTS_BYTES = 256 * 1024


def _check_url(url: str, *, listing: bool) -> None:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != HOST or parsed.port not in {None, 443}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or (parsed.path != LIST_PATH if listing else not ARTICLE_PATH.fullmatch(parsed.path))):
        raise ValueError("江苏公安网站 URL 不在允许的 HTTPS 栏目范围内。")


def _read_bytes(client: httpx.Client, url: str, limit: int) -> tuple[int, bytes]:
    with client.stream("GET", url) as response:
        if response.is_redirect:
            raise RuntimeError("江苏公安页面发生重定向，未继续访问目标。")
        if response.status_code == 429:
            raise RuntimeError("江苏公安网站限流，未立即重试。")
        if response.status_code == 404:
            return 404, b""
        response.raise_for_status()
        declared = response.headers.get("content-length")
        if declared and int(declared) > limit:
            raise RuntimeError("江苏公安页面超过大小限制。")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > limit:
                raise RuntimeError("江苏公安页面超过大小限制。")
            chunks.append(chunk)
        body = b"".join(chunks)
        if b"__jsl_clearance" in body or b"captcha" in body.lower():
            raise RuntimeError("江苏公安网站要求交互式验证，未尝试绕过。")
        return response.status_code, body


def _robots_policy(client: httpx.Client) -> RobotFileParser:
    url = f"https://{HOST}/robots.txt"
    status, body = _read_bytes(client, url, MAX_ROBOTS_BYTES)
    policy = RobotFileParser()
    policy.set_url(url)
    policy.parse([] if status == 404 else body.decode("utf-8", errors="replace").splitlines())
    return policy


def _listing_urls(raw: bytes, base_url: str) -> list[tuple[str, str]]:
    text = raw.decode("utf-8", errors="replace")
    fragments = RECORD.findall(text)
    if not fragments:
        raise RuntimeError("江苏公安栏目未解析出列表记录，页面结构可能已变化。")
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for fragment in fragments:
        soup = BeautifulSoup(fragment, "html.parser")
        anchor = soup.select_one("a[href]")
        if anchor is None:
            continue
        url = urljoin(base_url, anchor["href"])
        try:
            _check_url(url, listing=False)
        except ValueError:
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())[:500]
        if url not in seen and title:
            seen.add(url)
            found.append((url, title))
    if not found:
        raise RuntimeError("江苏公安栏目未解析出允许的文章链接。")
    return found


def _article(raw: bytes, url: str) -> FetchedArticle:
    soup = BeautifulSoup(raw, "html.parser")
    heading = soup.select_one(".wzzw-title")
    content = soup.select_one(".wzzw-article")
    if heading is None or content is None:
        raise RuntimeError("江苏公安文章标题或正文未找到，页面结构可能已变化。")
    for element in content.select("script, style, noscript, form"):
        element.decompose()
    title = " ".join(heading.get_text(" ", strip=True).split())[:500]
    body = "\n".join(
        line for line in (" ".join(part.split()) for part in content.get_text("\n", strip=True).splitlines())
        if line
    )[:100_000]
    if not title or len(body) < 80:
        raise RuntimeError("江苏公安文章正文过短，可能是异常页面。")
    pub_meta = soup.select_one('meta[name="PubDate"]')
    published_at = None
    if pub_meta and pub_meta.get("content"):
        try:
            published_at = datetime.strptime(pub_meta["content"], "%Y-%m-%d %H:%M").replace(tzinfo=CHINA_TZ).astimezone(UTC)
        except ValueError:
            pass
    return FetchedArticle(
        url=url, title=title, body=body, published_at=published_at,
        language="zh", country_code="CN", parse_status="full_text",
    )


def fetch_jiangsu_police_html(
    source: Source,
    *,
    known_urls: set[str] | None = None,
    client: httpx.Client | None = None,
    sleeper: Callable[[float], None] = sleep,
    diagnostics: dict[str, int] | None = None,
) -> list[FetchedArticle]:
    _check_url(source.base_url, listing=True)
    if set(source.config.get("allowed_hosts", [])) != {HOST}:
        raise ValueError("江苏公安来源仅允许访问指定官方主机。")
    max_articles = min(max(int(source.config.get("max_articles", 6)), 1), 10)
    delay = max(float(source.config.get("request_delay_seconds", 2)), 1.0)
    stats = diagnostics if diagnostics is not None else {}
    stats.update({"listing_links": 0, "new_candidates": 0, "known_skipped": 0,
                  "detail_pages": 0, "detail_parse_failed": 0})

    def run(active_client: httpx.Client) -> list[FetchedArticle]:
        policy = _robots_policy(active_client)
        effective_delay = max(delay, float(policy.crawl_delay(USER_AGENT) or 0))
        request_count = 1

        def get_page(url: str) -> tuple[int, bytes]:
            nonlocal request_count
            if not policy.can_fetch(USER_AGENT, url):
                raise RuntimeError("robots.txt 不允许抓取该江苏公安页面。")
            if request_count:
                sleeper(effective_delay)
            request_count += 1
            return _read_bytes(active_client, url, MAX_HTML_BYTES)

        status, listing = get_page(source.base_url)
        if status == 404:
            raise RuntimeError("江苏公安警务动态栏目不存在。")
        candidates = _listing_urls(listing, source.base_url)
        stats["listing_links"] = len(candidates)
        fresh = [(url, title) for url, title in candidates if url not in (known_urls or set())]
        stats["known_skipped"] = len(candidates) - len(fresh)
        stats["new_candidates"] = len(fresh)
        # Spend the limited detail-fetch budget on technology-looking titles first.
        prioritized = sorted(enumerate(fresh), key=lambda pair: (not bool(TECH_TITLE.search(pair[1][1])), pair[0]))
        results: list[FetchedArticle] = []
        for _, (url, _) in prioritized[:max_articles]:
            status, raw = get_page(url)
            if status == 404:
                continue
            stats["detail_pages"] += 1
            try:
                results.append(_article(raw, url))
            except RuntimeError:
                stats["detail_parse_failed"] += 1
        if not results and stats["detail_parse_failed"]:
            raise RuntimeError("江苏公安候选详情均未解析出可用正文，页面结构可能已变化。")
        return results

    if client is not None:
        return run(client)
    with httpx.Client(
        timeout=httpx.Timeout(connect=20, read=45, write=10, pool=8),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html, text/plain"},
    ) as new_client:
        return run(new_client)
