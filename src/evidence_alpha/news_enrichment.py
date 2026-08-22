from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from ipaddress import ip_address
from math import isfinite
from pathlib import Path
import json
import re
from typing import Any
from urllib.parse import urlparse

from .models import (
    ContractError,
    EntityMapping,
    EventSnapshot,
    parse_date,
    parse_datetime,
)
from .news_adapter import NewsExport


RESOLVED_BY_PUBLISHED_AT = "published_at_fell_back_to_first_seen"
RESOLVED_BY_NOVELTY = "novelty_not_exposed_by_api"
RESOLVED_BY_MAPPING = {
    "industry_mapping_contains_encoding_replacement",
    "no_investable_company_or_industry_mapping",
}
PLACEHOLDER_HOSTS = {"example.com", "example.org", "example.net", "localhost"}
NON_PUBLIC_HOST_SUFFIXES = (
    ".example",
    ".home",
    ".internal",
    ".invalid",
    ".lan",
    ".local",
    ".localdomain",
    ".localhost",
    ".test",
)


@dataclass(frozen=True)
class EnrichedMapping:
    entity: str
    ticker: str
    sector: str
    impact_multiplier: float
    effective_from: date
    effective_to: date | None
    source_url: str


@dataclass(frozen=True)
class EventEnrichment:
    event_ref: str
    available_at: datetime
    source_urls: tuple[str, ...]
    published_at: datetime | None
    novelty: float | None
    mappings: tuple[EnrichedMapping, ...]


@dataclass(frozen=True)
class EnrichmentInputArtifact:
    artifact_type: str
    path: Path
    sha256: str


@dataclass(frozen=True)
class NewsEnrichment:
    path: Path
    sha256: str
    generated_at: datetime
    repository: str
    commit: str
    pipeline_run_id: str
    methodology: str
    input_artifacts: tuple[EnrichmentInputArtifact, ...]
    selection_policy: str
    requested_event_refs: tuple[str, ...]
    unresolved_input_event_refs: tuple[str, ...]
    events: tuple[EventEnrichment, ...]


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _non_placeholder(value: object) -> bool:
    text = str(value or "").strip().casefold()
    return bool(text) and not any(
        marker in text
        for marker in (
            "example",
            "placeholder",
            "synthetic",
            "demo",
            "replace-me",
            "replace-with",
        )
    )


def _external_url(value: object) -> bool:
    try:
        parsed = urlparse(str(value))
    except ValueError:
        return False
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    if host in PLACEHOLDER_HOSTS or host.endswith(NON_PUBLIC_HOST_SUFFIXES):
        return False
    try:
        address = ip_address(host)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


def _ticker(value: object) -> str:
    ticker = str(value or "").strip().upper()
    if (
        not re.fullmatch(r"[A-Z0-9.^-]{1,20}", ticker)
        or ticker.startswith(("DEMO-", "TEST-", "SYNTH-", "PLACEHOLDER-"))
    ):
        raise ContractError(f"invalid enrichment ticker: {value!r}")
    return ticker


def _mapping_from_dict(value: object, event_ref: str) -> EnrichedMapping:
    if not isinstance(value, dict):
        raise ContractError(f"enrichment mapping must be an object: {event_ref}")
    entity = str(value.get("entity", "")).strip()
    sector = str(value.get("sector", "")).strip()
    source_url = str(value.get("source_url", "")).strip()
    if not entity or not sector or not _external_url(source_url):
        raise ContractError(
            f"enrichment mapping requires entity, sector, and external source URL: {event_ref}"
        )
    try:
        multiplier = float(value.get("impact_multiplier", 1.0))
    except (TypeError, ValueError) as exc:
        raise ContractError(
            f"invalid enrichment impact multiplier: {event_ref}"
        ) from exc
    if not isfinite(multiplier) or not 0.0 < multiplier <= 2.0:
        raise ContractError(
            f"enrichment impact multiplier must be in (0, 2]: {event_ref}"
        )
    effective_from = parse_date(value.get("effective_from", ""), "effective_from")
    effective_to_value = value.get("effective_to")
    effective_to = (
        parse_date(effective_to_value, "effective_to")
        if effective_to_value not in (None, "")
        else None
    )
    if effective_to and effective_to < effective_from:
        raise ContractError(
            f"enrichment mapping effective_to precedes effective_from: {event_ref}"
        )
    return EnrichedMapping(
        entity=entity,
        ticker=_ticker(value.get("ticker")),
        sector=sector,
        impact_multiplier=multiplier,
        effective_from=effective_from,
        effective_to=effective_to,
        source_url=source_url,
    )


