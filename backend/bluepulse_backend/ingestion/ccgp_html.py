from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from time import sleep
from typing import Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from bluepulse_backend.ingestion.adapters import FetchedArticle, USER_AGENT
from bluepulse_backend.ingestion.llm import ModelAnalysisError, analyze_notice, load_model_config
from bluepulse_backend.ingestion.model_adapter import model_adapter_from_config
from bluepulse_backend.models import Source

MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_ROBOTS_BYTES = 256 * 1024
ARTICLE_PATH = re.compile(r"^/cggg/(?:zygg|dfgg)/gkzb/\d{6}/t\d{8}_\d+\.htm$")
LISTING_PATH = re.compile(r"^/cggg/(?:zygg|dfgg)/gkzb/(?:index(?:_\d+)?\.htm)?$")
DATE_PATTERN = re.compile(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日\s*(\d{1,2}):(\d{2})")
POLICING_TERMS = ("公安", "警务", "交警", "刑侦", "治安", "边境管理", "警察", "公共安全")
TECH_TERMS = (
    "人工智能", "大模型", "智能", "信息化", "视频", "监控", "数据", "网络", "软件",
    "平台", "系统", "通信", "无人机", "机器人", "安全边界", "电子物证", "科技",
)


@dataclass(frozen=True)
class Candidate:
    url: str
    title: str
    listing_context: str = ""


def _validate_url(url: str, source: Source, path_pattern: re.Pattern[str]) -> None:
    parsed = urlsplit(url)
    allowed_hosts = set(source.config.get("allowed_hosts", []))
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.hostname.lower() not in allowed_hosts
        or parsed.username or parsed.password or parsed.port not in {None, 443}
        or not path_pattern.fullmatch(parsed.path) or parsed.query or parsed.fragment
    ):
        raise ValueError("采购网 URL 不在配置允许的 HTTPS 页面范围内。")


def _read_bytes(client: httpx.Client, url: str, limit: int) -> tuple[int, bytes]:
    with client.stream("GET", url) as response:
        if response.is_redirect:
            raise RuntimeError("采购网页面发生重定向，未继续访问目标。")
        if response.status_code == 404:
            return 404, b""
        response.raise_for_status()
        declared = response.headers.get("content-length")
        if declared and int(declared) > limit:
            raise RuntimeError("采购网页面超过大小限制。")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > limit:
                raise RuntimeError("采购网页面超过大小限制。")
            chunks.append(chunk)
        return response.status_code, b"".join(chunks)


def _robots_policy(client: httpx.Client, source: Source) -> RobotFileParser:
    parsed = urlsplit(source.base_url)
    robots_url = f"https://{parsed.hostname}/robots.txt"
    status, body = _read_bytes(client, robots_url, MAX_ROBOTS_BYTES)
    policy = RobotFileParser()
    policy.set_url(robots_url)
    if status == 404:
        policy.parse([])
    else:
        policy.parse(body.decode("utf-8", errors="replace").splitlines())
    return policy


def _candidates(raw_html: bytes, listing_url: str, source: Source) -> list[Candidate]:
    soup = BeautifulSoup(raw_html, "html.parser")
    found: list[Candidate] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(listing_url, anchor["href"])
        try:
            _validate_url(url, source, ARTICLE_PATH)
        except ValueError:
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())
        if title and url not in seen:
            container = anchor.find_parent("li")
            context = " ".join(container.get_text(" ", strip=True).split())[:500] if container else title
            found.append(Candidate(url, title, context))
            seen.add(url)
    return found


