"""Bounded CCGP listing/detail collection. Analysis belongs to the pipeline."""
from __future__ import annotations

import re
import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from .live_sources import BoundedHTTP, SourceFetchError, listing_evidence, plain_text
from .pipeline import Candidate
from .source_listing import linked_pages


HOST = "www.ccgp.gov.cn"
LISTING = "https://www.ccgp.gov.cn/cggg/zygg/gkzb/"
LOCAL_LISTING = "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/"
NOTICE_PATHS = {
    "tender": "gkzb", "award": "zbgg", "transaction": "cjgg", "correction": "gzgg",
    "consultation": "jzxcs", "negotiation": "jzxtpgg", "termination": "fblbgg",
    "other-notice": "qtgg", "inquiry": "xjgg",
}
LISTING_ENTRIES = {
    f"{authority}-{notice}": f"https://{HOST}/cggg/{branch}/{path}/"
    for authority, branch in (("central", "zygg"), ("local", "dfgg"))
    for notice, path in NOTICE_PATHS.items()
}
USER_AGENT = "BluePulseResearch/0.1"
ARTICLE_PATH = re.compile(r"/cggg/(?:zygg|dfgg)/(?:" + "|".join(NOTICE_PATHS.values())
                          + r")/\d{6}/t\d{8}_\d+\.htm")
PAGER = re.compile(r"Pager\(\{\s*size:\s*(\d+),\s*current:\s*(\d+),\s*prefix:\s*'index',\s*suffix:\s*'htm'\s*\}\)")
DATE = re.compile(
    r"(?<!\d)(20\d{2})(?:年|[-/.])\s*(\d{1,2})(?:月|[-/.])\s*(\d{1,2})(?:日)?"
    r"(?:[T\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?(?!\d)"
)
PUBLICATION_LABEL = re.compile(r"(?:发布时间|公告时间|发布日期)\s*[:：]\s*")
NOTICE_PUBLICATION_LABEL = re.compile(r"^发布日期\s*[:：]\s*")
CHINA = timezone(timedelta(hours=8))
POLICE = ("公安", "警务", "交警", "交管", "交通执法", "刑侦", "检案", "治安", "边境管理",
          "边防检查", "边检", "缉私", "派出所", "乘警", "警察", "执法办案", "法医", "检察",
          "消防", "监狱", "公共安全", "平安县城", "人民法院", "应急管理", "减灾中心")
TECH = ("人工智能", "大模型", "智能", "信息化", "视频", "监控", "数据", "网络", "软件",
        "平台", "系统", "通信", "无人机", "机器人", "电子物证", "科技", "vpn", "音频",
        "算法", "研判", "电子证据", "电子取证", "痕迹检验", "信创", "服务器", "算力",
        "执法记录仪", "物联网", "识别", "定位", "对讲", "数字化", "数智", "车载终端",
        "电子卷宗", "液质联用仪", "设备升级", "指挥调度", "指挥中心", "指挥室", "通讯",
        "信息采集", "全景", "三维模型", "光缆", "零信任", "车载4g", "虚拟仿真", "安防", "分析设备")
POLICING_TECH = ("接处警", "电子警察", "情指行", "巡防处评", "辅助办案助手", "图像结构化",
                 "反诈系统", "数字化劝导站", "应急救援指挥", "智能应急救援")
