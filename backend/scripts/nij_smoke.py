from __future__ import annotations

import json
from pathlib import Path

from bluepulse_backend.ingestion.nij_html import fetch_nij_html
from bluepulse_backend.models import Source


def main() -> int:
    config_path = Path(__file__).resolve().parents[1] / "config" / "sources.json"
    sources = json.loads(config_path.read_text(encoding="utf-8"))
    source_data = next(item for item in sources if item["adapter"] == "nij_html")
    diagnostics: dict[str, int] = {}
    try:
        articles = fetch_nij_html(Source(**source_data), diagnostics=diagnostics)
    except Exception as exc:
        print(json.dumps({
            "status": "failed", "error_type": type(exc).__name__,
            "message": str(exc)[:200], "diagnostics": diagnostics,
        }, ensure_ascii=True))
        return 1
    print(json.dumps({
        "status": "ok", "count": len(articles), "diagnostics": diagnostics,
        "articles": [
            {
                "url": article.url, "title": article.title,
                "published_at": article.published_at.isoformat() if article.published_at else None,
                "body_length": len(article.body or ""), "parse_status": article.parse_status,
            }
            for article in articles
        ],
    }, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
