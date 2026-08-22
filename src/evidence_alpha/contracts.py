from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
import json
from typing import Any, Iterable

from .models import (
    BaselineWeight,
    ContractError,
    EntityMapping,
    EventSnapshot,
    EvidenceRecord,
    PriceBar,
    content_hash,
    parse_date,
)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_events(path: str | Path) -> list[EventSnapshot]:
    source = Path(path)
    if source.suffix.lower() == ".jsonl":
        with source.open("r", encoding="utf-8") as handle:
            raw = [json.loads(line) for line in handle if line.strip()]
    elif source.suffix.lower() == ".json":
        payload = _load_json(source)
        raw = payload.get("events", []) if isinstance(payload, dict) else payload
    else:
        raise ContractError("MVP event input must be .json or .jsonl")
    if not isinstance(raw, list):
        raise ContractError("event payload must be a list or {'events': [...]} object")
    events = [EventSnapshot.from_dict(item) for item in raw]
    seen: dict[tuple[str, int], str] = {}
    for event in events:
        key = (event.event_id, event.event_version)
        digest = content_hash(event.to_dict())
        if key in seen and seen[key] != digest:
            raise ContractError(f"event version is not immutable: {event.ref}")
        seen[key] = digest
    return events


def load_evidence(path: str | Path) -> dict[str, EvidenceRecord]:
    payload = _load_json(Path(path))
    raw: Iterable[dict[str, Any]]
    if isinstance(payload, dict) and "evidence" in payload:
        raw = payload["evidence"]
    elif isinstance(payload, dict):
        raw = [dict(value, evidence_id=key) for key, value in payload.items()]
    elif isinstance(payload, list):
        raw = payload
    else:
        raise ContractError("evidence payload must be a list or object")
    result: dict[str, EvidenceRecord] = {}
    for item in raw:
        record = EvidenceRecord.from_dict(item)
        if record.evidence_id in result:
            raise ContractError(f"duplicate evidence_id: {record.evidence_id}")
        result[record.evidence_id] = record
    return result


def load_mappings(path: str | Path) -> list[EntityMapping]:
    result: list[EntityMapping] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            entity = str(row.get("entity", "")).strip()
            ticker = str(row.get("ticker", "")).strip().upper()
            sector = str(row.get("sector", "")).strip()
            if not entity or not ticker:
                raise ContractError("mapping entity and ticker are required")
            result.append(
                EntityMapping(
                    entity=entity,
                    ticker=ticker,
                    sector=sector,
                    impact_multiplier=float(row.get("impact_multiplier", 1.0)),
                    event_ref=str(row.get("event_ref", "")).strip() or None,
                )
            )
    return result


def load_prices(path: str | Path) -> list[PriceBar]:
    result: list[PriceBar] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            bar = PriceBar(
                trade_date=parse_date(row.get("date", ""), "date"),
                ticker=str(row.get("ticker", "")).strip().upper(),
                open=float(row.get("open", 0.0)),
                close=float(row.get("close", 0.0)),
            )
            if not bar.ticker or bar.open <= 0 or bar.close <= 0:
                raise ContractError("price ticker, open, and close must be valid")
            result.append(bar)
    return sorted(result, key=lambda item: (item.trade_date, item.ticker))


def load_baseline_weights(path: str | Path) -> list[BaselineWeight]:
    result: list[BaselineWeight] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            factor_version = str(row.get("factor_version", "")).strip()
            if not factor_version:
                raise ContractError("factor_version is required")
            result.append(
                BaselineWeight(
                    asof=parse_date(row.get("asof", ""), "asof"),
                    ticker=str(row.get("ticker", "")).strip().upper(),
                    weight=float(row.get("weight", 0.0)),
                    factor_version=factor_version,
                )
            )
    if not result:
        raise ContractError("baseline weights must not be empty")
    total = sum(item.weight for item in result)
    if abs(total - 1.0) > 1e-8:
        raise ContractError(f"baseline weights must sum to 1.0, got {total:.8f}")
    return result


def select_visible_versions(events: Iterable[EventSnapshot], cutoff: datetime) -> list[EventSnapshot]:
    visible: dict[str, EventSnapshot] = {}
    for event in events:
        if event.observed_at > cutoff or event.asof > cutoff:
            continue
        current = visible.get(event.event_id)
        if current is None or (event.event_version, event.asof) > (current.event_version, current.asof):
            visible[event.event_id] = event
    return sorted(visible.values(), key=lambda item: (item.asof, item.event_id))


def file_digests(paths: dict[str, str | Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, path in paths.items():
        source = Path(path)
        result[name] = content_hash(source.read_text(encoding="utf-8-sig"))
    return result
