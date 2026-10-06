import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from http.server import ThreadingHTTPServer

from scripts.selection_review import ReviewStore, complete, database_id, make_handler


class SelectionReviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.input = root / "labels.jsonl"
        self.db = root / "articles.db"
        self.row = {
            "case_id": "case-one", "article_id": "article-one", "source_slug": "demo",
            "source_name": "示例", "source_type": "government", "title": "测试公告",
            "source_url": "https://example.org/one", "published_at": None,
            "split": "development",
            "gold": {"relevance": None, "select": None, "primary_topic": None,
                     "content_kind": None, "evidence_level": None, "reason": ""},
        }
        self.input.write_text(json.dumps(self.row, ensure_ascii=False) + "\n", encoding="utf-8")
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("CREATE TABLE articles (id TEXT, source_body TEXT, parse_status TEXT)")
            connection.execute("INSERT INTO articles VALUES (?, ?, ?)", ("article-one", "原文内容" * 2000, "full_text"))
            connection.commit()

    def tearDown(self):
        self.directory.cleanup()

    def test_saves_each_field_and_recovers_after_restart(self):
        store = ReviewStore(self.input, self.db)
        store.save_field("case-one", "relevance", "direct")
        self.assertEqual(ReviewStore(self.input, self.db).page(1)["cases"][0]["gold"]["relevance"], "direct")
        store.save_field("case-one", "select", "reject")
        store.save_field("case-one", "primary_topic", "policing")
        store.save_field("case-one", "content_kind", "deployment")
        store.save_field("case-one", "evidence_level", "announcement")
        result = store.save_field("case-one", "reason", "只宣布试点，未披露效果。")
        self.assertTrue(result["complete"])
        self.assertEqual(result["labeled"], 1)
        page = ReviewStore(self.input, self.db).page(1)
        self.assertEqual(page["labeled"], 1)
        self.assertEqual(len(page["cases"][0]["source_excerpt"]), 6000)
        self.assertTrue(page["cases"][0]["excerpt_truncated"])

    def test_rejects_invalid_field_or_choice_without_changing_file(self):
        store = ReviewStore(self.input, self.db)
        original = self.input.read_bytes()
        with self.assertRaises(ValueError):
            store.save_field("case-one", "source_url", "https://evil.example")
        with self.assertRaises(ValueError):
            store.save_field("case-one", "relevance", "not-an-option")
        with self.assertRaises(KeyError):
            store.save_field("missing", "relevance", "direct")
        self.assertEqual(self.input.read_bytes(), original)

    def test_irrelevant_needs_reject(self):
        gold = {"relevance": "irrelevant", "select": "select", "primary_topic": None,
                "content_kind": None, "evidence_level": "unknown", "reason": "无具体任务。"}
        self.assertFalse(complete(gold))
        gold["select"] = "reject"
        self.assertTrue(complete(gold))

    def test_database_uuid_normalization(self):
        self.assertEqual(database_id("40bc66b5-42ff-442d-8727-5970c28974b4"),
                         "40bc66b542ff442d87275970c28974b4")

    def test_proposal_is_not_gold_until_confirmed(self):
        proposal_file = Path(self.directory.name) / "proposals.json"
        suggested = {"relevance": "direct", "select": "reject", "primary_topic": "policing",
                     "content_kind": "deployment", "evidence_level": "announcement", "reason": "仅有试点公告。"}
        proposal_file.write_text(json.dumps([{"case_id": "case-one", "basis": "summary_only",
                                              "summary": "一则试点公告。", "gold": suggested}]), encoding="utf-8")
        store = ReviewStore(self.input, self.db, proposal_file)
        page = store.page(1)
        self.assertEqual(page["reviewed"], 0)
        self.assertEqual(page["cases"][0]["proposal"]["gold"], suggested)
        self.assertIsNone(page["cases"][0]["gold"]["relevance"])
        with self.assertRaises(ValueError):
            store.confirm_case("case-one", dict(suggested, reason=""))
        self.assertEqual(store.confirm_case("case-one", suggested)["reviewed"], 1)
        self.assertEqual(ReviewStore(self.input, self.db, proposal_file).page(1)["reviewed"], 1)
        self.assertEqual(store.save_field("case-one", "reason", "我修改了理由。 ")["reviewed"], 0)

    def test_http_page_and_origin_protected_save(self):
        store = ReviewStore(self.input, self.db)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, "test-token"))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/") as response:
                self.assertIn("人工标注工作台", response.read().decode("utf-8"))
            with urlopen(base + "/api/cases?page=1") as response:
                self.assertEqual(json.load(response)["total"], 1)
            data = json.dumps({"case_id": "case-one", "field": "relevance", "value": "direct"}).encode()
            headers = {"Content-Type": "application/json", "X-Review-Token": "test-token"}
            with self.assertRaises(HTTPError) as context:
                urlopen(Request(base + "/api/label", data=data, headers=headers, method="POST"))
            self.assertEqual(context.exception.code, 403)
            context.exception.close()
            headers["Origin"] = base
            with urlopen(Request(base + "/api/label", data=data, headers=headers, method="POST")) as response:
                self.assertEqual(json.load(response)["gold"]["relevance"], "direct")
            self.assertEqual(ReviewStore(self.input, self.db).page(1)["cases"][0]["gold"]["relevance"], "direct")
            confirmed = {"case_id": "case-one", "gold": {
                "relevance": "direct", "select": "reject", "primary_topic": "policing",
                "content_kind": "deployment", "evidence_level": "announcement", "reason": "只公布试点。",
            }}
            with urlopen(Request(base + "/api/confirm", data=json.dumps(confirmed).encode(),
                                 headers=headers, method="POST")) as response:
                self.assertEqual(json.load(response)["reviewed"], 1)
            self.assertEqual(ReviewStore(self.input, self.db).page(1)["reviewed"], 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
