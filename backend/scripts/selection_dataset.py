"""Prepare and validate a local, human-labeled selection benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
from urllib.parse import quote
from uuid import UUID


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = BACKEND_ROOT / "data" / "bluepulse-dev.db"
TOPICS = frozenset({
    "policing", "artificial-intelligence", "public-safety-tech",
    "cybersecurity", "policy-standards", "procurement-projects", "research",
})
RELEVANCE = frozenset({"direct", "potential", "irrelevant", "uncertain"})
SELECTION = frozenset({"select", "reject", "uncertain"})
CONTENT_KINDS = frozenset({
    "research", "equipment", "deployment", "policy", "industry", "procurement",
})
EVIDENCE_LEVELS = frozenset({
    "marketing", "announcement", "lab_test", "pilot_observation",
    "field_evaluation", "unknown",
})
GOLD_FIELDS = ("relevance", "select", "primary_topic", "content_kind", "evidence_level", "reason")
REDACTIONS = (
    re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    re.compile(r"(?<!\d)\d{3,4}[- ]?\d{7,8}(?!\d)"),
)


def _redact_title(title: str) -> str:
    for pattern in REDACTIONS:
        title = pattern.sub("[已遮盖]", title)
    return " ".join(title.split())[:500]


def _readonly_connection(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.resolve(strict=True)
    uri = f"file:{quote(resolved.as_posix(), safe='/:')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _holdout_ids(sampled: list[sqlite3.Row], seed: int) -> set[str]:
    """Keep each source represented while favoring rare processing outcomes."""
    def rank(row: sqlite3.Row) -> bytes:
        return hashlib.sha256(f"{seed}:{row['id']}".encode("utf-8")).digest()

    by_source: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in sampled:
        by_source[row["source_slug"]].append(row)
    chosen: set[str] = set()
    for source_rows in by_source.values():
        target = max(1, round(len(source_rows) / 5)) if len(source_rows) >= 2 else 0
        by_status: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for row in source_rows:
            by_status[row["processing_status"]].append(row)
        for status in sorted(by_status, key=lambda key: (len(by_status[key]), key))[:target]:
            chosen.add(min(by_status[status], key=rank)["id"])
        remaining = sorted((row for row in source_rows if row["id"] not in chosen), key=rank)
        selected_here = sum(row["id"] in chosen for row in source_rows)
        chosen.update(row["id"] for row in remaining[:target - selected_here])
    global_target = max(1, math.ceil(len(sampled) / 5)) if sampled else 0
    if len(chosen) < global_target:
        remaining = sorted((row for row in sampled if row["id"] not in chosen), key=rank)
        chosen.update(row["id"] for row in remaining[:global_target - len(chosen)])
    return chosen


def export_candidates(db_path: Path, output: Path, limit: int = 150, seed: int = 20261001) -> dict[str, object]:
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    with closing(_readonly_connection(db_path)) as connection:
        rows = connection.execute("""
            SELECT a.id, a.source_title, a.source_url, a.published_at,
                   a.processing_status, s.slug AS source_slug, s.name AS source_name,
                   s.source_type
              FROM articles AS a JOIN sources AS s ON s.id = a.source_id
             WHERE a.deleted_at IS NULL
             ORDER BY a.first_seen_at DESC, a.id
        """).fetchall()

    groups: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        groups[(row["source_slug"], row["processing_status"])].append(row)
    rng = random.Random(seed)
    for group in groups.values():
        rng.shuffle(group)

    sampled: list[sqlite3.Row] = []
    while len(sampled) < limit and any(groups.values()):
        for key in sorted(groups):
            if groups[key] and len(sampled) < limit:
                sampled.append(groups[key].pop())

    holdout_ids = _holdout_ids(sampled, seed)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        for row in sampled:
            article_id = str(UUID(str(row["id"])))
            record = {
                "case_id": article_id,
                "article_id": article_id,
                "source_slug": row["source_slug"],
                "source_name": row["source_name"],
                "source_type": row["source_type"],
                "title": _redact_title(row["source_title"]),
                "source_url": row["source_url"],
                "published_at": row["published_at"],
                "split": "holdout" if row["id"] in holdout_ids else "development",
                "gold": {field: ("" if field == "reason" else None) for field in GOLD_FIELDS},
            }
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {
        "exported": len(sampled),
        "holdout": len(holdout_ids),
        "sources": dict(sorted(Counter(row["source_slug"] for row in sampled).items())),
        "output": str(output),
    }


def subset_candidates(input_path: Path, output: Path, limit: int = 40) -> dict[str, object]:
    """Create a smaller pilot without changing existing development/holdout assignments."""
    if not 5 <= limit <= 500:
        raise ValueError("limit must be between 5 and 500")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    rows = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len({row["case_id"] for row in rows}) != len(rows):
        raise ValueError("input contains duplicate case IDs")
    if len(rows) < limit or any(row.get("split") not in {"development", "holdout"} for row in rows):
        raise ValueError("input has too few cases or invalid splits")
    if any(any(value not in (None, "") for value in row["gold"].values()) for row in rows):
        raise ValueError("subset source must be unlabeled; do not silently discard labels")
    holdout_target = math.ceil(limit / 5)
    holdouts = [row for row in rows if row["split"] == "holdout"]
    developments = [row for row in rows if row["split"] == "development"]
    if len(holdouts) < holdout_target or len(developments) < limit - holdout_target:
        raise ValueError("input lacks enough cases in one split")
    source_names = sorted({row["source_slug"] for row in rows})
    chosen_holdout: set[str] = set()
    for source in source_names:
        candidate = next((row for row in holdouts if row["source_slug"] == source), None)
        if candidate and len(chosen_holdout) < holdout_target:
            chosen_holdout.add(candidate["case_id"])
    for row in holdouts:
        if len(chosen_holdout) >= holdout_target:
            break
        chosen_holdout.add(row["case_id"])
    chosen_dev = {row["case_id"] for row in developments[:limit - holdout_target]}
    selected = [row for row in rows if row["case_id"] in chosen_holdout or row["case_id"] in chosen_dev]
    if len(selected) != limit:
        raise ValueError("could not construct the requested subset")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        for row in selected:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"exported": len(selected), "holdout": len(chosen_holdout),
            "sources": dict(sorted(Counter(row["source_slug"] for row in selected).items())),
            "output": str(output)}


def select_candidates(input_path: Path, output: Path, ids_path: Path) -> dict[str, object]:
    """Select an explicit review queue, preserving all existing labels and splits."""
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    wanted = [line.strip() for line in ids_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not wanted or len(wanted) != len(set(wanted)):
        raise ValueError("case ID list is empty or contains duplicates")
    rows = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    available = {row["case_id"]: row for row in rows}
    if len(available) != len(rows) or any(case_id not in available for case_id in wanted):
        raise ValueError("source has duplicate IDs or requested case IDs are missing")
    touched = {
        row["case_id"] for row in rows
        if any(value not in (None, "") for value in row["gold"].values())
    }
    if not touched.issubset(wanted):
        raise ValueError("selection would omit cases with existing annotations")
    selected = [available[case_id] for case_id in wanted]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        for row in selected:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"exported": len(selected),
            "holdout": sum(row["split"] == "holdout" for row in selected),
            "preserved_partial": len(touched),
            "sources": dict(sorted(Counter(row["source_slug"] for row in selected).items())),
            "output": str(output)}


def validate_dataset(input_path: Path) -> dict[str, object]:
    errors: list[str] = []
    seen: set[str] = set()
    total = labeled = pending = holdout = 0
    with input_path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            total += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_number}: invalid JSON ({exc.msg})")
                continue
            if not isinstance(record, dict):
                errors.append(f"line {line_number}: expected an object")
                continue
            case_id = record.get("case_id")
            if not isinstance(case_id, str) or not case_id:
                errors.append(f"line {line_number}: missing case_id")
            elif case_id in seen:
                errors.append(f"line {line_number}: duplicate case_id {case_id}")
            else:
                seen.add(case_id)
            if record.get("split") not in {"development", "holdout"}:
                errors.append(f"line {line_number}: invalid split")
            if record.get("split") == "holdout":
                holdout += 1
            gold = record.get("gold")
            if not isinstance(gold, dict) or any(field not in gold for field in GOLD_FIELDS):
                errors.append(f"line {line_number}: missing gold fields")
                continue
            if all(gold[field] in (None, "") for field in GOLD_FIELDS):
                pending += 1
                continue
            labeled += 1
            relevance = gold["relevance"]
            selection = gold["select"]
            topic = gold["primary_topic"]
            kind = gold["content_kind"]
            evidence = gold["evidence_level"]
            reason = gold["reason"]
            if not isinstance(relevance, str) or relevance not in RELEVANCE:
                errors.append(f"line {line_number}: invalid relevance")
            if not isinstance(selection, str) or selection not in SELECTION:
                errors.append(f"line {line_number}: invalid select")
            if relevance == "irrelevant" and selection != "reject":
                errors.append(f"line {line_number}: irrelevant must be reject")
            if relevance in ("direct", "potential") and (
                not isinstance(topic, str) or topic not in TOPICS
                or not isinstance(kind, str) or kind not in CONTENT_KINDS
            ):
                errors.append(f"line {line_number}: relevant cases need primary_topic and content_kind")
            if topic is not None and (not isinstance(topic, str) or topic not in TOPICS):
                errors.append(f"line {line_number}: unknown primary_topic")
            if kind is not None and (not isinstance(kind, str) or kind not in CONTENT_KINDS):
                errors.append(f"line {line_number}: unknown content_kind")
            if not isinstance(evidence, str) or evidence not in EVIDENCE_LEVELS:
                errors.append(f"line {line_number}: invalid evidence_level")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(f"line {line_number}: a labeled case needs reason")
    return {"total": total, "labeled": labeled, "pending": pending,
            "holdout": holdout, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="create a local labeling queue from SQLite")
    export.add_argument("--database", type=Path, default=DEFAULT_DB)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--limit", type=int, default=150)
    export.add_argument("--seed", type=int, default=20261001)
    validate = commands.add_parser("validate", help="check a JSONL labeling file")
    validate.add_argument("--input", type=Path, required=True)
    subset = commands.add_parser("subset", help="make an unlabeled pilot while preserving split assignments")
    subset.add_argument("--input", type=Path, required=True)
    subset.add_argument("--output", type=Path, required=True)
    subset.add_argument("--limit", type=int, default=40)
    select = commands.add_parser("select", help="create a smaller queue from explicit case IDs, preserving labels")
    select.add_argument("--input", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)
    select.add_argument("--ids-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "export":
            result = export_candidates(args.database, args.output, args.limit, args.seed)
        elif args.command == "subset":
            result = subset_candidates(args.input, args.output, args.limit)
        elif args.command == "select":
            result = select_candidates(args.input, args.output, args.ids_file)
        else:
            result = validate_dataset(args.input)
    except (FileNotFoundError, FileExistsError, OSError, sqlite3.Error, ValueError) as exc:
        parser.exit(2, f"selection dataset error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
