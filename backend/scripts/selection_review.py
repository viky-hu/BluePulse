"""Loopback-only review UI for the local selection-labeling JSONL file."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sqlite3
import tempfile
import threading
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from scripts.selection_dataset import (
    BACKEND_ROOT, CONTENT_KINDS, DEFAULT_DB, EVIDENCE_LEVELS, GOLD_FIELDS,
    RELEVANCE, SELECTION, TOPICS, _readonly_connection,
)

DEFAULT_INPUT = BACKEND_ROOT / "data" / "selection-pilot-20.jsonl"
DEFAULT_PROPOSALS = BACKEND_ROOT / "config" / "selection-proposals-20.json"
PAGE = Path(__file__).with_name("selection_review.html")
ENUMS = {
    "relevance": RELEVANCE,
    "select": SELECTION,
    "primary_topic": TOPICS,
    "content_kind": CONTENT_KINDS,
    "evidence_level": EVIDENCE_LEVELS,
}


def database_id(article_id: str) -> str:
    """SQLAlchemy stores UUIDs as compact hexadecimal values in SQLite."""
    try:
        return UUID(article_id).hex
    except ValueError:
        return article_id


def load_records(path: Path) -> list[dict]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(isinstance(row, dict) and isinstance(row.get("gold"), dict) for row in records):
        raise ValueError("标注文件格式不正确。")
    ids = [row.get("case_id") for row in records]
    if not all(isinstance(case_id, str) and case_id for case_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("标注文件的 case_id 缺失或重复。")
    return records


def complete(gold: dict) -> bool:
    relevance = gold.get("relevance")
    selection = gold.get("select")
    if relevance not in RELEVANCE or selection not in SELECTION:
        return False
    if relevance == "irrelevant" and selection != "reject":
        return False
    if relevance in {"direct", "potential"} and (
        gold.get("primary_topic") not in TOPICS or gold.get("content_kind") not in CONTENT_KINDS
    ):
        return False
    if gold.get("primary_topic") is not None and gold["primary_topic"] not in TOPICS:
        return False
    if gold.get("content_kind") is not None and gold["content_kind"] not in CONTENT_KINDS:
        return False
    return gold.get("evidence_level") in EVIDENCE_LEVELS and bool(str(gold.get("reason") or "").strip())


class ReviewStore:
    def __init__(self, input_path: Path, db_path: Path, proposals_path: Path | None = DEFAULT_PROPOSALS):
        self.path = input_path.resolve(strict=True)
        self.db_path = db_path.resolve(strict=True)
        self.rows = load_records(self.path)
        self.by_id = {row["case_id"]: row for row in self.rows}
        proposals = json.loads(proposals_path.read_text(encoding="utf-8")) if proposals_path and proposals_path.exists() else []
        self.proposals = {row["case_id"]: row for row in proposals}
        if len(self.proposals) != len(proposals):
            raise ValueError("建议稿包含重复案例 ID。")
        self.lock = threading.Lock()

    def page(self, number: int, size: int = 8) -> dict:
        count = len(self.rows)
        pages = max(1, (count + size - 1) // size)
        if not 1 <= number <= pages:
            raise ValueError("页码不存在。")
        with self.lock:
            rows = [dict(row, gold=dict(row["gold"])) for row in self.rows[(number - 1) * size:number * size]]
            labeled = sum(complete(row["gold"]) for row in self.rows)
            reviewed = sum(row.get("review_status") == "confirmed" for row in self.rows)
        ids = [database_id(row["article_id"]) for row in rows if row.get("article_id")]
        bodies = {}
        if ids:
            with closing(_readonly_connection(self.db_path)) as connection:
                placeholders = ",".join("?" for _ in ids)
                query = f"SELECT id, source_body, parse_status FROM articles WHERE id IN ({placeholders})"
                bodies = {row["id"]: row for row in connection.execute(query, ids)}
        for row in rows:
            article = bodies.get(database_id(row["article_id"])) if row.get("article_id") else None
            body = article["source_body"] if article else None
            row["source_excerpt"] = body[:6000] if body else None
            row["excerpt_truncated"] = bool(body and len(body) > 6000)
            row["parse_status"] = article["parse_status"] if article else "unknown"
            row["complete"] = complete(row["gold"])
            row["proposal"] = self.proposals.get(row["case_id"])
            row["conflicts"] = [
                field for field in GOLD_FIELDS
                if row["proposal"] and row["gold"].get(field) not in (None, "")
                and row["gold"][field] != row["proposal"]["gold"].get(field)
            ]
        return {"page": number, "pages": pages, "total": count, "labeled": labeled,
                "reviewed": reviewed, "cases": rows}

    def save_field(self, case_id: str, field: str, value: object) -> dict:
        if field not in GOLD_FIELDS:
            raise ValueError("未知标注字段。")
        if field == "reason":
            if not isinstance(value, str) or len(value) > 2000:
                raise ValueError("理由须为不超过 2000 字的文本。")
        elif value is not None and value not in ENUMS[field]:
            raise ValueError("选项不在允许范围内。")
        with self.lock:
            row = self.by_id.get(case_id)
            if row is None:
                raise KeyError("案例不存在。")
            previous = row["gold"].get(field)
            previous_review = row.get("review_status")
            row["gold"][field] = value
            if previous != value:
                row["review_status"] = "pending"
            try:
                self._write_atomic()
            except OSError:
                row["gold"][field] = previous
                if previous_review is None:
                    row.pop("review_status", None)
                else:
                    row["review_status"] = previous_review
                raise
            return {"case_id": case_id, "gold": dict(row["gold"]), "complete": complete(row["gold"]),
                    "labeled": sum(complete(item["gold"]) for item in self.rows),
                    "reviewed": sum(item.get("review_status") == "confirmed" for item in self.rows),
                    "review_status": row.get("review_status")}

    def confirm_case(self, case_id: str, gold: dict) -> dict:
        if not isinstance(gold, dict) or set(gold) != set(GOLD_FIELDS):
            raise ValueError("标注字段不完整。")
        for field, allowed in ENUMS.items():
            if gold[field] is not None and gold[field] not in allowed:
                raise ValueError(f"{field} 的选项无效。")
        if not isinstance(gold["reason"], str) or len(gold["reason"]) > 2000 or not complete(gold):
            raise ValueError("请先补齐必填项、理由及相关性判断。")
        with self.lock:
            row = self.by_id.get(case_id)
            if row is None:
                raise KeyError("案例不存在。")
            previous_gold, previous_review = row["gold"], row.get("review_status")
            row["gold"] = dict(gold)
            row["review_status"] = "confirmed"
            try:
                self._write_atomic()
            except OSError:
                row["gold"] = previous_gold
                if previous_review is None:
                    row.pop("review_status", None)
                else:
                    row["review_status"] = previous_review
                raise
            return {"case_id": case_id, "gold": dict(gold), "complete": True,
                    "labeled": sum(complete(item["gold"]) for item in self.rows),
                    "reviewed": sum(item.get("review_status") == "confirmed" for item in self.rows),
                    "review_status": "confirmed"}

    def _write_atomic(self) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", dir=self.path.parent,
                prefix=".selection-review-", suffix=".tmp", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                for row in self.rows:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def make_handler(store: ReviewStore, token: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, data: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'nonce-" + token + "'; style-src 'nonce-" + token + "'; connect-src 'self'; img-src 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status: int, body: dict) -> None:
            self._send(status, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path == "/":
                page = PAGE.read_text(encoding="utf-8").replace("__NONCE__", token)
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/api/cases":
                try:
                    from urllib.parse import parse_qs
                    number = int(parse_qs(parsed.query).get("page", ["1"])[0])
                    self._json(200, store.page(number))
                except (ValueError, sqlite3.Error, OSError) as exc:
                    self._json(400, {"error": str(exc)})
            else:
                self._json(404, {"error": "未找到页面。"})

        def do_POST(self) -> None:
            origin = self.headers.get("Origin")
            if (
                self.path not in {"/api/label", "/api/confirm"}
                or origin != f"http://127.0.0.1:{self.server.server_port}"
                or self.headers.get("X-Review-Token") != token
                or self.headers.get("Content-Type") != "application/json"
            ):
                self._json(403, {"error": "仅允许从本机标注页面提交。"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("请求内容过大或为空。")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("请求格式不正确。")
                if self.path == "/api/label" and set(data) == {"case_id", "field", "value"}:
                    result = store.save_field(data["case_id"], data["field"], data["value"])
                elif self.path == "/api/confirm" and set(data) == {"case_id", "gold"}:
                    result = store.confirm_case(data["case_id"], data["gold"])
                else:
                    raise ValueError("请求格式不正确。")
                self._json(200, result)
            except (ValueError, TypeError, json.JSONDecodeError, KeyError) as exc:
                self._json(400, {"error": str(exc)})
            except OSError as exc:
                self._json(500, {"error": f"写入失败：{exc}"})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--proposals", type=Path, default=DEFAULT_PROPOSALS)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    store = ReviewStore(args.input, args.database, args.proposals)
    token = secrets.token_urlsafe(24)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store, token))
    print(f"本地标注页面：http://127.0.0.1:{server.server_port}/", flush=True)
    print(f"数据文件：{store.path}；按 Ctrl+C 结束。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
