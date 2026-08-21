from __future__ import annotations

from datetime import date
from tempfile import TemporaryDirectory
import unittest

from evidence_alpha.models import ContractError
from evidence_alpha.news_adapter import load_news_export
from evidence_alpha.sec_edgar import (
    SecCompany,
    SecExportConfig,
    export_sec_edgar,
    parse_company_spec,
    validate_user_agent,
)


class SecEdgarTests(unittest.TestCase):
    def _payload(self, ticker: str, cik: str) -> dict:
        return {
            "name": f"{ticker} Corp",
            "sic": "3674",
            "filings": {
                "recent": {
                    "form": ["8-K", "8-K", "10-Q"],
                    "filingDate": ["2022-10-03", "2024-10-03", "2024-11-03"],
                    "acceptanceDateTime": [
                        "2022-10-03T20:00:00.000Z",
                        "2024-10-03T20:00:00.000Z",
                        "2024-11-03T20:00:00.000Z",
                    ],
                    "accessionNumber": [
                        f"{cik[:4]}-22-000001",
                        f"{cik[:4]}-24-000002",
                        f"{cik[:4]}-24-000003",
                    ],
                    "reportDate": ["2022-10-03", "2024-10-03", "2024-11-03"],
                    "primaryDocument": ["first.htm", "second.htm", "third.htm"],
                    "primaryDocDescription": ["8-K", "8-K", "10-Q"],
                    "items": ["2.02", "5.02", "2.02"],
                }
            },
        }

    def test_placeholder_user_agent_is_rejected(self) -> None:
        with self.assertRaises(ContractError):
            validate_user_agent("Evidence-to-Alpha research@example.com")
        with self.assertRaises(ContractError):
            validate_user_agent("Evidence-to-Alpha without-email")
        validate_user_agent("Evidence-to-Alpha research@acme.co")

    def test_company_spec_zero_pads_cik(self) -> None:
        self.assertEqual(parse_company_spec("NVDA=1045810"), SecCompany("NVDA", "0001045810"))
        with self.assertRaises(ContractError):
            parse_company_spec("not-a-company")

    def test_export_is_point_in_time_and_reloadable(self) -> None:
        payloads = {
            "https://data.sec.gov/submissions/CIK0001045810.json": self._payload("NVDA", "0001045810"),
            "https://data.sec.gov/submissions/CIK0000002488.json": self._payload("AMD", "0000002488"),
        }

        def get_json(url: str, user_agent: str) -> dict:
            return payloads[url]

        def get_text(url: str, user_agent: str) -> str:
            return "<html><body>record revenue growth and strong results</body></html>"

        bundle = export_sec_edgar(
            [SecCompany("NVDA", "0001045810"), SecCompany("AMD", "0000002488")],
            user_agent="Evidence-to-Alpha research@acme.co",
            config=SecExportConfig(
                start_date=date(2022, 1, 1),
                end_date=date(2024, 12, 31),
                forms=("8-K",),
                max_events=4,
                request_delay_seconds=0,
            ),
            get_json=get_json,
            get_text=get_text,
        )
        self.assertEqual(len(bundle.events), 4)
        self.assertFalse(bundle.manifest["synthetic"])
        self.assertEqual(len(bundle.evidence), 4)
        self.assertEqual(len(bundle.mappings), 4)
        self.assertTrue(all(item.source_url.startswith("https://www.sec.gov/Archives/") for item in bundle.evidence.values()))
        self.assertTrue(all(item.observed_at >= item.published_at for item in bundle.events))
        self.assertTrue(all(item.ref in bundle.manifest["source_urls_by_event_version"] for item in bundle.events))
        with TemporaryDirectory() as temp:
            from evidence_alpha.news_adapter import write_news_export
            write_news_export(bundle, temp)
            reloaded = load_news_export(temp)
            self.assertEqual([item.to_dict() for item in reloaded.events], [item.to_dict() for item in bundle.events])
            self.assertEqual(reloaded.manifest["adapter"], "sec-edgar-official-disclosures-v1")


if __name__ == "__main__":
    unittest.main()
