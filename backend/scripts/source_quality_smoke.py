"""Read-only RSS/API source check; never calls a model or writes the database."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from bluepulse_backend.ingestion.adapters import fetch_gdelt, fetch_openalex, fetch_rss
from bluepulse_backend.ingestion.govuk_api import fetch_govuk_api
from bluepulse_backend.models import Source


FETCHERS = {"rss": fetch_rss, "gdelt": fetch_gdelt, "openalex": fetch_openalex,
            "govuk_api": fetch_govuk_api}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="configured RSS/API source slug")
    args = parser.parse_args()
    config_path = Path(__file__).resolve().parents[1] / "config" / "sources.json"
    sources = json.loads(config_path.read_text(encoding="utf-8"))
    source_data = next((row for row in sources if row["slug"] == args.source), None)
    if source_data is None or source_data["adapter"] not in FETCHERS:
        parser.error("source must be a configured RSS or API source")
    try:
        articles = FETCHERS[source_data["adapter"]](Source(**source_data))
    except Exception as exc:
        print(json.dumps({"status": "failed", "source": args.source,
                          "error_type": type(exc).__name__, "message": str(exc)[:200]},
                         ensure_ascii=False))
        return 1
    print(json.dumps({
        "status": "ok", "source": args.source, "count": len(articles),
        "parse_status": dict(Counter(article.parse_status for article in articles)),
        "sample": [{"url": article.url, "title": article.title,
                    "published_at": article.published_at.isoformat() if article.published_at else None,
                    "body_chars": len(article.body or ""), "body_preview": (article.body or "")[:180],
                    "parse_status": article.parse_status}
                   for article in articles[:3]],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