ROUTINE_PURCHASE = ("办公家具", "食材采购", "食堂食材", "保洁服务", "绿化养护", "物业管理")
ASCII_AI = re.compile(r"(?<![a-z0-9])ai(?![a-z0-9])", re.I)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "wbr"}


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _valid_article_url(raw: str, base: str = LISTING) -> str | None:
    url = urljoin(base, raw)
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != HOST or parts.port not in (None, 443)
            or parts.username or parts.password or parts.query or parts.fragment
            or not ARTICLE_PATH.fullmatch(parts.path)):
        return None
    return url


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, str, str]] = []
        self.li_text: list[str] | None = None
        self.li_links: list[tuple[str, str]] = []
        self.anchor_url: str | None = None
        self.anchor_text: list[str] = []
        self.anchor_title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "li":
            self.li_text, self.li_links = [], []
        if tag == "a":
            values = dict(attrs)
            self.anchor_url = values.get("href")
            self.anchor_text = []
            self.anchor_title = values.get("title") or ""

    def handle_data(self, data: str) -> None:
        if self.li_text is not None:
            self.li_text.append(data)
        if self.anchor_url is not None:
            self.anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.anchor_url is not None:
            title = " ".join((self.anchor_title or "".join(self.anchor_text)).split())
            if title:
                if self.li_text is None:
                    self.items.append((self.anchor_url, title, title))
                else:
                    self.li_links.append((self.anchor_url, title))
            self.anchor_url, self.anchor_text = None, []
        if tag == "li" and self.li_text is not None:
            context = " ".join("".join(self.li_text).split())[:500]
            self.items.extend((url, title, context) for url, title in self.li_links)
            self.li_text, self.li_links = None, []


