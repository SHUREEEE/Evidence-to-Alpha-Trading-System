from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any, Iterable

from .models import ContractError, EventSnapshot, canonical_json, content_hash


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS event_versions (
    event_id TEXT NOT NULL,
    event_version INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    registered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, event_version)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    cutoff TEXT NOT NULL,
    decision TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS run_artifacts (
    run_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, artifact_type, artifact_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
"""


class EvidenceStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "EvidenceStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def register_event(self, event: EventSnapshot) -> None:
        payload = canonical_json(event.to_dict())
        digest = content_hash(event.to_dict())
        existing = self.connection.execute(
            "SELECT content_hash FROM event_versions WHERE event_id=? AND event_version=?",
            (event.event_id, event.event_version),
        ).fetchone()
        if existing and existing[0] != digest:
            raise ContractError(f"event version overwrite rejected: {event.ref}")
        if not existing:
            self.connection.execute(
                "INSERT INTO event_versions(event_id,event_version,content_hash,payload_json) VALUES(?,?,?,?)",
                (event.event_id, event.event_version, digest, payload),
            )
            self.connection.commit()

    def register_events(self, events: Iterable[EventSnapshot]) -> None:
        for event in events:
            self.register_event(event)

    def write_run(
        self,
        run_id: str,
        cutoff: str,
        decision: str,
        config_hash: str,
        report: dict[str, Any],
        artifacts: dict[str, list[dict[str, Any]]],
    ) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO runs(run_id,cutoff,decision,config_hash,report_json) VALUES(?,?,?,?,?)",
            (run_id, cutoff, decision, config_hash, canonical_json(report)),
        )
        for artifact_type, items in artifacts.items():
            for index, item in enumerate(items):
                artifact_id = str(
                    item.get("signal_id")
                    or item.get("order_id")
                    or item.get("fill_id")
                    or item.get("event_ref")
                    or index
                )
                self.connection.execute(
                    "INSERT OR REPLACE INTO run_artifacts(run_id,artifact_type,artifact_id,payload_json) VALUES(?,?,?,?)",
                    (run_id, artifact_type, artifact_id, canonical_json(item)),
                )
        self.connection.commit()

