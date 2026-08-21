from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from html.parser import HTMLParser
import gzip
import json
import re
import time
from typing import Any, Callable, Iterable
from urllib.request import Request, urlopen

from .models import ContractError, EntityMapping, EventSnapshot, EvidenceRecord, parse_date, parse_datetime
from .news_adapter import NewsExport, write_news_export


JsonFetcher = Callable[[str, str], dict[str, Any]]
TextFetcher = Callable[[str, str], str]
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PLACEHOLDER_EMAIL_HOSTS = {"example.com", "example.org", "example.net", "invalid", "test"}


@dataclass(frozen=True)
class SecCompany:
    ticker: str
    cik: str

    def validate(self) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", self.ticker):
            raise ContractError(f"invalid SEC ticker: {self.ticker!r}")
        if not re.fullmatch(r"\d{10}", self.cik):
            raise ContractError(f"SEC CIK must contain 10 digits: {self.cik!r}")


@dataclass(frozen=True)
class SecExportConfig:
    start_date: date
    end_date: date
    forms: tuple[str, ...] = ("8-K", "10-Q", "10-K")
    max_events: int = 100
    fetch_documents: bool = True
    request_delay_seconds: float = 0.2
    timeout_seconds: float = 30.0

    def validate(self) -> None:
        if self.start_date > self.end_date:
            raise ContractError("SEC export start_date must not be after end_date")
        if not self.forms or any(not str(form).strip() for form in self.forms):
            raise ContractError("SEC export forms must not be empty")
        if self.max_events < 1:
            raise ContractError("SEC export max_events must be positive")
        if self.request_delay_seconds < 0 or self.timeout_seconds <= 0:
            raise ContractError("SEC export request timing is invalid")


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return " ".join(self.parts)


def parse_company_spec(value: str) -> SecCompany:
    text = str(value).strip()
    if "=" not in text:
        raise ContractError("SEC company must use TICKER=10_DIGIT_CIK")
    ticker, cik = (part.strip() for part in text.split("=", 1))
    company = SecCompany(ticker.upper(), cik.zfill(10))
    company.validate()
    return company


def validate_user_agent(user_agent: str) -> None:
    value = str(user_agent or "").strip()
    match = EMAIL_RE.search(value)
    if not value or not match:
        raise ContractError("SEC User-Agent must identify the client and include a real contact email")
    host = match.group(0).rsplit("@", 1)[1].casefold()
    if host in PLACEHOLDER_EMAIL_HOSTS or host.endswith((".invalid", ".test")):
        raise ContractError("SEC User-Agent must not use a placeholder email host")