def _input_artifacts_from_source(
    value: object, enrichment_path: Path
) -> tuple[EnrichmentInputArtifact, ...]:
    if not isinstance(value, list) or not value:
        raise ContractError("news enrichment source requires input_artifacts")
    artifacts: list[EnrichmentInputArtifact] = []
    seen_types: set[str] = set()
    for row in value:
        if not isinstance(row, dict):
            raise ContractError("news enrichment input artifact must be an object")
        artifact_type = str(row.get("artifact_type", "")).strip()
        artifact_value = str(row.get("artifact", "")).strip()
        expected_hash = str(row.get("sha256", "")).strip().casefold()
        if (
            not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", artifact_type)
            or artifact_type in seen_types
        ):
            raise ContractError(
                f"invalid or duplicate news enrichment input artifact type: "
                f"{artifact_type!r}"
            )
        if not artifact_value or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise ContractError(
                f"news enrichment input artifact is incomplete: {artifact_type}"
            )
        artifact_path = Path(artifact_value)
        if not artifact_path.is_absolute():
            artifact_path = enrichment_path.parent / artifact_path
        artifact_path = artifact_path.resolve()
        if not artifact_path.is_file():
            raise ContractError(
                f"news enrichment input artifact not found: {artifact_path}"
            )
        actual_hash = _sha256_file(artifact_path)
        if actual_hash != expected_hash:
            raise ContractError(
                f"news enrichment input artifact hash mismatch: {artifact_type}"
            )
        seen_types.add(artifact_type)
        artifacts.append(
            EnrichmentInputArtifact(
                artifact_type=artifact_type,
                path=artifact_path,
                sha256=actual_hash,
            )
        )
    required_types = {
        "news_claws_sqlite_snapshot",
        "news_export_events",
    }
    missing_types = sorted(required_types - seen_types)
    if missing_types:
        raise ContractError(
            f"news enrichment input artifacts missing required types: {missing_types}"
        )
    return tuple(sorted(artifacts, key=lambda item: item.artifact_type))


