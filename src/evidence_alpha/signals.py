from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from math import exp
from typing import Iterable

from .models import EntityMapping, EventSignal, EventSnapshot, content_hash


@dataclass(frozen=True)
class SignalConfig:
    conflict_multiplier: float = 0.5
    uncertain_multiplier: float = 0.25
    minimum_absolute_strength: float = 0.01

    @property
    def hash(self) -> str:
        return content_hash(asdict(self))


DIRECTION_SCORE = {
    "positive": 1.0,
    "negative": -1.0,
    "neutral": 0.0,
    "uncertain": 0.25,
}


def generate_signals(
    events: Iterable[EventSnapshot],
    mappings: Iterable[EntityMapping],
    cutoff: datetime,
    config: SignalConfig,
) -> tuple[list[EventSignal], list[dict[str, str]]]:
    mapping_index: dict[str, list[EntityMapping]] = {}
    event_mapping_index: dict[tuple[str, str], list[EntityMapping]] = {}
    for mapping in mappings:
        entity_key = mapping.entity.casefold()
        if mapping.event_ref:
            event_mapping_index.setdefault(
                (mapping.event_ref, entity_key), []
            ).append(mapping)
        else:
            mapping_index.setdefault(entity_key, []).append(mapping)

    signals: list[EventSignal] = []
    unmapped: list[dict[str, str]] = []
    for event in events:
        age_days = max(0.0, (cutoff - event.observed_at).total_seconds() / 86400.0)
        decay = exp(-age_days / event.impact_horizon_days)
        conflict_multiplier = config.conflict_multiplier if event.conflict else 1.0
        uncertain_multiplier = config.uncertain_multiplier if event.direction == "uncertain" else 1.0
        candidates: list[EntityMapping] = []
        for entity in (*event.entities, *event.sectors):
            entity_key = entity.casefold()
            matches = event_mapping_index.get((event.ref, entity_key))
            if matches is None:
                matches = mapping_index.get(entity_key, [])
            if not matches:
                unmapped.append({"event_ref": event.ref, "entity": entity})
            candidates.extend(matches)
        unique = {(item.entity.casefold(), item.ticker): item for item in candidates}.values()
        for mapping in unique:
            raw = (
                DIRECTION_SCORE[event.direction]
                * event.confidence
                * event.novelty
                * conflict_multiplier
                * uncertain_multiplier
                * mapping.impact_multiplier
            )
            decayed = raw * decay
            if abs(decayed) < config.minimum_absolute_strength:
                continue
            identity = {
                "event_id": event.event_id,
                "event_version": event.event_version,
                "ticker": mapping.ticker,
                "config_hash": config.hash,
                "signal_asof": cutoff.isoformat(),
            }
            signals.append(
                EventSignal(
                    signal_id=f"SIG-{content_hash(identity)[:16].upper()}",
                    event_id=event.event_id,
                    event_version=event.event_version,
                    ticker=mapping.ticker,
                    sector=mapping.sector,
                    signal_asof=cutoff,
                    raw_strength=round(raw, 12),
                    decayed_strength=round(decayed, 12),
                    evidence_ids=event.evidence_ids,
                    config_hash=config.hash,
                )
            )
    return sorted(signals, key=lambda item: (item.ticker, item.signal_id)), unmapped


def lineage_by_ticker(signals: Iterable[EventSignal]) -> dict[str, dict[str, tuple[str, ...]]]:
    grouped: dict[str, dict[str, set[str]]] = {}
    for signal in signals:
        bucket = grouped.setdefault(signal.ticker, {"signal_ids": set(), "event_refs": set(), "evidence_ids": set()})
        bucket["signal_ids"].add(signal.signal_id)
        bucket["event_refs"].add(f"{signal.event_id}:v{signal.event_version}")
        bucket["evidence_ids"].update(signal.evidence_ids)
    return {
        ticker: {name: tuple(sorted(values)) for name, values in bucket.items()}
        for ticker, bucket in grouped.items()
    }