def _request_bytes(url: str, user_agent: str, timeout: float) -> bytes:
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json, text/html, */*",
            "Accept-Encoding": "gzip",
            "User-Agent": user_agent,
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed SEC host constructed below
            body = response.read()
    except OSError as exc:
        raise ContractError(f"SEC request failed: {url} ({type(exc).__name__})") from exc
    return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body


def _default_json_fetcher(url: str, user_agent: str, timeout: float = 30.0) -> dict[str, Any]:
    try:
        payload = json.loads(_request_bytes(url, user_agent, timeout).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"SEC JSON response is invalid: {url}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"SEC JSON response must be an object: {url}")
    return payload


def _default_text_fetcher(url: str, user_agent: str, timeout: float = 30.0) -> str:
    body = _request_bytes(url, user_agent, timeout)
    return body.decode("utf-8", errors="replace")


def _filing_url(cik: str, accession: str, primary_document: str) -> str:
    numeric_cik = str(int(cik))
    accession_path = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_path}/{primary_document}"


def _submission_url(cik: str) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik}.json"


def _acceptance_time(value: Any, filing_date: str) -> datetime:
    if value:
        return parse_datetime(str(value), "SEC acceptanceDateTime")
    return datetime.combine(parse_date(filing_date, "SEC filingDate"), datetime.max.time(), tzinfo=timezone.utc)


def _sector_from_sic(sic: Any) -> str:
    try:
        number = int(str(sic or "0"))
    except ValueError:
        return "SEC disclosure"
    if 1300 <= number < 1500:
        return "Materials"
    if 2000 <= number < 4000:
        return "Industrials"
    if 4800 <= number < 5000:
        return "Communication Services"
    if 5000 <= number < 5200:
        return "Consumer Discretionary"
    if 5200 <= number < 6000:
        return "Consumer Staples"
    if 6000 <= number < 6800:
        return "Financials"
    if 7000 <= number < 9000:
        return "Technology and Services"
    return "SEC disclosure"


_POSITIVE_TERMS = ("increase", "increased", "growth", "record", "strong", "improved", "profit", "revenue")
_NEGATIVE_TERMS = ("decrease", "decreased", "decline", "loss", "weak", "impairment", "restatement", "material weakness")


def _direction(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.casefold())
    positive = sum(normalized.count(term) for term in _POSITIVE_TERMS)
    negative = sum(normalized.count(term) for term in _NEGATIVE_TERMS)
    if positive - negative >= 2:
        return "positive"
    if negative - positive >= 2:
        return "negative"
    return "uncertain"


def _novelty(previous: Iterable[datetime], observed_at: datetime) -> float:
    cutoff = observed_at - timedelta(days=30)
    recent = sum(item >= cutoff for item in previous)
    return round(max(0.05, 1.0 / (1.0 + recent)), 6)


def _evenly_select(rows: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    if len(rows) <= maximum:
        return rows
    if maximum == 1:
        return [rows[len(rows) // 2]]
    indexes = [round(index * (len(rows) - 1) / (maximum - 1)) for index in range(maximum)]
    return [rows[index] for index in indexes]


def export_sec_edgar(
    companies: Iterable[SecCompany],
    *,
    user_agent: str,
    config: SecExportConfig,
    get_json: JsonFetcher | None = None,
    get_text: TextFetcher | None = None,
) -> NewsExport:
    """Export official SEC filings as immutable, point-in-time event versions."""
    validate_user_agent(user_agent)
    config.validate()
    company_list = list(companies)
    if not company_list:
        raise ContractError("SEC export requires at least one company")
    for company in company_list:
        company.validate()
    json_fetch = get_json or (lambda url, ua: _default_json_fetcher(url, ua, config.timeout_seconds))
    text_fetch = get_text or (lambda url, ua: _default_text_fetcher(url, ua, config.timeout_seconds))
    allowed_forms = {str(form).strip().upper() for form in config.forms}
    candidates: list[dict[str, Any]] = []
    input_hashes: dict[str, str] = {}
    company_metadata: dict[str, dict[str, Any]] = {}
    for company in company_list:
        payload = json_fetch(_submission_url(company.cik), user_agent)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        input_hashes[company.ticker] = sha256(raw).hexdigest()
        company_metadata[company.ticker] = payload
        recent = (payload.get("filings") or {}).get("recent")
        if not isinstance(recent, dict):
            raise ContractError(f"SEC submissions response lacks recent filings: {company.ticker}")
        forms = recent.get("form") or []
        for index, form in enumerate(forms):
            form_name = str(form or "").strip().upper()
            if form_name not in allowed_forms:
                continue
            filing_date = str((recent.get("filingDate") or [""])[index]).strip()
            if not filing_date:
                continue
            day = parse_date(filing_date, "SEC filingDate")
            if not config.start_date <= day <= config.end_date:
                continue
            row = {key: (recent.get(key) or [None])[index] for key in (
                "accessionNumber", "filingDate", "acceptanceDateTime", "reportDate", "form", "primaryDocument", "primaryDocDescription", "items"
            )}
            row.update({"ticker": company.ticker, "cik": company.cik, "sic": payload.get("sic"), "name": payload.get("name")})
            candidates.append(row)
        if config.request_delay_seconds:
            time.sleep(config.request_delay_seconds)
    candidates.sort(key=lambda item: (_acceptance_time(item.get("acceptanceDateTime"), str(item["filingDate"])), str(item["ticker"]), str(item["accessionNumber"])))
    selected = _evenly_select(candidates, config.max_events)
    if not selected:
        raise ContractError("SEC export found no filings in the requested date range")
    events: list[EventSnapshot] = []
    evidence: dict[str, EvidenceRecord] = {}
    mappings: list[EntityMapping] = []
    source_urls: dict[str, list[str]] = {}
    prior_by_ticker: dict[str, list[datetime]] = {}
    for row in selected:
        accession = str(row.get("accessionNumber") or "").strip()
        primary = str(row.get("primaryDocument") or "").strip()
        if not accession or not primary:
            raise ContractError("selected SEC filing is missing accessionNumber or primaryDocument")
        observed_at = _acceptance_time(row.get("acceptanceDateTime"), str(row["filingDate"]))
        url = _filing_url(str(row["cik"]), accession, primary)
        body = ""
        if config.fetch_documents:
            body = _VisibleText()
            parser = body
            parser.feed(text_fetch(url, user_agent))
            body = parser.text()
        direction = _direction(body or f"{row.get('form', '')} {row.get('items', '')} {row.get('primaryDocDescription', '')}")
        ticker = str(row["ticker"]).upper()
        event_id = f"sec_{ticker}_{accession.replace('-', '')}"
        event = EventSnapshot.from_dict({
            "event_id": event_id,
            "event_version": 1,
            "published_at": observed_at.isoformat(),
            "observed_at": observed_at.isoformat(),
            "event_type": f"sec_filing_{str(row.get('form')).lower().replace('-', '_')}",
            "direction": direction,
            "confidence": 0.75 if direction != "uncertain" else 0.55,
            "novelty": _novelty(prior_by_ticker.setdefault(ticker, []), observed_at),
            "conflict": False,
            "impact_horizon_days": 5,
            "entities": [ticker],
            "sectors": [],
            "evidence_ids": [f"sec_evidence_{accession.replace('-', '')}"],
            "status": "filed",
            "asof": observed_at.isoformat(),
        })
        prior_by_ticker[ticker].append(observed_at)
        record = EvidenceRecord(
            evidence_id=event.evidence_ids[0],
            source_url=url,
            captured_at=observed_at,
            source_name="SEC EDGAR official filing",
        )
        evidence[record.evidence_id] = record
        mappings.append(EntityMapping(ticker, ticker, _sector_from_sic(row.get("sic")), 1.0, event.ref))
        source_urls[event.ref] = [url]
        events.append(event)
        if config.request_delay_seconds and config.fetch_documents:
            time.sleep(config.request_delay_seconds)
    manifest = {
        "adapter": "sec-edgar-official-disclosures-v1",
        "api_dialects": ["sec-edgar-submissions-v1"],
        "event_count": len({item.event_id for item in events}),
        "event_version_count": len(events),
        "evidence_count": len(evidence),
        "synthetic": False,
        "synthetic_event_refs": [],
        "placeholder_mapping_refs": [],
        "contract_degradations_by_event_version": {},
        "source_urls_by_event_version": source_urls,
        "source_name": "SEC EDGAR",
        "source_terms_url": "https://www.sec.gov/edgar/searchedgar/accessing-edgar-data.htm",
        "source_input_hashes": input_hashes,
        "timestamp_policy": "acceptanceDateTime, with filing-date end-of-day fallback",
        "methodology": "official SEC filing text, deterministic keyword direction, and prior-30-day same-ticker novelty",
        "companies": [{"ticker": item.ticker, "cik": item.cik} for item in company_list],
        "coverage": {"start": config.start_date.isoformat(), "end": config.end_date.isoformat()},
    }
    return NewsExport(events=events, evidence=evidence, mappings=mappings, manifest=manifest)


def write_sec_export(bundle: NewsExport, output_dir: str) -> dict[str, str]:
    return {key: str(value) for key, value in write_news_export(bundle, output_dir).items()}
