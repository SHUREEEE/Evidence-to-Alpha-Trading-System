from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from hashlib import sha256
import json
from typing import Any


class ContractError(ValueError):
    """Raised when an input violates a point-in-time contract."""


def parse_datetime(value: str | datetime, field_name: str) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            result = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ContractError(f"{field_name} must be ISO-8601: {value!r}") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ContractError(f"{field_name} must include a timezone: {value!r}")
    return result


def parse_date(value: str | date, field_name: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ContractError(f"{field_name} must be ISO date: {value!r}") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EventSnapshot:
    event_id: str
    event_version: int
    published_at: datetime
    observed_at: datetime
    event_type: str
    direction: str
    confidence: float
    novelty: float
    conflict: bool
    impact_horizon_days: int
    entities: tuple[str, ...]
    sectors: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    status: str
    asof: datetime

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventSnapshot":
        required = {
            "event_id",
            "event_version",
            "published_at",
            "observed_at",
            "event_type",
            "direction",
            "confidence",
            "novelty",
            "conflict",
            "impact_horizon_days",
            "entities",
            "evidence_ids",
            "status",
            "asof",
        }
        missing = sorted(required - set(data))
        if missing:
            raise ContractError(f"event is missing required fields: {', '.join(missing)}")
        event = cls(
            event_id=str(data["event_id"]).strip(),
            event_version=int(data["event_version"]),
            published_at=parse_datetime(data["published_at"], "published_at"),
            observed_at=parse_datetime(data["observed_at"], "observed_at"),
            event_type=str(data["event_type"]).strip(),
            direction=str(data["direction"]).strip().lower(),
            confidence=float(data["confidence"]),
            novelty=float(data["novelty"]),
            conflict=bool(data["conflict"]),
            impact_horizon_days=int(data["impact_horizon_days"]),
            entities=tuple(str(item).strip() for item in data.get("entities", []) if str(item).strip()),
            sectors=tuple(str(item).strip() for item in data.get("sectors", []) if str(item).strip()),
            evidence_ids=tuple(str(item).strip() for item in data.get("evidence_ids", []) if str(item).strip()),
            status=str(data["status"]).strip(),
            asof=parse_datetime(data["asof"], "asof"),
        )
        event.validate()
        return event

    def validate(self) -> None:
        if not self.event_id or not self.event_type or not self.status:
            raise ContractError("event_id, event_type, and status must be non-empty")
        if self.event_version < 1:
            raise ContractError("event_version must be >= 1")
        if self.direction not in {"positive", "negative", "neutral", "uncertain"}:
            raise ContractError(f"unsupported direction: {self.direction}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ContractError("confidence must be in [0, 1]")
        if not 0.0 <= self.novelty <= 1.0:
            raise ContractError("novelty must be in [0, 1]")
        if self.impact_horizon_days < 1:
            raise ContractError("impact_horizon_days must be >= 1")
        if not self.entities and not self.sectors:
            raise ContractError("event must contain at least one entity or sector")
        if not self.evidence_ids:
            raise ContractError("event must reference at least one evidence item")
        if self.observed_at < self.published_at:
            raise ContractError("observed_at must not be earlier than published_at")
        if self.asof < self.observed_at:
            raise ContractError("asof must not be earlier than observed_at")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("published_at", "observed_at", "asof"):
            result[key] = result[key].isoformat()
        result["entities"] = list(self.entities)
        result["sectors"] = list(self.sectors)
        result["evidence_ids"] = list(self.evidence_ids)
        return result

    @property
    def ref(self) -> str:
        return f"{self.event_id}:v{self.event_version}"


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source_url: str
    captured_at: datetime
    source_name: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRecord":
        evidence_id = str(data.get("evidence_id", "")).strip()
        source_url = str(data.get("source_url", "")).strip()
        if not evidence_id or not source_url:
            raise ContractError("evidence_id and source_url are required")
        return cls(
            evidence_id=evidence_id,
            source_url=source_url,
            captured_at=parse_datetime(data.get("captured_at", ""), "captured_at"),
            source_name=str(data.get("source_name", "")).strip(),
        )


@dataclass(frozen=True)
class EntityMapping:
    entity: str
    ticker: str
    sector: str
    impact_multiplier: float = 1.0


@dataclass(frozen=True)
class PriceBar:
    trade_date: date
    ticker: str
    open: float
    close: float


@dataclass(frozen=True)
class BaselineWeight:
    asof: date
    ticker: str
    weight: float
    factor_version: str


@dataclass(frozen=True)
class EventSignal:
    signal_id: str
    event_id: str
    event_version: int
    ticker: str
    sector: str
    signal_asof: datetime
    raw_strength: float
    decayed_strength: float
    evidence_ids: tuple[str, ...]
    config_hash: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["signal_asof"] = self.signal_asof.isoformat()
        result["evidence_ids"] = list(self.evidence_ids)
        return result


@dataclass(frozen=True)
class Order:
    order_id: str
    run_id: str
    created_at: datetime
    ticker: str
    side: str
    quantity: int
    target_weight: float
    factor_version: str
    signal_ids: tuple[str, ...] = field(default_factory=tuple)
    event_refs: tuple[str, ...] = field(default_factory=tuple)
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["created_at"] = self.created_at.isoformat()
        for key in ("signal_ids", "event_refs", "evidence_ids"):
            result[key] = list(result[key])
        return result


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    run_id: str
    trade_date: date
    ticker: str
    side: str
    quantity: int
    fill_price: float
    commission: float
    slippage_bps: float

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["trade_date"] = self.trade_date.isoformat()
        return result

