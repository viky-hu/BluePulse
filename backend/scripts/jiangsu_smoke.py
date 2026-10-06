"""Read-only smoke test for the public Jiangsu police news list."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bluepulse_backend.ingestion.jiangsu_police_html import fetch_jiangsu_police_html
from bluepulse_backend.models import Source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.limit <= 6:
        parser.error("--limit must be between 1 and 6")
    config_path = Path(__file__).resolve().parents[1] / "config" / "sources.json"
    rows = json.loads(config_path.read_text(encoding="utf-8"))
    row = next(row for row in rows if row["slug"] == "jiangsu-police-news")
    row["config"]["max_articles"] = args.limit
    diagnostics: dict[str, int] = {}
    articles = fetch_jiangsu_police_html(Source(**row), diagnostics=diagnostics)
    print(json.dumps({
        "status": "ok", "diagnostics": diagnostics,
        "articles": [{"url": item.url, "title": item.title,
                      "published_at": item.published_at.isoformat() if item.published_at else None,
                      "body_chars": len(item.body or "")} for item in articles],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
