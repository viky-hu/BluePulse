"""Summarize bounded validation runs; repeat snapshots are excluded from ingest totals."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def summarize(directory: Path) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    reviews: dict[tuple[str, str, str], dict] = {}
    for path in sorted(directory.glob("baseline-*.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        day = run["run_at"][:10]
        for source in run["sources"]:
            mode = "longitudinal" if Path(run.get("database", "")).name == "observation.db" else "isolated"
            grouped[(day, source["source"])].append({**source, "_database_mode": mode})
    for path in sorted(directory.glob("review-*.json")):
        review = json.loads(path.read_text(encoding="utf-8"))
        day = review["run_at"][:10]
        for item in review["items"]:
            key = (day, item["source"], item["url"])
            if item.get("evidence_sufficient") is not None:
                reviews[key] = item
    output = []
    for (day, slug), runs in sorted(grouped.items()):
        status = Counter()
        ingest = Counter()
        for run in runs:
            status.update(run["body_status"])
            ingest.update((run["ingest_first"] or {}).get("discoveries", {}))
        assessed = [item for (review_day, source_slug, _), item in reviews.items()
                    if review_day == day and source_slug == slug]
        output.append({
            "day": day, "source": slug, "runs": len(runs),
            "database_modes": ",".join(sorted({run["_database_mode"] for run in runs})),
            "robots_statuses": ",".join(str(run["robots_status"]) for run in runs),
            "entry_statuses": ",".join(str(run.get("entry_status")) for run in runs),
            "discovered_max": max((run["diagnostics"].get("listing_links") or
                                   run["diagnostics"].get("sitemap_news_urls") or
                                   run["diagnostics"].get("feed_items") or
                                   run["diagnostics"].get("search_results") or
                                   run["diagnostics"].get("listing_items") or 0) for run in runs),
            "detail_attempts": sum(run["diagnostics"].get("detail_attempts", 0) for run in runs),
            "candidates": sum(run["candidate_count"] for run in runs),
            "empty_runs": sum(run["error_code"] is None and run["candidate_count"] == 0
                              for run in runs),
            "full_text": status["full_text"], "abstract_only": status["abstract_only"],
            "metadata_only": status["metadata_only"],
            "date_covered": sum(run["date_covered"] for run in runs),
            "new": ingest["new"], "revised": ingest["revised"],
            "duplicate": ingest["duplicate"], "rejected": ingest["rejected"],
            "same_snapshot_duplicate": sum((run["ingest_repeat_same_snapshot"] or {})
                                           .get("discoveries", {}).get("duplicate", 0) for run in runs),
            "reviewed_urls": len(assessed),
            "original_pages_checked": sum(item.get("page_checked") is True for item in assessed),
            "clean_body_confirmed": sum(item.get("body_clean") is True for item in assessed),
            "evidence_sufficient": sum(item["evidence_sufficient"] is True for item in assessed),
            "editorial_fit": sum(item.get("editorial_fit") is True for item in assessed),
            "errors": ",".join(run["error_code"] for run in runs if run["error_code"]),
            "seconds": round(sum(run["duration_seconds"] for run in runs), 2),
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data/source-validation")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = summarize(args.input_dir)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["day", "source"])
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]) if rows else ["day", "source"])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
