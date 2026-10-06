"""Read-only model replay against confirmed selection labels; never edits gold or articles."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from contextlib import closing
from pathlib import Path
from uuid import UUID

from bluepulse_backend.ingestion.llm import (
    ModelAnalysisError, analyze_notice, analyze_source_article, load_model_config,
)
from scripts.selection_dataset import DEFAULT_DB, _readonly_connection

DEFAULT_GOLD = Path(__file__).resolve().parents[1] / "data" / "selection-pilot-20.jsonl"


def replay(*, gold_path: Path = DEFAULT_GOLD, db_path: Path = DEFAULT_DB,
           split: str = "development", limit: int = 15, offset: int = 0) -> dict[str, object]:
    model_config = load_model_config()
    if model_config is None:
        raise RuntimeError("模型服务未配置；无法进行只读回放。")
    rows = [json.loads(line) for line in gold_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    results: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    eligible_index = 0
    with closing(_readonly_connection(db_path)) as db:
        for number, case in enumerate(rows, 1):
            if case["split"] != split or case.get("review_status") != "confirmed":
                continue
            eligible_index += 1
            if eligible_index <= offset:
                continue
            if len(results) >= limit:
                break
            article_id = UUID(case["article_id"]).hex
            article = db.execute(
                "SELECT a.source_url, a.source_title, a.source_body, a.parse_status, "
                "s.adapter, s.source_type FROM articles a JOIN sources s ON s.id=a.source_id "
                "WHERE a.id=?", (article_id,),
            ).fetchone()
            if article is None:
                results.append({"number": number, "status": "missing_article"})
                counts["missing_article"] += 1
                continue
            try:
                if article["adapter"] == "ccgp_html":
                    predicted = analyze_notice(article["source_url"], article["source_title"],
                                               article["source_body"] or "", model_config)
                else:
                    predicted = analyze_source_article(
                        article["source_url"], article["source_title"], article["source_body"],
                        article["source_type"], article["parse_status"], model_config,
                    )
            except ModelAnalysisError as exc:
                results.append({"number": number, "status": "model_failed", "error": str(exc)[:160]})
                counts["model_failed"] += 1
                continue
            expected_relevant = case["gold"]["relevance"] in {"direct", "potential"}
            expected_featured = case["gold"]["select"] == "select"
            relevant_ok = predicted.relevant == expected_relevant
            featured_ok = predicted.featured_candidate == expected_featured
            counts["relevance_correct" if relevant_ok else "relevance_wrong"] += 1
            counts["featured_correct" if featured_ok else "featured_wrong"] += 1
            results.append({
                "number": number,
                "status": "ok",
                "expected_relevant": expected_relevant,
                "predicted_relevant": predicted.relevant,
                "expected_featured": expected_featured,
                "predicted_featured": predicted.featured_candidate,
                "importance_score": predicted.importance_score,
                "featured_reason": predicted.featured_reason or None,
            })
    return {"split": split, "offset": offset, "cases": len(results),
            "counts": dict(counts), "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--split", choices=("development", "holdout"), default="development")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.limit <= 20:
        parser.error("--limit must be between 1 and 20")
    if not 0 <= args.offset < 20:
        parser.error("--offset must be between 0 and 19")
    print(json.dumps(replay(gold_path=args.gold, db_path=args.db, split=args.split,
                            limit=args.limit, offset=args.offset), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
