"""Preview or apply confirmed local labels as durable editorial overrides."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from bluepulse_backend.db import create_database_engine
from bluepulse_backend.ingestion.pipeline import refresh_featured
from bluepulse_backend.models import Article
from scripts.selection_dataset import validate_dataset

DEFAULT_GOLD = Path(__file__).resolve().parents[1] / "data" / "selection-pilot-20.jsonl"


def apply_confirmed_gold(session: Session, gold_path: Path, *, apply: bool = False) -> dict[str, object]:
    check = validate_dataset(gold_path)
    if check["errors"] or check["pending"] or check["labeled"] != check["total"]:
        raise ValueError(f"标注文件未完成或无效：{check}")
    cases = [json.loads(line) for line in gold_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(case.get("review_status") != "confirmed" for case in cases):
        raise ValueError("仅能导入全部已确认的人工标注。")
    changes: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    applied_at = datetime.now(UTC)
    for number, case in enumerate(cases, 1):
        article = session.get(Article, UUID(case["article_id"]))
        if article is None:
            raise ValueError(f"第 {number} 条标注对应的文章不存在；没有写入任何改动。")
        if article.editorial_case_id not in (None, case["case_id"]):
            raise ValueError(f"第 {number} 条已有另一人工决定；拒绝覆盖。")
        gold = case["gold"]
        expected = (
            gold["relevance"], gold["select"], gold["reason"].strip(), case["case_id"],
        )
        current = (
            article.editorial_relevance, article.editorial_select,
            article.editorial_reason, article.editorial_case_id,
        )
        changed = current != expected
        if gold["relevance"] in {"irrelevant", "uncertain"}:
            counts["withheld_by_human"] += 1
        elif article.processing_status != "processed":
            counts["relevant_but_unprocessed"] += 1
        else:
            counts["public_relevant"] += 1
        if gold["select"] == "select" and article.processing_status == "processed":
            counts["human_featured_candidate"] += 1
        if changed:
            counts["changed"] += 1
            changes.append({
                "number": number,
                "relevance": gold["relevance"],
                "select": gold["select"],
                "model_status": article.processing_status,
                "model_featured_candidate": article.featured_candidate,
            })
            if apply:
                article.editorial_relevance = expected[0]
                article.editorial_select = expected[1]
                article.editorial_reason = expected[2]
                article.editorial_case_id = expected[3]
                article.editorial_applied_at = applied_at
        else:
            counts["unchanged"] += 1
    if apply and counts["changed"]:
        session.flush()
        refresh_featured(session)
    for key in ("changed", "unchanged", "withheld_by_human", "relevant_but_unprocessed",
                "public_relevant", "human_featured_candidate"):
        counts.setdefault(key, 0)
    return {"mode": "apply" if apply else "preview", "total": len(cases),
            "counts": dict(counts), "changes": changes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--apply", action="store_true", help="persist overrides after preview")
    args = parser.parse_args()
    engine = create_database_engine()
    try:
        with Session(engine) as session:
            result = apply_confirmed_gold(session, args.gold, apply=args.apply)
            if args.apply:
                session.commit()
            print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