class _Detail(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.container_tag = ""
        self.done = False
        self.skip = 0
        self.row_cells = 0
        self.parts: list[str] = []
        self.heading_depth = 0
        self.heading: list[str] = []
        self.publication_depth = 0
        self.publication: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if attrs_map.get("id") == "pubTime":
            self.publication_depth = 1
        elif self.publication_depth and tag not in VOID:
            self.publication_depth += 1
        if not self.done and self.depth == 0 and (
            "vF_detail_content" in (attrs_map.get("class") or "").split()
            or attrs_map.get("id") in {"mycontent", "content", "Zoom"}
            or tag == "article"
        ):
            self.depth = 1
            self.container_tag = tag
            return
        if self.depth:
            if tag == self.container_tag:
                self.depth += 1
            if tag in {"script", "style", "noscript", "nav", "footer", "form"}:
                self.skip += 1
            if tag == "tr":
                self.row_cells = 0
            elif tag in {"td", "th"}:
                if self.row_cells:
                    self.parts.append(" | ")
                self.row_cells += 1
            if tag in {"p", "br", "li", "h2", "h3", "div", "tr"}:
                self.parts.append("\n")
        elif not self.heading and tag in {"h1", "h2"}:
            self.heading_depth = 1
        elif self.heading_depth and tag not in VOID:
            self.heading_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self.publication_depth and tag not in VOID:
            self.publication_depth -= 1
        if self.depth:
            if tag in {"script", "style", "noscript", "nav", "footer", "form"} and self.skip:
                self.skip -= 1
            if tag in {"p", "li", "h2", "h3", "div"}:
                self.parts.append("\n")
            if tag == self.container_tag:
                self.depth -= 1
                self.done = self.depth == 0
        elif self.heading_depth:
            self.heading_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.publication_depth:
            self.publication.append(data)
        if self.depth and not self.skip:
            self.parts.append(data)
        elif self.heading_depth:
            self.heading.append(data)


def _publication(text: str) -> tuple[datetime | None, date | None]:
    match = DATE.match(text.strip())
    if not match:
        return None, None
    year, month, day, hour, minute, second = match.groups()
    try:
        calendar_day = date(int(year), int(month), int(day))
        if hour is None:
            return None, calendar_day
        return datetime(int(year), int(month), int(day), int(hour), int(minute),
                        int(second or 0), tzinfo=CHINA).astimezone(UTC), None
    except ValueError:
        return None, None


def _listing_date(context: str) -> tuple[datetime | None, date | None]:
    label = PUBLICATION_LABEL.search(context)
    return _publication(context[label.end():]) if label else (None, None)


def _original_notice_date(body: str, title: str):
    first_lines = body.splitlines()
    if len(first_lines) < 2 or not title or "".join(first_lines[0].split()) != "".join(title.split()):
        return None, None
    label = NOTICE_PUBLICATION_LABEL.match(first_lines[1])
    return _publication(first_lines[1][label.end():]) if label else (None, None)


def _relevant_listing(title: str, context: str) -> bool:
    text = f"{title} {context}".casefold()
    if any(word in text for word in POLICING_TECH):
        return True
    if not any(word in text for word in POLICE):
        return False
    # A relevant buyer may put the technology only in its specification. Fetch the
    # notice unless its title clearly describes a routine purchase without technology.
    return (not any(word in title for word in ROUTINE_PURCHASE)
            or any(word in text for word in TECH) or bool(ASCII_AI.search(text)))


class CcgpAdapter:
    listing_entries = LISTING_ENTRIES

    def __init__(self, http: BoundedHTTP, *, max_items: int = 2,
                 request_delay_seconds: float = 1.0, sleeper: Callable[[float], None] = time.sleep):
        if not 1 <= max_items <= 5:
            raise ValueError("max_items_must_be_1_to_5")
        if request_delay_seconds < 0:
            raise ValueError("invalid_request_delay")
        self.http = http
        self.max_items = max_items
        self.request_delay_seconds = request_delay_seconds
        self.sleeper = sleeper
        self._policy: RobotFileParser | None = None
        self._delay = 0.0
        self._reset_diagnostics()

    def _reset_diagnostics(self) -> None:
        self.diagnostics = {"robots_unavailable": 0, "listing_links": 0, "topic_filtered": 0,
                            "detail_attempts": 0, "detail_parsed": 0,
                            "detail_failed": 0, "detail_skipped": 0}

    def _load_robots(self) -> None:
        try:
            robots = self.http.get(f"https://{HOST}/robots.txt", accept="text/plain")
        except SourceFetchError as exc:
            if exc.code != "http_404":
                raise
            # RFC 9309 treats a 4xx robots response as unavailable. Other errors fail closed.
            robots = b""
            self.diagnostics["robots_unavailable"] = 1
        policy = RobotFileParser()
        policy.parse(_decode(robots).splitlines())
        crawl_delay = policy.crawl_delay(USER_AGENT) or 0
        if crawl_delay > 10:
            raise SourceFetchError("robots_delay_exceeds_budget")
        self._policy, self._delay = policy, max(self.request_delay_seconds, float(crawl_delay))

    def _fetch(self, url: str) -> bytes:
        if self._policy is None:
            self._load_robots()
        if not self._policy.can_fetch(USER_AGENT, url):
            raise SourceFetchError("robots_disallowed")
        if getattr(self.http.client, "pulse_host_pace", None):
            self.http.delay_seconds = max(self.http.delay_seconds, self._delay)
        else:
            self.sleeper(self._delay)
        return self.http.get(url, accept="text/html,application/xhtml+xml;q=0.9")

    def _listing_candidates(self, html, page_url):
        links = _Links()
        links.feed(html)
        unique: dict[str, tuple[str, str]] = {}
        for raw_url, title, context in links.items:
            url = _valid_article_url(raw_url, page_url)
            if url and url not in unique:
                unique[url] = (title, context)
        self.diagnostics["listing_links"] += len(unique)
        if not unique:
            raise SourceFetchError("listing_no_article_links")
        dates = {url: _listing_date(context) for url, (_, context) in unique.items()}
        self.listing_page_evidence = listing_evidence(
            (instant or day for instant, day in dates.values()), ordered=True, local_zone=CHINA)
        matched = [item for item in unique.items() if _relevant_listing(*item[1])]
        self.diagnostics["topic_filtered"] += len(unique) - len(matched)
        return [Candidate(url=url, title=title, published_at=dates[url][0], published_date=dates[url][1],
                          language="zh") for url, (title, _) in matched]

    def list_candidates(self, *, first_import: bool = False) -> list[Candidate]:
        self._reset_diagnostics()
        self._policy = None
        return self._listing_candidates(_decode(self._fetch(LISTING)), LISTING)

    def iter_listing_pages(self, *, start=0):
        self._reset_diagnostics()
        self._policy = None

        def pager_links(html):
            if pager := PAGER.search(html):
                size, current = map(int, pager.groups())
                if current + 1 < size:
                    yield f"index_{current + 1}.htm"

        index = 0
        for entry in (LISTING, LOCAL_LISTING):
            archive = urlsplit(entry).path
            pages = linked_pages(entry, lambda url: _decode(self._fetch(url)), self._listing_candidates,
                                 lambda parts: not parts.query and re.fullmatch(
                                     re.escape(archive) + r"index_[1-9]\d*\.htm", parts.path),
                                 extra_links=pager_links)
            for items, following in pages:
                if index >= start:
                    checkpoint = index + 1 if following is not None or entry == LISTING else None
                    yield items, checkpoint
                index += 1

    def iter_entry_pages(self, entry, *, start=0):
        if entry not in self.listing_entries or start < 0:
            raise SourceFetchError("invalid_listing_offset")
        self._reset_diagnostics()
        archive = self.listing_entries[entry]
        index = start
        while True:
            url = archive if index == 0 else f"{archive}index_{index}.htm"
            html = _decode(self._fetch(url))
            pager = PAGER.search(html)
            size, current = map(int, pager.groups()) if pager else (None, None)
            if current is not None and (current != index or size <= current):
                raise SourceFetchError("invalid_listing_offset")
            items = self._listing_candidates(html, url)
            following = index + 1 if size is not None and index + 1 < size else None
            # The source's public category archive currently exposes at most 25 pages.
            self.listing_page_evidence["terminal"] = (
                "truncated" if size is None or size >= 25 else "exhausted") if following is None else None
            yield items, following
            if following is None:
                return
            index = following

    def fetch_detail(self, candidate: Candidate) -> Candidate:
        if not _valid_article_url(candidate.url):
            raise SourceFetchError("invalid_article_url")
        self.diagnostics["detail_attempts"] += 1
        try:
            html = _decode(self._fetch(candidate.url))
            detail = _Detail()
            detail.feed(html)
            body = "\n".join(line.strip() for line in "".join(detail.parts).splitlines() if line.strip())[:12000]
            if len(body) < 100:
                raise SourceFetchError("incomplete_article")
        except SourceFetchError:
            self.diagnostics["detail_failed"] += 1
            raise
        self.diagnostics["detail_parsed"] += 1
        title = " ".join("".join(detail.heading).split())[:500] or candidate.title
        instant, day = _publication("".join(detail.publication))
        if instant is None and day is None and not candidate.published_at and not candidate.published_date:
            # Legacy article headers put the date immediately before the source attribution.
            legacy = re.search(DATE.pattern + r"\s*来源\s*[:：]", plain_text(html, max_chars=3000))
            if legacy:
                instant, day = _publication(legacy[0])
        reprint_at = instant or candidate.published_at
        original_at, original_day = _original_notice_date(body, title)
        original_local_day = original_at.astimezone(CHINA).date() if original_at else original_day
        if reprint_at and original_local_day and original_local_day < reprint_at.astimezone(CHINA).date():
            return replace(candidate, title=title, body=body, published_at=original_at,
                           published_date=original_day, source_updated_at=reprint_at)
        if instant or day:
            return replace(candidate, title=title, body=body, published_at=instant, published_date=day)
        return replace(candidate, title=title, body=body)

    def candidates(self) -> list[Candidate]:
        results: list[Candidate] = []
        for listed in self.list_candidates()[:self.max_items * 3]:
            if len(results) >= self.max_items:
                break
            try:
                results.append(self.fetch_detail(listed))
            except SourceFetchError as exc:
                if exc.code in {"http_403", "http_429", "robots_disallowed"}:
                    raise
        self.diagnostics["detail_skipped"] = self.diagnostics["listing_links"] - self.diagnostics["detail_attempts"]
        if not results and self.diagnostics["detail_failed"]:
            raise SourceFetchError("detail_parse_or_fetch_failed")
        return results