def _published_at(text: str) -> datetime | None:
    match = DATE_PATTERN.search(text)
    if not match:
        return None
    try:
        return datetime(*map(int, match.groups()), tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(UTC)
    except ValueError:
        return None


def _article_text(raw_html: bytes, fallback_title: str) -> tuple[str, str, datetime | None]:
    soup = BeautifulSoup(raw_html, "html.parser")
    for element in soup.select("script, style, noscript, nav, footer, form"):
        element.decompose()
    heading = soup.find(["h1", "h2"])
    title = " ".join(heading.get_text(" ", strip=True).split()) if heading else fallback_title
    if not title or len(title) > 500:
        title = fallback_title
    timestamp = _published_at(soup.get_text(" ", strip=True)[:3000])
    content = (
        soup.select_one(".vF_detail_content, #mycontent, #content, #Zoom, article, main")
        or soup.body or soup
    )
    lines = (" ".join(line.split()) for line in content.get_text("\n", strip=True).splitlines())
    body = "\n".join(line for line in lines if line)[:100_000]
    if len(body) < 100:
        raise RuntimeError("采购网公告正文过短，可能是异常页面。")
    return title, body, timestamp


def _looks_relevant(title: str, body: str) -> bool:
    sample = f"{title} {body[:2000]}"
    return any(term in sample for term in POLICING_TERMS) and any(
        term in sample for term in TECH_TERMS
    )


def fetch_ccgp_html(
    source: Source,
    *,
    known_urls: set[str] | None = None,
    client: httpx.Client | None = None,
    sleeper: Callable[[float], None] = sleep,
    diagnostics: dict[str, int] | None = None,
    analyze: bool = True,
) -> list[FetchedArticle]:
    _validate_url(source.base_url, source, LISTING_PATH)
    listing_urls = source.config.get("listing_urls", [source.base_url])
    if not isinstance(listing_urls, list) or not listing_urls:
        raise ValueError("采购网来源缺少受控的 listing_urls。")
    for listing_url in listing_urls:
        _validate_url(listing_url, source, LISTING_PATH)

    max_candidates = min(max(int(source.config.get("max_candidates", 12)), 1), 30)
    max_articles = min(max(int(source.config.get("max_articles", 4)), 1), 10)
    max_model_calls = min(max(int(source.config.get("max_model_calls", 6)), 1), 10)
    max_listing_pages = min(max(int(source.config.get("max_listing_pages", 1)), 1), 10)
    delay = max(float(source.config.get("request_delay_seconds", 2)), 1.0)
    model_config = load_model_config() if analyze else None
    model_adapter = (
        model_adapter_from_config(model_config, notice_analyzer=analyze_notice)
        if model_config is not None else None
    )
    stats = diagnostics if diagnostics is not None else {}
    stats.update({
        "listing_links": 0,
        "listing_pages": 0,
        "new_candidates": 0,
        "candidate_limit": max_candidates,
        "detail_pages": 0,
        "detail_parse_failed": 0,
        "keyword_filtered": 0,
        "model_calls": 0,
        "model_rejected": 0,
        "model_failed": 0,
    })

    def run(active_client: httpx.Client) -> list[FetchedArticle]:
        policy = _robots_policy(active_client, source)
        robot_delay = policy.crawl_delay(USER_AGENT)
        effective_delay = max(delay, float(robot_delay or 0))
        request_count = 1  # robots.txt was the first request

        def get_page(url: str) -> tuple[int, bytes]:
            nonlocal request_count
            if not policy.can_fetch(USER_AGENT, url):
                raise RuntimeError("robots.txt 不允许抓取配置的采购网页面。")
            if request_count:
                sleeper(effective_delay)
            request_count += 1
            return _read_bytes(active_client, url, MAX_HTML_BYTES)

        candidates: list[Candidate] = []
        seen: set[str] = set()
        for listing_url in listing_urls:
            for page_number in range(max_listing_pages):
                page_url = (
                    listing_url if page_number == 0
                    else urljoin(listing_url, f"index_{page_number}.htm")
                )
                _validate_url(page_url, source, LISTING_PATH)
                status, raw = get_page(page_url)
                if status == 404:
                    if page_number == 0:
                        raise RuntimeError("采购网公告列表不存在。")
                    break
                stats["listing_pages"] += 1
                for candidate in _candidates(raw, page_url, source):
                    if candidate.url not in seen:
                        candidates.append(candidate)
                        seen.add(candidate.url)
        if not candidates:
            raise RuntimeError("采购网公告列表未解析出文章链接，页面结构可能已变化。")
        stats["listing_links"] = len(candidates)

        ranked = sorted(
            (item for item in candidates if item.url not in (known_urls or set())),
            key=lambda item: (
                not (any(term in item.listing_context for term in POLICING_TERMS)
                     and any(term in item.listing_context for term in TECH_TERMS)),
                not any(term in item.listing_context for term in POLICING_TERMS),
            ),
        )
        stats["new_candidates"] = len(ranked)
        results: list[FetchedArticle] = []
        model_calls = 0
        model_available = model_config is not None
        for candidate in ranked[:max_candidates]:
            if len(results) >= max_articles:
                break
            status, raw = get_page(candidate.url)
            if status == 404:
                continue
            stats["detail_pages"] += 1
            try:
                title, body, published_at = _article_text(raw, candidate.title)
            except RuntimeError:
                stats["detail_parse_failed"] += 1
                continue
            if not _looks_relevant(title, body):
                stats["keyword_filtered"] += 1
                continue

            analysis = None
            processing_status = "pending_model"
            if model_config is not None and model_available and model_calls < max_model_calls:
                model_calls += 1
                stats["model_calls"] += 1
                try:
                    analysis = model_adapter.analyze_notice(candidate.url, title, body)
                    processing_status = "processed"
                except ModelAnalysisError:
                    processing_status = "model_failed"
                    model_available = False
                    stats["model_failed"] += 1
            if analysis is not None and not analysis.relevant:
                stats["model_rejected"] += 1
                continue
            results.append(FetchedArticle(
                url=candidate.url,
                title=title,
                published_at=published_at,
                body=body,
                language="zh",
                country_code="CN",
                parse_status="full_text",
                zh_title=analysis.short_title or title if analysis else title,
                zh_summary=analysis.summary or None if analysis else None,
                topic_slugs=analysis.topics if analysis else ("policing", "procurement-projects"),
                importance_score=analysis.importance_score if analysis else 0,
                relevance=analysis.relevance if analysis else None,
                featured_candidate=analysis.featured_candidate if analysis else False,
                featured_reason=analysis.featured_reason or None if analysis else None,
                processing_status=processing_status,
            ))
        if not results and stats["detail_parse_failed"]:
            raise RuntimeError("采购网候选详情均未解析出可用正文，页面结构可能已变化。")
        return results

    if client is not None:
        return run(client)
    with httpx.Client(
        timeout=httpx.Timeout(connect=20, read=45, write=10, pool=8),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html, text/plain"},
    ) as new_client:
        return run(new_client)
