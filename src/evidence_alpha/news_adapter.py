from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import csv
import json
import re
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


def _default_get_json(
    url: str, timeout: float, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "evidence-alpha/0.5",
            **(headers or {}),
        },
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
        admin_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if not self.base_url.startswith(("http://", "https://")):
            raise ContractError("news base URL must use http or https")
        self.timeout = timeout
        request_headers = (
            {"Authorization": f"Bearer {admin_token}"} if admin_token else {}
        )
        self.get_json = get_json or (
            lambda url, timeout: _default_get_json(url, timeout, request_headers)
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = urlencode({key: value for key, value in (params or {}).items() if value is not None})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        payload = self.get_json(url, self.timeout)
        if "data" in payload:
            if payload.get("data_version") not in (None, "v1"):
                raise ContractError(
                    f"unsupported news data_version: {payload.get('data_version')}"
                )
            return payload["data"]
        if "items" in payload or "event" in payload:
            return payload
        raise ContractError(f"news API response has no supported payload: {path}")

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
        placeholder_mapping_refs: list[str] = []
        timestamp_adjustments: list[dict[str, str]] = []
        source_urls: dict[str, list[str]] = {}
        contract_degradations: dict[str, list[str]] = {}
        api_dialects: set[str] = set()

        for summary in summaries:
            event_id = str(summary.get("id", "")).strip()
            if not event_id:
                raise ContractError("news event is missing id")
            if "is_demo" in summary:
                api_dialects.add("news-claws-current")
                detail = self._get(f"/api/v1/events/{event_id}")
                converted, records, direct_mappings, metadata = (
                    self._convert_current_event(detail)
                )
                if metadata["synthetic"]:
                    synthetic_refs.append(converted.ref)
                    if not allow_synthetic:
                        raise ContractError(
                            f"synthetic news event rejected: {converted.ref}; "
                            "use explicit allow_synthetic only for research fixtures"
                        )
                if metadata["placeholder_tickers"]:
                    placeholder_mapping_refs.append(converted.ref)
                if metadata["contract_degradations"]:
                    contract_degradations[converted.ref] = metadata[
                        "contract_degradations"
                    ]
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
                source_urls[converted.ref] = metadata["source_urls"]
                continue
            api_dialects.add("news-claws-v1")
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
                "placeholder_mapping_refs": sorted(placeholder_mapping_refs),
                "synthetic_allowed": allow_synthetic,
                "api_dialects": sorted(api_dialects),
                "contract_degradations_by_event_version": contract_degradations,
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

    def _convert_current_event(
        self, detail: dict[str, Any]
    ) -> tuple[EventSnapshot, list[EvidenceRecord], list[EntityMapping], dict[str, Any]]:
        if not isinstance(detail, dict) or not isinstance(detail.get("event"), dict):
            raise ContractError("current News Claws detail is missing event data")
        event_row = detail["event"]
        report = detail.get("report")
        if not isinstance(report, dict):
            raise ContractError(
                f"current News Claws event has no immutable report: {event_row.get('id')}"
            )
        event_id = str(event_row.get("id", "")).strip()
        version_number = int(report.get("version", 0) or 0)
        if not event_id or version_number < 1:
            raise ContractError("current News Claws event/report identity is invalid")

        articles = [item for item in detail.get("articles", []) if isinstance(item, dict)]
        article_by_id = {
            str(item.get("id")): item for item in articles if item.get("id")
        }
        source_urls = sorted(
            {
                str(item.get("url", "")).strip()
                for item in articles
                if str(item.get("url", "")).strip()
            }
        )
        if not source_urls:
            raise ContractError(
                f"current News Claws event has no source article: {event_id}:v{version_number}"
            )

        degradations: list[str] = []
        published_times = [
            _parse_current_utc(item.get("published_at"), "article.published_at")
            for item in articles
            if item.get("published_at")
        ]
        if published_times:
            published_at = min(published_times)
        else:
            published_at = _parse_current_utc(
                event_row.get("first_seen"), "event.first_seen"
            )
            degradations.append("published_at_fell_back_to_first_seen")
        observed_candidates = [
            published_at,
            _parse_current_utc(event_row.get("first_seen"), "event.first_seen"),
            _parse_current_utc(event_row.get("last_seen"), "event.last_seen"),
            _parse_current_utc(report.get("generated_at"), "report.generated_at"),
            _parse_current_utc(
                report.get("data_cutoff_at"), "report.data_cutoff_at"
            ),
        ]
        observed_at = max(observed_candidates)

        evidence_rows = [
            item for item in detail.get("evidence", []) if isinstance(item, dict)
        ]
        records: list[EvidenceRecord] = []
        for item in evidence_rows:
            evidence_id = str(item.get("id", "")).strip()
            article = article_by_id.get(str(item.get("article_id", "")), {})
            source_url = str(article.get("url", "")).strip()
            if not evidence_id or not source_url:
                continue
            captured_candidates = [published_at, observed_at]
            if item.get("fetched_at"):
                captured_candidates.append(
                    _parse_current_utc(item.get("fetched_at"), "evidence.fetched_at")
                )
            records.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    source_url=source_url,
                    captured_at=max(captured_candidates),
                    source_name=str(article.get("source_name", "")).strip(),
                )
            )
        if not records:
            raise ContractError(
                f"current News Claws event has no traceable evidence: {event_id}:v{version_number}"
            )

        industries = [
            item for item in detail.get("industries", []) if isinstance(item, dict)
        ]
        companies = [
            item for item in detail.get("companies", []) if isinstance(item, dict)
        ]
        sector_names = {
            str(item.get("name", "")).strip()
            for item in industries
            if str(item.get("name", "")).strip()
        }
        corrupted_sector_labels = sorted(
            name for name in sector_names if not _usable_mapping_label(name)
        )
        sectors = sorted(sector_names - set(corrupted_sector_labels))
        if corrupted_sector_labels:
            degradations.append(
                "industry_mapping_contains_encoding_replacement"
            )
        tickers: list[str] = []
        placeholder_tickers: list[str] = []
        for company in companies:
            identifiers = company.get("identifiers")
            identifiers = identifiers if isinstance(identifiers, dict) else {}
            ticker = str(identifiers.get("ticker", "")).strip().upper()
            if not ticker:
                continue
            if _placeholder_ticker(ticker):
                placeholder_tickers.append(ticker)
            else:
                tickers.append(ticker)
        tickers = sorted(set(tickers))
        placeholder_tickers = sorted(set(placeholder_tickers))
        if not tickers and not sectors:
            degradations.append("no_investable_company_or_industry_mapping")
            sectors = ["__UNMAPPED__"]

        content = report.get("content_json")
        content = content if isinstance(content, dict) else {}
        novelty_value = content.get("novelty")
        if novelty_value is None:
            novelty = 0.0
            degradations.append("novelty_not_exposed_by_api")
        else:
            novelty = _unit_interval(novelty_value)
        directions = {
            str(item.get("direction", "")).strip().casefold()
            for item in [*companies, *industries]
            if str(item.get("direction", "")).strip()
        }
        direction = _current_direction(content.get("overall_tone"), directions)
        verification = detail.get("verification")
        verification = verification if isinstance(verification, dict) else {}
        confidence = _confidence_value(verification.get("confidence"))
        if confidence == 0.0:
            confidence = max(
                (
                    _confidence_value(item.get("confidence"))
                    for item in [*companies, *industries]
                ),
                default=0.0,
            )
        horizons = [
            _horizon_days(item.get("horizon"))
            for item in [*companies, *industries]
        ]
        evidence_ids = sorted(item.evidence_id for item in records)
        event = EventSnapshot.from_dict(
            {
                "event_id": event_id,
                "event_version": version_number,
                "published_at": published_at.isoformat(),
                "observed_at": observed_at.isoformat(),
                "event_type": "news_event",
                "direction": direction,
                "confidence": confidence,
                "novelty": novelty,
                "conflict": bool(
                    {"positive", "negative"}.issubset(directions)
                    or verification.get("status") == "conflicting"
                ),
                "impact_horizon_days": max(horizons, default=5),
                "entities": tickers,
                "sectors": sectors if not tickers else [],
                "evidence_ids": evidence_ids,
                "status": str(event_row.get("state", "unknown")).strip() or "unknown",
                "asof": observed_at.isoformat(),
            }
        )
        primary_sector = sectors[0] if sectors else "Unknown"
        mappings = [
            EntityMapping(ticker, ticker, primary_sector, 1.0)
            for ticker in tickers
        ]
        return event, records, mappings, {
            "synthetic": bool(event_row.get("is_demo")),
            "placeholder_tickers": placeholder_tickers,
            "source_urls": source_urls,
            "contract_degradations": degradations,
        }

    @staticmethod
    def _assert_immutable(events: list[EventSnapshot]) -> None:
        seen: dict[tuple[str, int], EventSnapshot] = {}
        for event in events:
            key = (event.event_id, event.event_version)
            if key in seen and seen[key] != event:
                raise ContractError(f"news event version changed during export: {event.ref}")
            seen[key] = event


