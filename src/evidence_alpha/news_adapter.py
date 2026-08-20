from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import csv
import json
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import (
    ContractError,
    EntityMapping,
    EventSnapshot,
    EvidenceRecord,
    parse_datetime,
)


JsonGetter = Callable[[str, float], dict[str, Any]]


def _default_get_json(url: str, timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        method="GET",
        headers={"Accept": "application/json", "User-Agent": "evidence-alpha/0.2"},
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - caller controls the base URL
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ContractError(f"news API returned a non-object payload: {url}")
    return payload


@dataclass
class NewsExport:
    events: list[EventSnapshot]
    evidence: dict[str, EvidenceRecord]
    mappings: list[EntityMapping]
    manifest: dict[str, Any]


class NewsAdapter:
    """Read-only adapter for the News Claws v1 HTTP API."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        get_json: JsonGetter | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if not self.base_url.startswith(("http://", "https://")):
            raise ContractError("news base URL must use http or https")
        self.timeout = timeout
        self.get_json = get_json or _default_get_json

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = urlencode({key: value for key, value in (params or {}).items() if value is not None})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        payload = self.get_json(url, self.timeout)
        if "data" not in payload:
            raise ContractError(f"news API envelope is missing data: {path}")
        if payload.get("data_version") not in (None, "v1"):
            raise ContractError(f"unsupported news data_version: {payload.get('data_version')}")
        return payload["data"]

    def list_events(self, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1:
            raise ContractError("news event limit must be positive")
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(items) < limit:
            page = self._get(
                "/api/v1/events",
                {"limit": min(100, limit - len(items)), "cursor": cursor},
            )
            if not isinstance(page, dict) or not isinstance(page.get("items"), list):
                raise ContractError("news event list must contain data.items")
            items.extend(item for item in page["items"] if isinstance(item, dict))
            cursor = page.get("next_cursor")
            if not cursor:
                break
        return items[:limit]

    def export(self, *, limit: int = 100, allow_synthetic: bool = False) -> NewsExport:
        summaries = self.list_events(limit)
        events: list[EventSnapshot] = []
        evidence: dict[str, EvidenceRecord] = {}
        mappings: dict[tuple[str, str], EntityMapping] = {}
        synthetic_refs: list[str] = []
        timestamp_adjustments: list[dict[str, str]] = []
        source_urls: dict[str, list[str]] = {}

        for summary in summaries:
            event_id = str(summary.get("id", "")).strip()
            if not event_id:
                raise ContractError("news event is missing id")
            timeline = self._get(f"/api/v1/events/{event_id}/timeline")
            versions = timeline.get("items", []) if isinstance(timeline, dict) else []
            if not versions:
                raise ContractError(f"news event has no version timeline: {event_id}")
            for version_row in sorted(versions, key=lambda item: int(item.get("version", 0))):
                version_number = int(version_row.get("version", 0))
                if version_number < 1:
                    raise ContractError(f"invalid news event version: {event_id}")
                detail = self._get(
                    f"/api/v1/events/{event_id}", {"version": version_number}
                )
                converted, records, direct_mappings, metadata = self._convert_version(detail)
                if metadata["synthetic"]:
                    synthetic_refs.append(converted.ref)
                    if not allow_synthetic:
                        raise ContractError(
                            f"synthetic news event rejected: {converted.ref}; "
                            "use explicit allow_synthetic only for research fixtures"
                        )
                events.append(converted)
                for record in records:
                    existing = evidence.get(record.evidence_id)
                    if existing and existing != record:
                        raise ContractError(
                            f"evidence ID changed across event versions: {record.evidence_id}"
                        )
                    evidence[record.evidence_id] = record
                for mapping in direct_mappings:
                    mappings[(mapping.entity.casefold(), mapping.ticker)] = mapping
                if metadata["timestamp_adjusted"]:
                    timestamp_adjustments.append(
                        {"event_ref": converted.ref, "observed_at": converted.observed_at.isoformat()}
                    )
                source_urls[converted.ref] = metadata["source_urls"]

        self._assert_immutable(events)
        return NewsExport(
            events=events,
            evidence=evidence,
            mappings=sorted(mappings.values(), key=lambda item: (item.ticker, item.entity)),
            manifest={
                "adapter": "news-claws-v1-read-only",
                "base_url": self.base_url,
                "event_count": len(summaries),
                "event_version_count": len(events),
                "evidence_count": len(evidence),
                "synthetic": bool(synthetic_refs),
                "synthetic_event_refs": sorted(synthetic_refs),
                "synthetic_allowed": allow_synthetic,
                "timestamp_policy": "observed_at=max(relevant published_at, discovered_at, version.created_at)",
                "timestamp_adjustments": timestamp_adjustments,
                "source_urls_by_event_version": source_urls,
            },
        )

    def _convert_version(
        self, detail: dict[str, Any]
    ) -> tuple[EventSnapshot, list[EvidenceRecord], list[EntityMapping], dict[str, Any]]:
        if not isinstance(detail, dict) or not isinstance(detail.get("version"), dict):
            raise ContractError("news event detail is missing version data")
        version = detail["version"]
        event_id = str(detail.get("id", version.get("event_id", ""))).strip()
        version_number = int(version.get("version", 0))

        articles = [item for item in detail.get("articles", []) if isinstance(item, dict)]
        article_by_url = {
            str(item.get("canonical_url", "")): item
            for item in articles
            if str(item.get("canonical_url", "")).strip()
        }
        raw_evidence = [
            item
            for claim in detail.get("claims", [])
            if isinstance(claim, dict)
            for item in claim.get("evidence", [])
            if isinstance(item, dict)
        ]
        unique_evidence = {str(item.get("id", "")): item for item in raw_evidence if item.get("id")}
        if not unique_evidence:
            raise ContractError(f"news event version has no traceable evidence: {event_id}:v{version_number}")

        relevant_urls = {
            str(item.get("canonical_url", "")).strip()
            for item in unique_evidence.values()
            if str(item.get("canonical_url", "")).strip()
        }
        relevant_articles = [article_by_url[url] for url in relevant_urls if url in article_by_url]
        if not relevant_articles:
            relevant_articles = articles
        if not relevant_articles:
            raise ContractError(f"news event version has no source article: {event_id}:v{version_number}")

        published_times = [
            parse_datetime(item["published_at"], "article.published_at")
            for item in relevant_articles
            if item.get("published_at")
        ]
        if not published_times:
            raise ContractError(f"source article has no published_at: {event_id}:v{version_number}")
        discovered_times = [
            parse_datetime(item["discovered_at"], "article.discovered_at")
            for item in relevant_articles
            if item.get("discovered_at")
        ]
        version_created = parse_datetime(version.get("created_at", ""), "version.created_at")
        published_at = min(published_times)
        observed_at = max([*published_times, *discovered_times, version_created])
        timestamp_adjusted = any(value < published_at for value in [*discovered_times, version_created])

        records: list[EvidenceRecord] = []
        for evidence_id, item in sorted(unique_evidence.items()):
            source_url = str(item.get("canonical_url", "")).strip()
            article = article_by_url.get(source_url, {})
            captured_candidates = [published_at]
            for key, field_name in (
                (item.get("created_at"), "evidence.created_at"),
                (article.get("published_at"), "article.published_at"),
                (article.get("discovered_at"), "article.discovered_at"),
            ):
                if key:
                    captured_candidates.append(parse_datetime(key, field_name))
            records.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    source_url=source_url or f"{self.base_url}/events/{event_id}",
                    captured_at=max(captured_candidates),
                    source_name=str(item.get("source_name", "")).strip(),
                )
            )

        company_impacts = [item for item in detail.get("company_impacts", []) if isinstance(item, dict)]
        industry_impacts = [item for item in detail.get("industry_impacts", []) if isinstance(item, dict)]
        tickers = sorted(
            {
                str(item.get("ticker", "")).strip().upper()
                for item in company_impacts
                if str(item.get("ticker", "")).strip()
            }
        )
        sectors = sorted(
            {
                str(item.get("industry_name") or item.get("industry_id") or "").strip()
                for item in industry_impacts
                if str(item.get("industry_name") or item.get("industry_id") or "").strip()
            }
        )
        if not tickers and not sectors:
            raise ContractError(f"news event version has no investable impact mapping: {event_id}:v{version_number}")
        primary_sector = sectors[0] if sectors else "Unknown"
        direct_mappings = [EntityMapping(ticker, ticker, primary_sector, 1.0) for ticker in tickers]

        direction = _direction(version.get("sentiment_label"), version.get("sentiment_score"))
        breakdown = version.get("reliability_breakdown") or {}
        conflict = float(breakdown.get("conflict_penalty", 0.0) or 0.0) > 0 or any(
            str(item.get("stance", "")).casefold() in {"contradicts", "conflicts"}
            for item in unique_evidence.values()
        )
        horizons = [
            _horizon_days(item.get("horizon"))
            for item in [*company_impacts, *industry_impacts]
        ]
        event = EventSnapshot.from_dict(
            {
                "event_id": event_id,
                "event_version": version_number,
                "published_at": published_at.isoformat(),
                "observed_at": observed_at.isoformat(),
                "event_type": "news_event",
                "direction": direction,
                "confidence": _unit_interval(version.get("reliability", 0)),
                "novelty": _unit_interval(version.get("novelty", 0)),
                "conflict": conflict,
                "impact_horizon_days": max(horizons, default=5),
                "entities": tickers,
                "sectors": sectors if not tickers else [],
                "evidence_ids": sorted(unique_evidence),
                "status": str(detail.get("state", "unknown")).strip() or "unknown",
                "asof": observed_at.isoformat(),
            }
        )
        synthetic = any(
            bool((item.get("metadata") or {}).get("synthetic_demo"))
            or str((item.get("metadata") or {}).get("license_policy", "")).casefold()
            == "synthetic-demo"
            for item in relevant_articles
        )
        return event, records, direct_mappings, {
            "synthetic": synthetic,
            "timestamp_adjusted": timestamp_adjusted,
            "source_urls": sorted(relevant_urls),
        }

    @staticmethod
    def _assert_immutable(events: list[EventSnapshot]) -> None:
        seen: dict[tuple[str, int], EventSnapshot] = {}
        for event in events:
            key = (event.event_id, event.event_version)
            if key in seen and seen[key] != event:
                raise ContractError(f"news event version changed during export: {event.ref}")
            seen[key] = event


def _unit_interval(value: Any) -> float:
    number = float(value or 0.0)
    return max(0.0, min(1.0, number / 100.0 if number > 1.0 else number))


def _direction(label: Any, score: Any) -> str:
    normalized = str(label or "").strip().casefold()
    if normalized in {"positive", "bullish"}:
        return "positive"
    if normalized in {"negative", "bearish"}:
        return "negative"
    if normalized in {"uncertain", "mixed", "conflicting"}:
        return "uncertain"
    numeric = float(score or 0.0)
    if numeric > 0.05:
        return "positive"
    if numeric < -0.05:
        return "negative"
    return "neutral"


def _horizon_days(value: Any) -> int:
    normalized = str(value or "").strip().casefold()
    return {"immediate": 1, "short": 5, "medium": 20, "long": 60}.get(normalized, 5)


def write_news_export(bundle: NewsExport, output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "events": output / "events.json",
        "evidence": output / "evidence.json",
        "mappings": output / "mappings.csv",
        "manifest": output / "news_manifest.json",
    }
    paths["events"].write_text(
        json.dumps([item.to_dict() for item in bundle.events], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["evidence"].write_text(
        json.dumps(
            {
                "evidence": [
                    {
                        "evidence_id": item.evidence_id,
                        "source_url": item.source_url,
                        "captured_at": item.captured_at.isoformat(),
                        "source_name": item.source_name,
                    }
                    for item in sorted(bundle.evidence.values(), key=lambda record: record.evidence_id)
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    with paths["mappings"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["entity", "ticker", "sector", "impact_multiplier"]
        )
        writer.writeheader()
        for item in bundle.mappings:
            writer.writerow(
                {
                    "entity": item.entity,
                    "ticker": item.ticker,
                    "sector": item.sector,
                    "impact_multiplier": item.impact_multiplier,
                }
            )
    paths["manifest"].write_text(
        json.dumps(bundle.manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return paths
