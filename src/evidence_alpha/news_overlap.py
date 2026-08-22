from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import sqlite3
from typing import Any

from .models import ContractError, parse_date, parse_datetime


TIMESTAMP_POLICY = (
    "observed_at=max(earliest linked published_at or event first_seen, "
    "event first_seen, event last_seen, report generated_at, "
    "report data_cutoff_at)"
)
REQUIRED_COLUMNS = {
    "report": {"event_id", "version", "generated_at", "data_cutoff_at"},
    "event_cluster": {"id", "is_demo", "first_seen", "last_seen"},
    "event_article": {"event_id", "article_id"},
    "article": {"id", "published_at"},
}


@dataclass(frozen=True)
class FileFingerprint:
    sha256: str
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True)
class Observation:
    event_id: str
    published_at: datetime
    observed_at: datetime


def _fingerprint(path: Path) -> FileFingerprint:
    digest = sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        stat = path.stat()
    except OSError as exc:
        raise ContractError(
            f"cannot fingerprint News_Claws snapshot ({type(exc).__name__})"
        ) from exc
    return FileFingerprint(digest.hexdigest(), stat.st_size, stat.st_mtime_ns)


def _sqlite_utc(value: object, field_name: str) -> datetime:
    text = str(value or "").strip()
    if text and not text.endswith(("Z", "z")) and not re.search(
        r"[+-]\d\d:\d\d$", text
    ):
        text = f"{text}+00:00"
    return parse_datetime(text, field_name).astimezone(timezone.utc)


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
    if not quick_check or str(quick_check[0]).casefold() != "ok":
        raise ContractError("News_Claws SQLite snapshot failed quick_check")


def _fraction(value: float) -> Fraction:
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise ContractError("oos_fraction must be a finite number in (0, 1]") from exc
    if result <= 0 or result > 1:
        raise ContractError("oos_fraction must be in (0, 1]")
    return result


def _ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def _minimum_total_for_oos(minimum_oos_events: int, fraction: Fraction) -> int:
    if minimum_oos_events <= 0:
        return 0
    # ceil(n * f) >= m iff n * f > m - 1.
    numerator = (minimum_oos_events - 1) * fraction.denominator
    return numerator // fraction.numerator + 1


def _validate_thresholds(
    minimum_event_count: int,
    oos_fraction: float,
    minimum_oos_events: int,
) -> Fraction:
    if isinstance(minimum_event_count, bool) or minimum_event_count < 1:
        raise ContractError("minimum_event_count must be >= 1")
    if isinstance(minimum_oos_events, bool) or minimum_oos_events < 1:
        raise ContractError("minimum_oos_events must be >= 1")
    return _fraction(oos_fraction)


def _load_observations(connection: sqlite3.Connection) -> list[Observation]:
    report_rows = connection.execute(
        """
        SELECT
            r.event_id,
            r.version,
            r.generated_at,
            r.data_cutoff_at,
            ec.first_seen,
            ec.last_seen
        FROM report AS r
        JOIN event_cluster AS ec ON ec.id = r.event_id
        WHERE ec.is_demo = 0
        ORDER BY r.event_id, r.version
        """
    ).fetchall()
    publication_rows = connection.execute(
        """
        SELECT ea.event_id, a.published_at
        FROM event_article AS ea
        JOIN article AS a ON a.id = ea.article_id
        JOIN event_cluster AS ec ON ec.id = ea.event_id
        WHERE ec.is_demo = 0 AND a.published_at IS NOT NULL
        ORDER BY ea.event_id, a.published_at
        """
    ).fetchall()
    publications: dict[str, list[datetime]] = defaultdict(list)
    for row in publication_rows:
        event_id = str(row["event_id"] or "").strip()
        if not event_id:
            raise ContractError("article mapping contains an empty event_id")
        publications[event_id].append(
            _sqlite_utc(row["published_at"], "article.published_at")
        )

    observations: list[Observation] = []
    seen_versions: set[tuple[str, int]] = set()
    for row in report_rows:
        event_id = str(row["event_id"] or "").strip()
        if not event_id:
            raise ContractError("report contains an empty event_id")
        try:
            version = int(row["version"])
        except (TypeError, ValueError) as exc:
            raise ContractError("report version must be an integer") from exc
        if version < 1:
            raise ContractError("report version must be >= 1")
        version_key = (event_id, version)
        if version_key in seen_versions:
            raise ContractError("duplicate immutable report event/version")
        seen_versions.add(version_key)

        first_seen = _sqlite_utc(row["first_seen"], "event.first_seen")
        last_seen = _sqlite_utc(row["last_seen"], "event.last_seen")
        generated_at = _sqlite_utc(row["generated_at"], "report.generated_at")
        data_cutoff_at = _sqlite_utc(
            row["data_cutoff_at"], "report.data_cutoff_at"
        )
        if last_seen < first_seen:
            raise ContractError("event last_seen precedes first_seen")
        if generated_at < data_cutoff_at:
            raise ContractError("report generated_at precedes data_cutoff_at")
        published_at = min(publications.get(event_id, (first_seen,)))
        observations.append(
            Observation(
                event_id=event_id,
                published_at=published_at,
                observed_at=max(
                    published_at,
                    first_seen,
                    last_seen,
                    generated_at,
                    data_cutoff_at,
                ),
            )
        )
    return observations