def _parse_current_utc(value: Any, field_name: str) -> datetime:
    text = str(value or "").strip()
    if text and not text.endswith(("Z", "z")) and not re.search(
        r"[+-]\d\d:\d\d$", text
    ):
        text = f"{text}+00:00"
    return parse_datetime(text, field_name)


def _placeholder_ticker(value: str) -> bool:
    normalized = value.strip().upper()
    return (
        not re.fullmatch(r"[A-Z0-9.^-]{1,20}", normalized)
        or normalized.startswith(("DEMO-", "TEST-", "SYNTH-", "PLACEHOLDER-"))
    )


def _usable_mapping_label(value: str) -> bool:
    return bool(value.strip()) and "\ufffd" not in value


def _current_direction(label: Any, impact_directions: set[str]) -> str:
    normalized = str(label or "").strip().casefold()
    if normalized in {"positive", "negative", "neutral"}:
        return normalized
    if normalized in {"mixed", "uncertain", "conflicting"}:
        return "uncertain"
    supported = impact_directions & {"positive", "negative", "neutral"}
    if supported == {"positive"}:
        return "positive"
    if supported == {"negative"}:
        return "negative"
    if supported == {"neutral"} or not supported:
        return "neutral"
    return "uncertain"


def _confidence_value(value: Any) -> float:
    normalized = str(value or "").strip().casefold()
    if normalized in {"high", "verified"}:
        return 0.85
    if normalized in {"medium", "moderate"}:
        return 0.65
    if normalized in {"low", "limited"}:
        return 0.40
    try:
        return _unit_interval(value)
    except (TypeError, ValueError):
        return 0.0


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
            handle,
            fieldnames=[
                "entity",
                "ticker",
                "sector",
                "impact_multiplier",
                "event_ref",
            ],
        )
        writer.writeheader()
        for item in bundle.mappings:
            writer.writerow(
                {
                    "entity": item.entity,
                    "ticker": item.ticker,
                    "sector": item.sector,
                    "impact_multiplier": item.impact_multiplier,
                    "event_ref": item.event_ref or "",
                }
            )
    paths["manifest"].write_text(
        json.dumps(bundle.manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return paths
