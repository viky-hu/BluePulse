"""Read-only API smoke: public list -> detail -> original source link."""

from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx
from fastapi.testclient import TestClient

from bluepulse_backend.api import create_app


class _PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.heading_parts: list[str] = []
        self.reading_page = False
        self.in_heading = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.reading_page = self.reading_page or any(key == "data-reading-page" for key, _ in attrs)
        if self.reading_page and tag == "h1":
            self.in_heading = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self.in_heading = False

    def handle_data(self, data: str) -> None:
        if self.in_heading:
            self.heading_parts.append(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="jiangsu-police-news", help="configured source slug")
    parser.add_argument("--frontend-url", help="optional running local frontend, e.g. http://127.0.0.1:3000")
    args = parser.parse_args()
    with TestClient(create_app()) as client:
        sources_response = client.get("/api/v1/sources")
        sources_response.raise_for_status()
        sources = sources_response.json()["items"]
        source = next((item for item in sources if item["slug"] == args.source), None)
        if source is None:
            raise RuntimeError(f"公开来源不存在：{args.source}")
        listing_response = client.get("/api/v1/articles", params={
            "period": "all", "sort": "recent", "source": source["id"], "limit": 1,
        })
        listing_response.raise_for_status()
        items = listing_response.json()["items"]
        if not items:
            raise RuntimeError(f"来源暂无可公开文章：{args.source}")
        card = items[0]
        detail_response = client.get(f"/api/v1/articles/{card['id']}")
        detail_response.raise_for_status()
        detail = detail_response.json()
        original = urlsplit(detail["url"])
        if (detail["id"] != card["id"] or detail["source"]["slug"] != args.source
                or original.scheme != "https" or not original.hostname):
            raise RuntimeError("文章列表、详情或原站链接不一致。")
        edition_response = client.get("/api/v1/home/featured")
        edition_response.raise_for_status()
        edition = edition_response.json()
        for entry in edition["items"]:
            candidate = entry["article"]
            if client.get(f"/api/v1/articles/{candidate['id']}").status_code != 200:
                raise RuntimeError("精选包含无法打开详情的文章。")
            if not entry.get("featured_reason"):
                raise RuntimeError("精选缺少值得关注的理由。")
        frontend_checked = False
        if args.frontend_url:
            frontend = urlsplit(args.frontend_url)
            if frontend.scheme != "http" or frontend.hostname not in {"127.0.0.1", "localhost"}:
                raise ValueError("--frontend-url 仅接受本机 HTTP 地址。")
            page_url = f"{args.frontend_url.rstrip('/')}/articles/{detail['id']}"
            with httpx.Client(timeout=20, trust_env=False) as browser:
                page_response = browser.get(page_url)
                page_response.raise_for_status()
            parsed = _PageText()
            parsed.feed(page_response.text)
            if not parsed.reading_page or detail["title"] not in "".join(parsed.heading_parts):
                raise RuntimeError("前端详情页未呈现同一篇文章的标题。")
            frontend_checked = True
        print(json.dumps({
            "status": "ok", "source": args.source, "article_id": detail["id"],
            "published_at": detail["published_at"], "parse_status": detail["parse_status"],
            "has_summary": bool(detail.get("summary")), "has_source_body": bool(detail.get("source_body")),
            "original_host": original.hostname, "featured_count": len(edition["items"]),
            "frontend_checked": frontend_checked,
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