def build_news_overlap_audit(
    database_path: str | Path,
    *,
    factor_coverage_start: str | date,
    adjusted_price_coverage_end: str | date,
    minimum_event_count: int = 30,
    oos_fraction: float = 0.30,
    minimum_oos_events: int = 10,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Audit causal news/market overlap without retaining raw news fields."""
    database = Path(database_path).resolve()
    if not database.is_file():
        raise ContractError("News_Claws SQLite snapshot not found")
    factor_start = parse_date(factor_coverage_start, "factor_coverage_start")
    price_end = parse_date(
        adjusted_price_coverage_end, "adjusted_price_coverage_end"
    )
    latest_safe_event_date = price_end - timedelta(days=1)
    if factor_start > latest_safe_event_date:
        raise ContractError(
            "market coverage has no date that can support an event through T+1"
        )
    fraction = _validate_thresholds(
        minimum_event_count, oos_fraction, minimum_oos_events
    )
    if generated_at is not None and (
        generated_at.tzinfo is None or generated_at.utcoffset() is None
    ):
        raise ContractError("generated_at must include a timezone")

    wal_path = Path(f"{database}-wal")
    if wal_path.is_file() and wal_path.stat().st_size:
        raise ContractError(
            "news overlap audit requires a checkpointed snapshot with no pending WAL"
        )
    before = _fingerprint(database)
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        query_only = connection.execute("PRAGMA query_only").fetchone()
        if not query_only or int(query_only[0]) != 1:
            raise ContractError("SQLite query_only could not be enabled")
        _assert_schema(connection)
        observations = _load_observations(connection)
    except sqlite3.Error as exc:
        raise ContractError(
            f"cannot audit News_Claws SQLite snapshot ({type(exc).__name__})"
        ) from exc
    finally:
        connection.close()

    after = _fingerprint(database)
    if after != before:
        raise ContractError("read-only SQLite snapshot changed during overlap audit")
    if wal_path.is_file() and wal_path.stat().st_size:
        raise ContractError("pending WAL appeared during news overlap audit")

    overlap = [
        item
        for item in observations
        if factor_start <= item.observed_at.date() <= latest_safe_event_date
    ]
    publication_overlap = [
        item
        for item in observations
        if factor_start <= item.published_at.date() <= latest_safe_event_date
    ]
    late_observed = [
        item
        for item in publication_overlap
        if item.observed_at.date() > latest_safe_event_date
    ]
    overlap_event_count = len({item.event_id for item in overlap})
    oos_event_count = _ceil_fraction(overlap_event_count * fraction)
    event_gate = overlap_event_count >= minimum_event_count
    oos_gate = oos_event_count >= minimum_oos_events
    minimum_total = max(
        minimum_event_count,
        _minimum_total_for_oos(minimum_oos_events, fraction),
    )
    artifact_generated_at = (
        generated_at.astimezone(timezone.utc)
        if generated_at is not None
        else datetime.now(timezone.utc)
    )
    observed_years = Counter(item.observed_at.year for item in observations)
    published_years = Counter(item.published_at.year for item in observations)
    audit_key = "|".join(
        (
            before.sha256,
            factor_start.isoformat(),
            price_end.isoformat(),
            str(minimum_event_count),
            str(fraction),
            str(minimum_oos_events),
            TIMESTAMP_POLICY,
        )
    )
    return {
        "schema_version": "1.0",
        "artifact_type": "historical_news_overlap_audit",
        "audit_id": f"NEWS-OVERLAP-{sha256(audit_key.encode('utf-8')).hexdigest()[:20].upper()}",
        "generated_at": artifact_generated_at.isoformat(),
        "source": {
            "logical_name": database.name,
            "sha256": before.sha256,
            "size_bytes": before.size_bytes,
            "selection": "non_demo_only",
        },
        "read_safety": {
            "sqlite_mode": "ro",
            "query_only": True,
            "quick_check": "ok",
            "pending_wal": False,
            "input_unchanged": True,
        },
        "timestamp_policy": TIMESTAMP_POLICY,
        "market_overlap_contract": {
            "factor_coverage_start": factor_start.isoformat(),
            "adjusted_price_coverage_end": price_end.isoformat(),
            "latest_safe_event_date": latest_safe_event_date.isoformat(),
            "required_return_endpoint": "T+1_or_later",
        },
        "thresholds": {
            "minimum_event_count": minimum_event_count,
            "oos_fraction": float(fraction),
            "minimum_oos_events": minimum_oos_events,
            "minimum_total_events_required": minimum_total,
        },
        "counts": {
            "non_demo_report_versions": len(observations),
            "non_demo_events": len({item.event_id for item in observations}),
            "causally_observed_overlap_versions": len(overlap),
            "causally_observed_overlap_events": overlap_event_count,
            "publication_date_only_overlap_versions": len(publication_overlap),
            "publication_overlap_but_observed_too_late_versions": len(late_observed),
            "chronological_oos_events": oos_event_count,
        },
        "distributions": {
            "observed_year": {
                str(year): count for year, count in sorted(observed_years.items())
            },
            "published_year": {
                str(year): count for year, count in sorted(published_years.items())
            },
        },
        "observed_at_range": {
            "minimum": min(
                (item.observed_at for item in observations), default=None
            ).isoformat()
            if observations
            else None,
            "maximum": max(
                (item.observed_at for item in observations), default=None
            ).isoformat()
            if observations
            else None,
        },
        "gates": [
            {
                "id": "minimum_causal_event_count",
                "passed": event_gate,
                "actual": overlap_event_count,
                "required": minimum_event_count,
            },
            {
                "id": "minimum_chronological_oos_count",
                "passed": oos_gate,
                "actual": oos_event_count,
                "required": minimum_oos_events,
            },
        ],
        "decision": (
            "COHORT_CANDIDATE"
            if event_gate and oos_gate
            else "INSUFFICIENT_CAUSAL_OVERLAP"
        ),
    }


def write_news_overlap_audit(report: dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        temporary.write_text(payload + "\n", encoding="utf-8")
        os.replace(temporary, output)
    except (OSError, UnicodeError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ContractError(
            f"cannot write news overlap audit ({type(exc).__name__})"
        ) from exc
    return output
