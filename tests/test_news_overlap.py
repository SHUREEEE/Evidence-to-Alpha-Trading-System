from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from evidence_alpha.cli import main as cli_main
from evidence_alpha.models import ContractError
from evidence_alpha.news_overlap import (
    FileFingerprint,
    build_news_overlap_audit,
)


RAW_TITLE = "RAW-TITLE-MUST-NOT-LEAK"
RAW_BODY = "RAW-BODY-MUST-NOT-LEAK"
RAW_URL = "https://raw-news-must-not-leak.invalid/article"


def _database(
    path: Path,
    *,
    event_count: int = 1,
    published_at: str = "2024-06-01 08:00:00",
    first_seen: str = "2024-06-01 09:00:00",
    last_seen: str = "2024-06-01 09:30:00",
    generated_at: str = "2024-06-01 10:05:00",
    data_cutoff_at: str = "2024-06-01 10:00:00",
) -> Path:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE event_cluster (
                id TEXT PRIMARY KEY,
                is_demo INTEGER NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                title TEXT,
                body TEXT
            );
            CREATE TABLE report (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                generated_at TEXT NOT NULL,
                data_cutoff_at TEXT NOT NULL,
                content_json TEXT
            );
            CREATE TABLE event_article (
                event_id TEXT NOT NULL,
                article_id TEXT NOT NULL
            );
            CREATE TABLE article (
                id TEXT PRIMARY KEY,
                published_at TEXT,
                canonical_url TEXT,
                title TEXT
            );
            """
        )
        for index in range(event_count):
            event_id = f"SECRET-EVENT-{index:03d}"
            article_id = f"SECRET-ARTICLE-{index:03d}"
            connection.execute(
                "INSERT INTO event_cluster VALUES (?, 0, ?, ?, ?, ?)",
                (event_id, first_seen, last_seen, RAW_TITLE, RAW_BODY),
            )
            connection.execute(
                "INSERT INTO report VALUES (?, ?, 1, ?, ?, ?)",
                (
                    f"SECRET-REPORT-{index:03d}",
                    event_id,
                    generated_at,
                    data_cutoff_at,
                    json.dumps({"body": RAW_BODY}),
                ),
            )
            connection.execute(
                "INSERT INTO event_article VALUES (?, ?)",
                (event_id, article_id),
            )
            connection.execute(
                "INSERT INTO article VALUES (?, ?, ?, ?)",
                (article_id, published_at, RAW_URL, RAW_TITLE),
            )
        connection.commit()
    finally:
        connection.close()
    return path


def _audit(database: Path, **overrides: object) -> dict[str, object]:
    arguments = {
        "factor_coverage_start": "2024-01-01",
        "adjusted_price_coverage_end": "2024-12-31",
        "minimum_event_count": 30,
        "oos_fraction": 0.30,
        "minimum_oos_events": 10,
    }
    arguments.update(overrides)
    return build_news_overlap_audit(database, **arguments)


class NewsOverlapAuditTests(unittest.TestCase):
    def test_31_historical_events_clear_exact_primary_and_oos_math(self):
        with tempfile.TemporaryDirectory() as directory:
            database = _database(Path(directory) / "news.db", event_count=31)
            before_hash = sha256(database.read_bytes()).hexdigest()
            before_mtime = database.stat().st_mtime_ns

            report = _audit(database)

            self.assertEqual(report["decision"], "COHORT_CANDIDATE")
            self.assertEqual(
                report["counts"]["causally_observed_overlap_events"], 31
            )
            self.assertEqual(report["counts"]["chronological_oos_events"], 10)
            self.assertEqual(
                report["thresholds"]["minimum_total_events_required"], 31
            )
            self.assertEqual(sha256(database.read_bytes()).hexdigest(), before_hash)
            self.assertEqual(database.stat().st_mtime_ns, before_mtime)
            self.assertTrue(report["read_safety"]["query_only"])
            self.assertTrue(report["read_safety"]["input_unchanged"])

    def test_30_events_fail_when_30_percent_oos_rounds_to_9(self):
        with tempfile.TemporaryDirectory() as directory:
            report = _audit(_database(Path(directory) / "news.db", event_count=30))

            self.assertEqual(report["decision"], "INSUFFICIENT_CAUSAL_OVERLAP")
            self.assertEqual(report["counts"]["chronological_oos_events"], 9)
            self.assertTrue(report["gates"][0]["passed"])
            self.assertFalse(report["gates"][1]["passed"])

    def test_old_publication_observed_in_2026_is_rejected_for_causal_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            database = _database(
                Path(directory) / "news.db",
                published_at="2024-06-01 08:00:00",
                first_seen="2026-08-01 09:00:00",
                last_seen="2026-08-01 09:30:00",
                generated_at="2026-08-01 10:05:00",
                data_cutoff_at="2026-08-01 10:00:00",
            )

            report = _audit(database)

            self.assertEqual(
                report["counts"]["publication_date_only_overlap_versions"], 1
            )
            self.assertEqual(
                report["counts"][
                    "publication_overlap_but_observed_too_late_versions"
                ],
                1,
            )
            self.assertEqual(
                report["counts"]["causally_observed_overlap_events"], 0
            )
            self.assertEqual(report["distributions"]["observed_year"], {"2026": 1})

    def test_non_empty_wal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            database = _database(Path(directory) / "news.db")
            Path(f"{database}-wal").write_bytes(b"pending")

            with self.assertRaisesRegex(ContractError, "no pending WAL"):
                _audit(database)

    def test_input_change_during_audit_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            database = _database(Path(directory) / "news.db")
            stat = database.stat()
            original = FileFingerprint(
                sha256(database.read_bytes()).hexdigest(),
                stat.st_size,
                stat.st_mtime_ns,
            )
            changed = FileFingerprint("0" * 64, stat.st_size, stat.st_mtime_ns)

            with patch(
                "evidence_alpha.news_overlap._fingerprint",
                side_effect=(original, changed),
            ):
                with self.assertRaisesRegex(ContractError, "changed during"):
                    _audit(database)

    def test_cli_output_is_machine_readable_and_contains_no_raw_news(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = _database(root / "news.db", event_count=31)
            output = root / "audit.json"
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = cli_main(
                    [
                        "audit-news-overlap",
                        "--database",
                        str(database),
                        "--factor-coverage-start",
                        "2024-01-01",
                        "--adjusted-price-coverage-end",
                        "2024-12-31",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(exit_code, 0)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(stdout.getvalue()), written)
            serialized = json.dumps(written, ensure_ascii=False)
            for forbidden in (
                RAW_TITLE,
                RAW_BODY,
                RAW_URL,
                "SECRET-EVENT",
                "SECRET-ARTICLE",
                str(root),
            ):
                self.assertNotIn(forbidden, serialized)

    def test_cli_refuses_to_overwrite_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database = _database(Path(directory) / "news.db")
            original = database.read_bytes()
            stderr = StringIO()

            with redirect_stderr(stderr):
                exit_code = cli_main(
                    [
                        "audit-news-overlap",
                        "--database",
                        str(database),
                        "--factor-coverage-start",
                        "2024-01-01",
                        "--adjusted-price-coverage-end",
                        "2024-12-31",
                        "--output",
                        str(database),
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertEqual(database.read_bytes(), original)
            self.assertEqual(json.loads(stderr.getvalue())["decision"], "REJECT")


if __name__ == "__main__":
    unittest.main()
