from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import sqlite3
from typing import Any

from .models import ContractError, EventSnapshot, parse_datetime
from .news_enrichment import NewsEnrichment, _external_url, load_news_enrichment


METHODOLOGY = (
    "news-claws-sqlite-pit-published-at-v1: exact report event/version; "
    "article first_seen_at <= report data_cutoff_at; earliest published_at; "
    "available_at=max(report generated_at, selected article first_seen_at)"
)
REQUIRED_COLUMNS = {
    "report": {
        "event_id",
        "version",
        "generated_at",
        "data_cutoff_at",
    },
    "event_article": {"event_id", "article_id"},
    "article": {
        "id",
        "canonical_url",
        "original_url",
        "origin_url",
        "published_at",
        "first_seen_at",
    },
}


class NoEligibleArticleError(ContractError):
    pass


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sqlite_utc(value: object, field_name: str) -> datetime:
    text = str(value or "").strip()
    if text and not text.endswith(("Z", "z")) and not re.search(
        r"[+-]\d\d:\d\d$", text
    ):
        text = f"{text}+00:00"
    return parse_datetime(text, field_name).astimezone(timezone.utc)


def _artifact_reference(path: Path, output_parent: Path) -> str:
    try:
        return Path(os.path.relpath(path, output_parent)).as_posix()
    except ValueError:
        return str(path)


def _load_event_snapshots(path: Path) -> list[EventSnapshot]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("news export events must be valid UTF-8 JSON") from exc
    if not isinstance(payload, list) or not payload:
        raise ContractError("news export events must be a non-empty list")
    snapshots: list[EventSnapshot] = []
    seen: set[str] = set()
    for row in payload:
        if not isinstance(row, dict):
            raise ContractError("news export event must be an object")
        snapshot = EventSnapshot.from_dict(row)
        if snapshot.ref in seen:
            raise ContractError(f"duplicate news export event: {snapshot.ref}")
        seen.add(snapshot.ref)
        snapshots.append(snapshot)
    return sorted(snapshots, key=lambda item: (item.event_id, item.event_version))


def _assert_schema(connection: sqlite3.Connection) -> None:
    for table, required in REQUIRED_COLUMNS.items():
        rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        available = {str(row["name"]) for row in rows}
        missing = sorted(required - available)
        if missing:
            raise ContractError(
                f"News_Claws SQLite table {table} is missing columns: {missing}"
            )
    quick_check = connection.execute("PRAGMA quick_check").fetchone()
    if not quick_check or quick_check[0] != "ok":
        raise ContractError("News_Claws SQLite snapshot failed quick_check")


def _external_urls(row: sqlite3.Row) -> list[str]:
    return sorted(
        {
            str(row[column]).strip()
            for column in ("canonical_url", "original_url", "origin_url")
            if row[column] and _external_url(row[column])
        }
    )


def _event_enrichment(
    connection: sqlite3.Connection, snapshot: EventSnapshot
) -> tuple[dict[str, Any], datetime]:
    report_rows = connection.execute(
        """
        SELECT generated_at, data_cutoff_at
        FROM report
        WHERE event_id = ? AND version = ?
        """,
        (snapshot.event_id, snapshot.event_version),
    ).fetchall()
    if len(report_rows) != 1:
        raise ContractError(
            f"expected one immutable report for {snapshot.ref}, found "
            f"{len(report_rows)}"
        )
    report_generated = _sqlite_utc(
        report_rows[0]["generated_at"], f"{snapshot.ref}.report.generated_at"
    )
    report_cutoff = _sqlite_utc(
        report_rows[0]["data_cutoff_at"], f"{snapshot.ref}.report.data_cutoff_at"
    )
    if report_generated < report_cutoff:
        raise ContractError(
            f"report generated_at precedes data_cutoff_at: {snapshot.ref}"
        )

    article_rows = connection.execute(
        """
        SELECT
            a.id,
            a.canonical_url,
            a.original_url,
            a.origin_url,
            a.published_at,
            a.first_seen_at
        FROM event_article AS ea
        JOIN article AS a ON a.id = ea.article_id
        WHERE ea.event_id = ?
        ORDER BY a.id
        """,
        (snapshot.event_id,),
    ).fetchall()
    candidates: list[tuple[datetime, datetime, str, list[str]]] = []
    for row in article_rows:
        first_seen = _sqlite_utc(
            row["first_seen_at"], f"{snapshot.ref}.article.first_seen_at"
        )
        if first_seen > report_cutoff or not row["published_at"]:
            continue
        published = _sqlite_utc(
            row["published_at"], f"{snapshot.ref}.article.published_at"
        )
        urls = _external_urls(row)
        if urls:
            candidates.append((published, first_seen, str(row["id"]), urls))
    if not candidates:
        raise NoEligibleArticleError(
            f"no eligible article with published_at and external URL: {snapshot.ref}"
        )

    published_at, first_seen_at, _article_id, source_urls = min(candidates)
    available_at = max(report_generated, first_seen_at)
    if published_at > available_at:
        raise ContractError(
            f"published_at exceeds PIT availability time: {snapshot.ref}"
        )
    return (
        {
            "event_id": snapshot.event_id,
            "event_version": snapshot.event_version,
            "available_at": available_at.isoformat(),
            "source_urls": source_urls,
            "published_at": published_at.isoformat(),
        },
        available_at,
    )


