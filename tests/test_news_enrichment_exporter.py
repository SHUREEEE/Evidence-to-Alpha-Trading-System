from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from evidence_alpha.cli import main as cli_main
from evidence_alpha.models import ContractError
from evidence_alpha.news_enrichment import load_news_enrichment
from evidence_alpha.news_enrichment_exporter import export_sqlite_news_enrichment


COMMIT = "a" * 40


def _event(event_id: str, version: int) -> dict[str, object]:
    observed_hour = 10 if version == 1 else 12
    return {
        "event_id": event_id,
        "event_version": version,
        "published_at": "2026-01-01T08:00:00+00:00",
        "observed_at": f"2026-01-01T{observed_hour:02d}:05:00+00:00",
        "event_type": "news_event",
        "direction": "positive",
        "confidence": 0.8,
        "novelty": 0.0,
        "conflict": False,
        "impact_horizon_days": 5,
        "entities": [],
        "sectors": ["__UNMAPPED__"],
        "evidence_ids": [f"EV-{event_id}-{version}"],
        "status": "active",
        "asof": f"2026-01-01T{observed_hour:02d}:05:00+00:00",
    }


def _write_events(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return path


def _database(path: Path) -> Path:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE report (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                generated_at TEXT NOT NULL,
                data_cutoff_at TEXT NOT NULL
            );
            CREATE TABLE event_article (
                event_id TEXT NOT NULL,
                article_id TEXT NOT NULL
            );
            CREATE TABLE article (
                id TEXT PRIMARY KEY,
                canonical_url TEXT NOT NULL,
                original_url TEXT NOT NULL,
                origin_url TEXT,
                published_at TEXT,
                first_seen_at TEXT NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO report VALUES (?, ?, ?, ?, ?)",
            [
                (
                    "R1",
                    "E1",
                    1,
                    "2026-01-01 10:05:00",
                    "2026-01-01 10:00:00",
                ),
                (
                    "R2",
                    "E1",
                    2,
                    "2026-01-01 12:05:00",
                    "2026-01-01 12:00:00",
                ),
                (
                    "R3",
                    "E2",
                    1,
                    "2026-01-01 10:05:00",
                    "2026-01-01 10:00:00",
                ),
            ],
        )
        connection.executemany(
            "INSERT INTO event_article VALUES (?, ?)",
            [("E1", "A1"), ("E1", "A2"), ("E2", "A3")],
        )
        connection.executemany(
            "INSERT INTO article VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    "A1",
                    "https://news.trusted-source.com/a1",
                    "https://news.trusted-source.com/a1",
                    None,
                    "2026-01-01 08:00:00",
                    "2026-01-01 09:00:00",
                ),
                (
                    "A2",
                    "https://news.trusted-source.com/a2",
                    "https://news.trusted-source.com/a2",
                    None,
                    "2026-01-01 07:00:00",
                    "2026-01-01 11:00:00",
                ),
                (
                    "A3",
                    "https://news.trusted-source.com/a3",
                    "https://news.trusted-source.com/a3",
                    None,
                    None,
                    "2026-01-01 09:00:00",
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()
    return path


class NewsEnrichmentExporterTests(unittest.TestCase):
    def test_exact_versions_cutoff_and_read_only_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = _database(root / "news.db")
            events = _write_events(
                root / "events.json", [_event("E1", 1), _event("E1", 2)]
            )
            before_hash = sha256(database.read_bytes()).hexdigest()
            before_mtime = database.stat().st_mtime_ns
            enrichment = export_sqlite_news_enrichment(
                database_path=database,
                events_path=events,
                output_path=root / "enrichment.json",
                repository="SHUREEEE/News_Claws",
                commit=COMMIT,
                generated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            )

            self.assertEqual(sha256(database.read_bytes()).hexdigest(), before_hash)
            self.assertEqual(database.stat().st_mtime_ns, before_mtime)
            by_ref = {item.event_ref: item for item in enrichment.events}
            self.assertEqual(
                by_ref["E1:v1"].published_at.isoformat(),
                "2026-01-01T08:00:00+00:00",
            )
            self.assertEqual(
                by_ref["E1:v2"].published_at.isoformat(),
                "2026-01-01T07:00:00+00:00",
            )
            self.assertEqual(
                by_ref["E1:v1"].available_at.isoformat(),
                "2026-01-01T10:05:00+00:00",
            )

    def test_missing_exact_report_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ContractError, "expected one immutable report"):
                export_sqlite_news_enrichment(
                    database_path=_database(root / "news.db"),
                    events_path=_write_events(
                        root / "events.json", [_event("UNKNOWN", 1)]
                    ),
                    output_path=root / "enrichment.json",
                    repository="SHUREEEE/News_Claws",
                    commit=COMMIT,
                    generated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                )

    def test_no_eligible_published_article_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = _database(root / "news.db")
            connection = sqlite3.connect(database)
            try:
                connection.execute("UPDATE article SET published_at = NULL")
                connection.commit()
            finally:
                connection.close()
            with self.assertRaisesRegex(ContractError, "no eligible article"):
                export_sqlite_news_enrichment(
                    database_path=database,
                    events_path=_write_events(
                        root / "events.json", [_event("E1", 1)]
                    ),
                    output_path=root / "enrichment.json",
                    repository="SHUREEEE/News_Claws",
                    commit=COMMIT,
                    generated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                )

    def test_pending_wal_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = _database(root / "news.db")
            Path(f"{database}-wal").write_bytes(b"pending")
            with self.assertRaisesRegex(ContractError, "no pending WAL"):
                export_sqlite_news_enrichment(
                    database_path=database,
                    events_path=_write_events(
                        root / "events.json", [_event("E1", 1)]
                    ),
                    output_path=root / "enrichment.json",
                    repository="SHUREEEE/News_Claws",
                    commit=COMMIT,
                    generated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                )

    def test_explicit_partial_mode_records_unresolved_refs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            enrichment = export_sqlite_news_enrichment(
                database_path=_database(root / "news.db"),
                events_path=_write_events(
                    root / "events.json", [_event("E1", 1), _event("E2", 1)]
                ),
                output_path=root / "enrichment.json",
                repository="SHUREEEE/News_Claws",
                commit=COMMIT,
                generated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                allow_partial=True,
            )

            self.assertEqual(
                enrichment.selection_policy, "eligible_published_at_only"
            )
            self.assertEqual(
                enrichment.requested_event_refs, ("E1:v1", "E2:v1")
            )
            self.assertEqual(enrichment.unresolved_input_event_refs, ("E2:v1",))
            self.assertEqual(
                [item.event_ref for item in enrichment.events], ["E1:v1"]
            )

    def test_cli_output_loads_and_has_deterministic_run_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = _database(root / "news.db")
            events = _write_events(root / "events.json", [_event("E1", 1)])
            output = root / "enrichment.json"
            with patch("builtins.print"):
                result = cli_main(
                    [
                        "news-enrichment-sqlite",
                        "--database",
                        str(database),
                        "--events",
                        str(events),
                        "--commit",
                        COMMIT,
                        "--output",
                        str(output),
                    ]
                )
            loaded = load_news_enrichment(output)

            self.assertEqual(result, 0)
            self.assertEqual(len(loaded.events), 1)
            self.assertRegex(
                loaded.pipeline_run_id, r"^NEWS-SQLITE-[0-9A-F]{20}$"
            )


if __name__ == "__main__":
    unittest.main()