def load_news_enrichment(path: str | Path) -> NewsEnrichment:
    source_path = Path(path).resolve()
    if not source_path.is_file():
        raise ContractError(f"news enrichment file not found: {source_path}")
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("news enrichment must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ContractError("news enrichment root must be an object")
    if payload.get("schema_version") != "1.0":
        raise ContractError("unsupported news enrichment schema_version")
    if payload.get("enrichment_type") != "news_event_enrichment":
        raise ContractError("unsupported news enrichment type")

    generated_at = parse_datetime(payload.get("generated_at", ""), "generated_at")
    source = payload.get("source")
    if not isinstance(source, dict) or source.get("synthetic") is not False:
        raise ContractError("news enrichment source must explicitly be non-synthetic")
    repository = str(source.get("repository", "")).strip()
    commit = str(source.get("commit", "")).strip()
    pipeline_run_id = str(source.get("pipeline_run_id", "")).strip()
    methodology = str(source.get("methodology", "")).strip()
    if (
        not _non_placeholder(repository)
        or not re.fullmatch(r"[0-9a-fA-F]{40}", commit)
        or not _non_placeholder(pipeline_run_id)
        or not _non_placeholder(methodology)
    ):
        raise ContractError(
            "news enrichment requires production repository, commit, run, and methodology"
        )
    input_artifacts = _input_artifacts_from_source(
        source.get("input_artifacts"), source_path
    )
    selection = source.get("selection")
    if selection is not None and not isinstance(selection, dict):
        raise ContractError("news enrichment source selection must be an object")

    rows = payload.get("events")
    if not isinstance(rows, list) or not rows:
        raise ContractError("news enrichment must contain at least one event")
    events: list[EventEnrichment] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ContractError("news enrichment event must be an object")
        event_id = str(row.get("event_id", "")).strip()
        event_version_value = row.get("event_version")
        if (
            isinstance(event_version_value, bool)
            or not isinstance(event_version_value, int)
        ):
            raise ContractError("news enrichment event_version must be an integer")
        event_version = event_version_value
        if not event_id or event_version < 1:
            raise ContractError("news enrichment event identity is invalid")
        event_ref = f"{event_id}:v{event_version}"
        if event_ref in seen:
            raise ContractError(f"duplicate news enrichment event: {event_ref}")
        seen.add(event_ref)

        available_at = parse_datetime(row.get("available_at", ""), "available_at")
        if available_at > generated_at:
            raise ContractError(
                f"news enrichment available_at exceeds generated_at: {event_ref}"
            )
        source_urls_value = row.get("source_urls")
        if not isinstance(source_urls_value, list) or not source_urls_value:
            raise ContractError(
                f"news enrichment requires external source URLs: {event_ref}"
            )
        source_urls = tuple(
            sorted({str(item).strip() for item in source_urls_value})
        )
        if not source_urls or not all(_external_url(item) for item in source_urls):
            raise ContractError(
                f"news enrichment contains a non-external source URL: {event_ref}"
            )

        published_value = row.get("published_at")
        published_at = (
            parse_datetime(published_value, "published_at")
            if published_value not in (None, "")
            else None
        )
        if published_at and published_at > available_at:
            raise ContractError(
                f"enriched published_at exceeds available_at: {event_ref}"
            )
        novelty_value = row.get("novelty")
        novelty: float | None = None
        if novelty_value not in (None, ""):
            try:
                novelty = float(novelty_value)
            except (TypeError, ValueError) as exc:
                raise ContractError(f"invalid enrichment novelty: {event_ref}") from exc
            if not isfinite(novelty) or not 0.0 <= novelty <= 1.0:
                raise ContractError(
                    f"enrichment novelty must be in [0, 1]: {event_ref}"
                )
        mappings_value = row.get("mappings", [])
        if not isinstance(mappings_value, list):
            raise ContractError(f"enrichment mappings must be a list: {event_ref}")
        mappings = tuple(
            _mapping_from_dict(item, event_ref) for item in mappings_value
        )
        if published_at is None and novelty is None and not mappings:
            raise ContractError(
                f"news enrichment event does not resolve any field: {event_ref}"
            )
        events.append(
            EventEnrichment(
                event_ref=event_ref,
                available_at=available_at,
                source_urls=source_urls,
                published_at=published_at,
                novelty=novelty,
                mappings=mappings,
            )
        )

    event_refs = tuple(sorted(item.event_ref for item in events))
    if selection is None:
        selection_policy = "all_requested"
        requested_event_refs = event_refs
        unresolved_input_event_refs: tuple[str, ...] = ()
    else:
        selection_policy = str(selection.get("policy", "")).strip()
        requested_value = selection.get("requested_event_refs")
        enriched_value = selection.get("enriched_event_refs")
        unresolved_value = selection.get("unresolved_event_refs")
        if (
            selection_policy
            not in {"all_requested", "eligible_published_at_only"}
            or not isinstance(requested_value, list)
            or not isinstance(enriched_value, list)
            or not isinstance(unresolved_value, list)
            or not all(
                isinstance(item, str) and item.strip()
                for values in (requested_value, enriched_value, unresolved_value)
                for item in values
            )
        ):
            raise ContractError("news enrichment source selection is invalid")
        requested_event_refs = tuple(sorted(requested_value))
        enriched_event_refs = tuple(sorted(enriched_value))
        unresolved_input_event_refs = tuple(sorted(unresolved_value))
        if (
            len(requested_event_refs) != len(set(requested_event_refs))
            or len(enriched_event_refs) != len(set(enriched_event_refs))
            or len(unresolved_input_event_refs)
            != len(set(unresolved_input_event_refs))
            or enriched_event_refs != event_refs
            or set(enriched_event_refs) & set(unresolved_input_event_refs)
            or set(requested_event_refs)
            != set(enriched_event_refs) | set(unresolved_input_event_refs)
            or (
                selection_policy == "all_requested"
                and unresolved_input_event_refs
            )
        ):
            raise ContractError(
                "news enrichment source selection does not match event coverage"
            )

    return NewsEnrichment(
        path=source_path,
        sha256=_sha256_file(source_path),
        generated_at=generated_at,
        repository=repository,
        commit=commit.casefold(),
        pipeline_run_id=pipeline_run_id,
        methodology=methodology,
        input_artifacts=input_artifacts,
        selection_policy=selection_policy,
        requested_event_refs=requested_event_refs,
        unresolved_input_event_refs=unresolved_input_event_refs,
        events=tuple(events),
    )


def apply_news_enrichment(
    bundle: NewsExport, enrichment_path: str | Path
) -> NewsExport:
    enrichment = load_news_enrichment(enrichment_path)
    event_by_ref = {item.ref: item for item in bundle.events}
    entries = {item.event_ref: item for item in enrichment.events}
    unknown_refs = sorted(set(entries) - set(event_by_ref))
    if unknown_refs:
        raise ContractError(
            f"news enrichment references unknown event versions: {unknown_refs}"
        )

    manifest = json.loads(json.dumps(bundle.manifest))
    degradations_value = manifest.get("contract_degradations_by_event_version")
    degradations = (
        {
            str(ref): list(values)
            for ref, values in degradations_value.items()
            if isinstance(values, list)
        }
        if isinstance(degradations_value, dict)
        else {}
    )
    placeholder_refs = set(manifest.get("placeholder_mapping_refs", []))
    source_urls_value = manifest.get("source_urls_by_event_version")
    source_urls = (
        {
            str(ref): list(values)
            for ref, values in source_urls_value.items()
            if isinstance(values, list)
        }
        if isinstance(source_urls_value, dict)
        else {}
    )
    mapping_index = {
        (item.event_ref, item.entity.casefold(), item.ticker): item
        for item in bundle.mappings
    }
    updated_events: list[EventSnapshot] = []

    for event in bundle.events:
        entry = entries.get(event.ref)
        if entry is None:
            updated_events.append(event)
            continue
        corrected_published = entry.published_at or event.published_at
        corrected_observed = max(event.observed_at, entry.available_at)
        reference_date = corrected_published.date()
        for mapping in entry.mappings:
            if mapping.effective_from > reference_date or (
                mapping.effective_to and mapping.effective_to < reference_date
            ):
                raise ContractError(
                    f"enrichment mapping is not effective for {event.ref}: "
                    f"{mapping.entity}->{mapping.ticker}"
                )

        sectors = list(event.sectors)
        if entry.mappings:
            sectors = [item for item in sectors if item != "__UNMAPPED__"]
        entities = list(event.entities)
        sector_names = {item.casefold() for item in sectors}
        entity_names = {item.casefold() for item in entities}
        for mapping in entry.mappings:
            key = (event.ref, mapping.entity.casefold(), mapping.ticker)
            converted = EntityMapping(
                mapping.entity,
                mapping.ticker,
                mapping.sector,
                mapping.impact_multiplier,
                event.ref,
            )
            existing = mapping_index.get(key)
            if existing and existing != converted:
                raise ContractError(
                    f"enrichment mapping conflicts with existing mapping: "
                    f"{mapping.entity}->{mapping.ticker}"
                )
            mapping_index[key] = converted
            if (
                mapping.entity.casefold() not in sector_names
                and mapping.entity.casefold() not in entity_names
            ):
                entities.append(mapping.entity)
                entity_names.add(mapping.entity.casefold())

        updated = EventSnapshot.from_dict(
            {
                **event.to_dict(),
                "published_at": corrected_published.isoformat(),
                "observed_at": corrected_observed.isoformat(),
                "asof": max(event.asof, corrected_observed).isoformat(),
                "novelty": (
                    entry.novelty
                    if entry.novelty is not None
                    else event.novelty
                ),
                "entities": entities,
                "sectors": sectors,
            }
        )
        updated_events.append(updated)

        remaining = set(degradations.get(event.ref, []))
        if entry.published_at is not None:
            remaining.discard(RESOLVED_BY_PUBLISHED_AT)
        if entry.novelty is not None:
            remaining.discard(RESOLVED_BY_NOVELTY)
        if entry.mappings:
            remaining.difference_update(RESOLVED_BY_MAPPING)
            placeholder_refs.discard(event.ref)
        if remaining:
            degradations[event.ref] = sorted(remaining)
        else:
            degradations.pop(event.ref, None)
        source_urls[event.ref] = sorted(
            {
                *source_urls.get(event.ref, []),
                *entry.source_urls,
                *(item.source_url for item in entry.mappings),
            }
        )

    unresolved_refs = sorted(degradations)
    manifest["contract_degradations_by_event_version"] = dict(
        sorted(degradations.items())
    )
    manifest["placeholder_mapping_refs"] = sorted(placeholder_refs)
    manifest["source_urls_by_event_version"] = dict(sorted(source_urls.items()))
    manifest["enrichment"] = {
        "schema_version": "1.0",
        "artifact": str(enrichment.path),
        "sha256": enrichment.sha256,
        "synthetic": False,
        "source_repository": enrichment.repository,
        "source_commit": enrichment.commit,
        "pipeline_run_id": enrichment.pipeline_run_id,
        "methodology": enrichment.methodology,
        "input_artifacts": [
            {
                "artifact_type": item.artifact_type,
                "artifact": str(item.path),
                "sha256": item.sha256,
            }
            for item in enrichment.input_artifacts
        ],
        "selection": {
            "policy": enrichment.selection_policy,
            "requested_event_refs": list(enrichment.requested_event_refs),
            "enriched_event_refs": sorted(entries),
            "unresolved_event_refs": list(
                enrichment.unresolved_input_event_refs
            ),
        },
        "generated_at": enrichment.generated_at.isoformat(),
        "applied_event_refs": sorted(entries),
        "unresolved_event_refs": unresolved_refs,
    }
    return NewsExport(
        events=updated_events,
        evidence=dict(bundle.evidence),
        mappings=sorted(
            mapping_index.values(),
            key=lambda item: (item.event_ref or "", item.ticker, item.entity),
        ),
        manifest=manifest,
    )