def export_sqlite_news_enrichment(
    *,
    database_path: str | Path,
    events_path: str | Path,
    output_path: str | Path,
    repository: str,
    commit: str,
    generated_at: datetime | None = None,
    allow_partial: bool = False,
) -> NewsEnrichment:
    database = Path(database_path).resolve()
    events = Path(events_path).resolve()
    output = Path(output_path).resolve()
    if not database.is_file():
        raise ContractError(f"News_Claws SQLite snapshot not found: {database}")
    if not events.is_file():
        raise ContractError(f"news export events file not found: {events}")
    if not repository.strip() or not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise ContractError("SQLite enrichment requires repository and 40-char commit")
    wal_path = Path(f"{database}-wal")
    if wal_path.is_file() and wal_path.stat().st_size:
        raise ContractError(
            "SQLite enrichment requires a checkpointed snapshot with no pending WAL"
        )

    database_stat = database.stat()
    database_hash = _sha256_file(database)
    events_stat = events.stat()
    events_hash = _sha256_file(events)
    snapshots = _load_event_snapshots(events)

    connection = sqlite3.connect(
        f"{database.as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        _assert_schema(connection)
        enriched_rows: list[dict[str, Any]] = []
        availability_times: list[datetime] = []
        unresolved_refs: list[str] = []
        for snapshot in snapshots:
            try:
                row, available_at = _event_enrichment(connection, snapshot)
            except NoEligibleArticleError:
                if not allow_partial:
                    raise
                unresolved_refs.append(snapshot.ref)
                continue
            enriched_rows.append(row)
            availability_times.append(available_at)
    finally:
        connection.close()

    if (
        database.stat().st_size != database_stat.st_size
        or database.stat().st_mtime_ns != database_stat.st_mtime_ns
        or _sha256_file(database) != database_hash
    ):
        raise ContractError("read-only SQLite snapshot changed during enrichment")
    if (
        events.stat().st_size != events_stat.st_size
        or events.stat().st_mtime_ns != events_stat.st_mtime_ns
        or _sha256_file(events) != events_hash
    ):
        raise ContractError("news export events changed during enrichment")

    if not enriched_rows:
        raise ContractError("SQLite enrichment did not resolve any requested event")
    if (
        generated_at is not None
        and (generated_at.tzinfo is None or generated_at.utcoffset() is None)
    ):
        raise ContractError("enrichment generated_at must include a timezone")
    artifact_generated_at = (
        generated_at.astimezone(timezone.utc)
        if generated_at is not None
        else datetime.now(timezone.utc)
    )
    if max(availability_times) > artifact_generated_at:
        raise ContractError("enrichment contains data not yet available at generated_at")

    run_digest = sha256(
        "|".join(
            (
                database_hash,
                events_hash,
                repository.strip(),
                commit.casefold(),
                METHODOLOGY,
                "eligible_published_at_only" if allow_partial else "all_requested",
            )
        ).encode("utf-8")
    ).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "enrichment_type": "news_event_enrichment",
        "generated_at": artifact_generated_at.isoformat(),
        "source": {
            "synthetic": False,
            "repository": repository.strip(),
            "commit": commit.casefold(),
            "pipeline_run_id": f"NEWS-SQLITE-{run_digest[:20].upper()}",
            "methodology": METHODOLOGY,
            "input_artifacts": [
                {
                    "artifact_type": "news_claws_sqlite_snapshot",
                    "artifact": _artifact_reference(database, output.parent),
                    "sha256": database_hash,
                },
                {
                    "artifact_type": "news_export_events",
                    "artifact": _artifact_reference(events, output.parent),
                    "sha256": events_hash,
                },
            ],
            "selection": {
                "policy": (
                    "eligible_published_at_only"
                    if allow_partial
                    else "all_requested"
                ),
                "requested_event_refs": [item.ref for item in snapshots],
                "enriched_event_refs": sorted(
                    f"{item['event_id']}:v{item['event_version']}"
                    for item in enriched_rows
                ),
                "unresolved_event_refs": sorted(unresolved_refs),
            },
        },
        "events": enriched_rows,
    }
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return load_news_enrichment(output)
