from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.selection_dataset import export_candidates, select_candidates, subset_candidates, validate_dataset


class SelectionDatasetTests(unittest.TestCase):
    def test_export_is_read_only_redacts_contact_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "articles.db"
            output = root / "candidates.jsonl"
            with closing(sqlite3.connect(database)) as connection:
                connection.executescript("""
                    CREATE TABLE sources (id TEXT PRIMARY KEY, slug TEXT, name TEXT, source_type TEXT);
                    CREATE TABLE articles (
                        id TEXT PRIMARY KEY, source_id TEXT, source_title TEXT, source_url TEXT,
                        published_at TEXT, processing_status TEXT, first_seen_at TEXT, deleted_at TEXT
                    );
                    INSERT INTO sources VALUES ('s1', 'gov', 'Government', 'government');
                    INSERT INTO sources VALUES ('s2', 'research', 'Research', 'academic');
                    INSERT INTO articles VALUES (
                        '00000000000000000000000000000001', 's1', '试点联系人 13812345678',
                        'https://example.org/pilot', '2026-09-01', 'processed', '2026-09-01', NULL
                    );
                    INSERT INTO articles VALUES (
                        '00000000000000000000000000000002', 's2', '音频伪造检测研究',
                        'https://example.org/audio', '2026-09-02', 'pending_model', '2026-09-02', NULL
                    );
                    INSERT INTO articles VALUES (
                        '00000000000000000000000000000003', 's1', '采购公告',
                        'https://example.org/procurement', '2026-09-03', 'irrelevant', '2026-09-03', NULL
                    );
                    INSERT INTO articles VALUES (
                        '00000000000000000000000000000004', 's2', '视频分析研究',
                        'https://example.org/video', '2026-09-04', 'processed', '2026-09-04', NULL
                    );
                """)

            result = export_candidates(database, output)
            self.assertEqual(result["exported"], 4)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual({row["source_slug"] for row in rows}, {"gov", "research"})
            self.assertEqual({row["split"] for row in rows}, {"holdout", "development"})
            self.assertEqual({row["source_slug"] for row in rows if row["split"] == "holdout"},
                             {"gov", "research"})
            self.assertNotIn("13812345678", output.read_text(encoding="utf-8"))
            self.assertNotIn("processing_status", rows[0])
            self.assertEqual(validate_dataset(output)["pending"], 4)
            with self.assertRaises(FileExistsError):
                export_candidates(database, output)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0], 4)

    def test_complete_examples_and_invalid_labels(self) -> None:
        example = Path(__file__).resolve().parents[2] / "docs" / "selection-gold.example.jsonl"
        self.assertEqual(validate_dataset(example)["errors"], [])
        self.assertEqual(validate_dataset(example)["labeled"], 5)
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid = Path(temp_dir) / "invalid.jsonl"
            record = json.loads(example.read_text(encoding="utf-8").splitlines()[0])
            record["gold"]["relevance"] = ["direct"]
            record["gold"]["primary_topic"] = ["policing"]
            invalid.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            result = validate_dataset(invalid)
            self.assertTrue(any("invalid relevance" in error for error in result["errors"]))
            self.assertTrue(any("unknown primary_topic" in error for error in result["errors"]))

    def test_subset_preserves_original_split_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.jsonl"
            output = Path(temp_dir) / "pilot.jsonl"
            records = []
            for number in range(15):
                records.append({
                    "case_id": str(number), "source_slug": "a" if number % 2 else "b",
                    "split": "holdout" if number < 5 else "development",
                    "gold": {"relevance": None},
                })
            source.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
            result = subset_candidates(source, output, 10)
            selected = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(result["exported"], 10)
            self.assertEqual(result["holdout"], 2)
            self.assertEqual({row["case_id"]: row["split"] for row in selected},
                             {row["case_id"]: row["split"] for row in records
                              if row["case_id"] in {item["case_id"] for item in selected}})
            with self.assertRaises(FileExistsError):
                subset_candidates(source, output, 10)

    def test_explicit_selection_preserves_partial_annotation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source, output, ids = (root / name for name in ("source.jsonl", "pilot.jsonl", "ids.txt"))
            records = [
                {"case_id": "one", "source_slug": "a", "split": "holdout", "gold": {"relevance": "direct"}},
                {"case_id": "two", "source_slug": "b", "split": "development", "gold": {"relevance": None}},
                {"case_id": "three", "source_slug": "b", "split": "development", "gold": {"relevance": None}},
            ]
            source.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
            ids.write_text("two\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "existing annotations"):
                select_candidates(source, output, ids)
            self.assertFalse(output.exists())
            ids.write_text("one\ntwo\n", encoding="utf-8")
            result = select_candidates(source, output, ids)
            self.assertEqual((result["exported"], result["preserved_partial"]), (2, 1))
            selected = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(selected[0]["gold"], {"relevance": "direct"})


if __name__ == "__main__":
    unittest.main()
