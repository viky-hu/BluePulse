"""Read the public NPCC releases listing and a few technology-relevant details."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from time import sleep
from typing import Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from bluepulse_backend.ingestion.adapters import FetchedArticle, USER_AGENT
from bluepulse_backend.models import Source

HOST = "news.npcc.police.uk"
LIST_PATH = "/releases"
DETAIL_PATH = re.compile(r"/releases/[a-z0-9-]+")
TECH_TITLE = re.compile(
    r"\b(?:AI|artificial intelligence|algorithm|automated|automation|biometric|"
    r"camera|cyber|data|digital|drone|facial recognition|fingerprint|"
    r"license plate recognition|ANPR|ALPR|online crime reporting|robot|"
    r"software|technology|video)\b", re.I,
)
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_ROBOTS_BYTES = 256 * 1024


def _check_url(url: str, *, listing: bool) -> None:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != HOST or parsed.port not in {None, 443}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or (parsed.path != LIST_PATH if listing else not DETAIL_PATH.fullmatch(parsed.path))):
        raise ValueError("NPCC URL is outside the allowed HTTPS news paths.")


def _read_bytes(client: httpx.Client, url: str, limit: int) -> tuple[int, bytes]:
    with client.stream("GET", url) as response:
        if response.is_redirect:
            raise RuntimeError("NPCC redirected the request; target was not followed.")
        if response.status_code == 429:
            raise RuntimeError("NPCC returned HTTP 429; request was not retried.")
        if response.headers.get("x-amzn-waf-action", "").lower() in {"challenge", "captcha", "block"}:
            raise RuntimeError("NPCC requires an interactive access challenge.")
        if response.status_code == 404:
            return 404, b""
        response.raise_for_status()
        declared = response.headers.get("content-length")
        if declared and int(declared) > limit:
            raise RuntimeError("NPCC response exceeded the size limit.")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > limit:
                raise RuntimeError("NPCC response exceeded the size limit.")
            chunks.append(chunk)
        return response.status_code, b"".join(chunks)


def _robots_policy(client: httpx.Client) -> RobotFileParser:
    url = f"https://{HOST}/robots.txt"
    status, raw = _read_bytes(client, url, MAX_ROBOTS_BYTES)
    policy = RobotFileParser()
    policy.set_url(url)
    policy.parse([] if status == 404 else raw.decode("utf-8", errors="replace").splitlines())
    return policy


def _listing_candidates(raw: bytes, base_url: str) -> list[tuple[str, str, datetime | None]]:
    soup = BeautifulSoup(raw, "html.parser")
    candidates: list[tuple[str, str, datetime | None]] = []
    seen: set[str] = set()
    for anchor in soup.select("a.card__link[href]"):
        url = urljoin(base_url, anchor["href"])
        try:
            _check_url(url, listing=False)
        except ValueError:
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())[:500]
        card = anchor.find_parent(class_="card__body")
        summary = card.select_one(".card__summary") if card else None
        date_node = card.select_one(".card__date") if card else None
        teaser = f"{title} {summary.get_text(' ', strip=True) if summary else ''}"
        if not title or not TECH_TITLE.search(teaser) or url in seen:
            continue
        published_at = _parse_date(date_node.get_text(" ", strip=True)) if date_node else None
        seen.add(url)
        candidates.append((url, title, published_at))
    return candidates


def _parse_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value.strip(), "%d %b %Y").replace(tzinfo=UTC)
    except ValueError:
        return None


def _article(raw: bytes, url: str, listed_date: datetime | None) -> FetchedArticle:
    soup = BeautifulSoup(raw, "html.parser")
    heading = soup.select_one("h1.content-title")
    content = soup.select_one(".content-body")
    if heading is None or content is None:
        raise RuntimeError("NPCC detail title or body was not found.")
    for element in content.select("script, style, noscript, nav, footer, aside, form"):
        element.decompose()
    title = " ".join(heading.get_text(" ", strip=True).split())[:500]
    paragraphs = [" ".join(node.get_text(" ", strip=True).split())
                  for node in content.select("p, h2, h3, li")]
    body = "\n\n".join(part for part in paragraphs if len(part) >= 20)[:100_000]
    if not title or len(body) < 120:
        raise RuntimeError("NPCC detail body is too short to publish.")
    date_node = soup.select_one("p.date")
    published_at = _parse_date(date_node.get_text(" ", strip=True)) if date_node else None
    return FetchedArticle(url=url, title=title, body=body,
                          published_at=published_at or listed_date,
                          language="en", country_code="GB", parse_status="full_text")


def fetch_npcc_html(
    source: Source,
    *,
    known_urls: set[str] | None = None,
    client: httpx.Client | None = None,
    sleeper: Callable[[float], None] = sleep,
    diagnostics: dict[str, int] | None = None,
    now: datetime | None = None,
) -> list[FetchedArticle]:
    _check_url(source.base_url, listing=True)
    if set(source.config.get("allowed_hosts", [])) != {HOST}:
        raise ValueError("NPCC source must use only its official news host.")
    max_articles = min(max(int(source.config.get("max_articles", 3)), 1), 8)
    max_age_days = min(max(int(source.config.get("max_age_days", 90)), 1), 365)
    delay = max(float(source.config.get("request_delay_seconds", 1)), 1.0)
    stats = diagnostics if diagnostics is not None else {}
    stats.update({"listing_links": 0, "new_candidates": 0, "known_skipped": 0,
                  "detail_pages": 0, "detail_parse_failed": 0})

    def run(active_client: httpx.Client) -> list[FetchedArticle]:
        policy = _robots_policy(active_client)
        effective_delay = max(delay, float(policy.crawl_delay(USER_AGENT) or 0))
        if not policy.can_fetch(USER_AGENT, source.base_url):
            raise RuntimeError("robots.txt does not allow the NPCC listing.")
        sleeper(effective_delay)
        status, listing = _read_bytes(active_client, source.base_url, MAX_HTML_BYTES)
        if status == 404:
            raise RuntimeError("NPCC releases listing was not found.")
        stats["listing_links"] = len(BeautifulSoup(listing, "html.parser").select("a.card__link[href]"))
        if not stats["listing_links"]:
            raise RuntimeError("NPCC listing contained no release links; page structure may have changed.")
        candidates = _listing_candidates(listing, source.base_url)
        cutoff = (now or datetime.now(UTC)) - timedelta(days=max_age_days)
        fresh = [(url, date) for url, _, date in candidates
                 if url not in (known_urls or set()) and date and date >= cutoff]
        stats["known_skipped"] = sum(url in (known_urls or set()) for url, _, _ in candidates)
        stats["new_candidates"] = len(fresh)
        results: list[FetchedArticle] = []
        for url, listed_date in fresh[:max_articles]:
            if not policy.can_fetch(USER_AGENT, url):
                continue
            sleeper(effective_delay)
            status, raw = _read_bytes(active_client, url, MAX_HTML_BYTES)
            if status == 404:
                continue
            stats["detail_pages"] += 1
            try:
                results.append(_article(raw, url, listed_date))
            except RuntimeError:
                stats["detail_parse_failed"] += 1
        if not results and stats["detail_parse_failed"]:
            raise RuntimeError("NPCC candidate details contained no usable body.")
        return results

    if client is not None:
        return run(client)
    with httpx.Client(
        timeout=httpx.Timeout(connect=20, read=45, write=10, pool=8),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html, text/plain"},
    ) as new_client:
        return run(new_client)
