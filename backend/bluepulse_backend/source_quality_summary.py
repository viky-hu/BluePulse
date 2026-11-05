"""Summarize human topic reviews over distinct URLs, separate from fetch reliability."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from .pipeline import canonical_url
from .source_collection import SOURCES


TOPIC_FIT = {"direct", "adjacent", "off"}


def summarize(directory: Path, *, as_of: date, run_from: date | None = None,
              run_to: date | None = None, new_only: bool = False) -> tuple[list[dict], list[dict]]:
    materials: dict[tuple[str, str], dict] = {}
    first_seen: dict[tuple[str, str], date] = {}
    discovered: dict[str, int] = defaultdict(int)
    for path in sorted(directory.glob("baseline-*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        run_date = date.fromisoformat(report["run_at"][:10])
        in_window = not ((run_from and run_date < run_from) or (run_to and run_date > run_to))
        for source in report["sources"]:
            slug = source["source"]
            metrics = source.get("diagnostics") or {}
            count = max((metrics.get(key) or 0 for key in
                         ("listing_links", "sitemap_news_urls", "feed_items", "search_results", "listing_items")),
                        default=0)
            if in_window:
                discovered[slug] = max(discovered[slug], count)
            for item in source["items"]:
                url = canonical_url(item["url"], [SOURCES[slug].host])
                key = (slug, url)
                first_seen[key] = min(first_seen.get(key, run_date), run_date)
                if in_window:
                    materials[key] = {**item, "url": url}
    if new_only:
        materials = {key: value for key, value in materials.items()
                     if (run_from is None or first_seen[key] >= run_from)
                     and (run_to is None or first_seen[key] <= run_to)}

    reviews: dict[tuple[str, str], dict] = defaultdict(dict)
    for path in sorted(directory.glob("review-*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        for item in report["items"]:
            slug = item["source"]
            url = canonical_url(item["url"], [SOURCES[slug].host])
            current = reviews[(slug, url)]
            for field in ("topic_fit", "evidence_sufficient", "editorial_fit",
                          "page_checked", "body_clean", "note"):
                if item.get(field) is not None and (field != "note" or item[field]):
                    current[field] = (current.get(field, False) or item[field]
                                      if field == "page_checked" else item[field])

    by_source: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for key, material in materials.items():
        by_source[key[0]].append((material, reviews.get(key, {})))

    rows = []
    for slug in SOURCES:
        sample = by_source[slug]
        reviewed = [(item, review) for item, review in sample
                    if review.get("topic_fit") in TOPIC_FIT]
        direct = [(item, review) for item, review in reviewed
                  if review["topic_fit"] == "direct"]
        recent_direct = 0
        future = 0
        for item, review in reviewed:
            raw_date = item.get("published_date") or (item.get("published_at") or "")[:10]
            if not raw_date:
                continue
            age = (as_of - date.fromisoformat(raw_date)).days
            if age < 0:
                future += 1
            if 0 <= age <= 60 and review["topic_fit"] == "direct":
                recent_direct += 1
        rows.append({
            "source": slug, "discovered_max": discovered[slug],
            "unique_sampled": len(sample), "reviewed": len(reviewed),
            "direct": len(direct),
            "adjacent": sum(review["topic_fit"] == "adjacent" for _, review in reviewed),
            "off": sum(review["topic_fit"] == "off" for _, review in reviewed),
            "direct_evidence": sum(review.get("evidence_sufficient") is True for _, review in direct),
            "recent_direct_60d": recent_direct,
            "future_dated": future,
            "editorial_fit": sum(review.get("editorial_fit") is True for _, review in reviewed),
            "original_pages_checked": sum(review.get("page_checked") is True for _, review in reviewed),
        })
    details = [{"source": slug, "url": url, "title": item["title"],
                "first_seen": first_seen[(slug, url)].isoformat(),
                "published_date": item.get("published_date") or (item.get("published_at") or "")[:10],
                "body_chars": item["body_chars"], **reviews.get((slug, url), {})}
               for (slug, url), item in sorted(materials.items())]
    return rows, details


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data/source-validation")
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now().astimezone().date())
    parser.add_argument("--run-from", type=date.fromisoformat,
                        help="include runs on or after this observation date")
    parser.add_argument("--run-to", type=date.fromisoformat,
                        help="include runs on or before this observation date")
    parser.add_argument("--new-only", action="store_true",
                        help="exclude URLs first observed before the run date window")
    parser.add_argument("--output-csv", type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    if args.run_from and args.run_to and args.run_from > args.run_to:
        parser.error("--run-from must not exceed --run-to")
    rows, details = summarize(args.input_dir, as_of=args.as_of,
                              run_from=args.run_from, run_to=args.run_to, new_only=args.new_only)
    by_url: dict[str, set[str]] = defaultdict(set)
    by_title: dict[str, set[str]] = defaultdict(set)
    for item in details:
        by_url[item["url"]].add(item["source"])
        by_title[" ".join(item["title"].casefold().split())].add(item["source"])
    overlaps = {"unique_urls_across_sources": len(by_url),
                "cross_source_urls": sorted(url for url, sources in by_url.items() if len(sources) > 1),
                "cross_source_same_titles": sorted(title for title, sources in by_title.items()
                                                   if len(sources) > 1)}
    if args.output_csv:
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps({"as_of": args.as_of.isoformat(),
                                                "run_from": args.run_from.isoformat() if args.run_from else None,
                                                "run_to": args.run_to.isoformat() if args.run_to else None,
                                                "new_only": args.new_only,
                                                "sources": rows,
                                                "overlaps": overlaps, "items": details},
                                               ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
    if not args.output_csv and not args.output_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
