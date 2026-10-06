"""Read-only smoke test of the public NPCC news list and limited details."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bluepulse_backend.ingestion.npcc_html import fetch_npcc_html
from bluepulse_backend.models import Source


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.limit <= 3:
        parser.error("--limit must be between 1 and 3")
    config_path = Path(__file__).resolve().parents[1] / "config" / "sources.json"
    rows = json.loads(config_path.read_text(encoding="utf-8"))
    row = next(row for row in rows if row["slug"] == "npcc-policing-tech")
    row["config"]["max_articles"] = args.limit
    diagnostics: dict[str, int] = {}
    try:
        articles = fetch_npcc_html(Source(**row), diagnostics=diagnostics)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "message": str(exc)[:200], "diagnostics": diagnostics}, ensure_ascii=False))
        return 1
    print(json.dumps({
        "status": "ok", "diagnostics": diagnostics,
        "articles": [{"url": item.url, "title": item.title,
                      "published_at": item.published_at.isoformat() if item.published_at else None,
                      "body_chars": len(item.body or ""), "parse_status": item.parse_status}
                     for item in articles],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
