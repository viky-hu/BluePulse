"""Check first and last extracted text spans against retained original responses."""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from .ccgp_source import _decode
from .europol_source import DATA_MARKER
from .live_sources import plain_text


def _flat(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def compare(directory: Path) -> list[dict]:
    latest = {}
    for report in sorted(directory.glob("baseline-*.json")):
        data = json.loads(report.read_text(encoding="utf-8"))
        for source in data["sources"]:
            if source["items"] and source["items"][0].get("raw_page_file"):
                latest[source["source"]] = source
    result = []
    for slug, source in sorted(latest.items()):
        item = source["items"][0]
        raw = _decode(Path(item["raw_page_file"]).read_bytes())
        if slug == "govuk":
            raw = (json.loads(raw).get("details") or {}).get("body") or ""
        if slug == "europol-news":
            start = raw.index(DATA_MARKER) + len(DATA_MARKER)
            end = raw.index(";</script>", start)
            node = json.loads(raw[start:end])["NodeLoader"]["node"]
            raw = str(node.get("introduction") or "") + "\n" + str(node.get("body") or "")
        # This generic text view is only an audit aid; it does not replace the
        # source-specific article parser or prove that middle paragraphs are complete.
        original = _flat(plain_text(raw, max_chars=1_000_000))
        body = _flat(item["body"] or "")
        start, end = body[:45], body[-45:]
        paragraphs = [_flat(part) for part in (item["body"] or "").splitlines()
                      if len(_flat(part)) >= 40]
        result.append({"source": slug, "url": item["url"], "body_chars": len(body),
                       "start_in_original": bool(start and start in original),
                       "end_in_original": bool(end and end in original),
                       "paragraphs_matched": sum(part in original for part in paragraphs),
                       "paragraphs_checked": len(paragraphs),
                       "raw_page_file": item["raw_page_file"]})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data/source-validation")
    args = parser.parse_args()
    print(json.dumps(compare(args.input_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
