# Readiness Input Examples

These files document the JSON shapes accepted by the readiness command.
They are illustrative contracts, not release evidence. Placeholder paths and
hashes cannot pass the runtime file-hash, provenance, freshness, or calendar
cross-checks.

`news_enrichment.example.json` is consumed upstream by `news-export
--enrichment` or `integrate --news-enrichment`. Readiness reloads the path and
SHA-256 recorded in the resulting news manifest. Example paths are rejected by
the production-input gate.

The CLI consumes each file separately:

    python -m evidence_alpha readiness
      --artifact-dir artifacts/integrated-real
      --factor-attestation examples/readiness/factor_attestation.example.json
      --price-attestation examples/readiness/price_attestation.example.json
      --pb-ingestion-manifest examples/readiness/pb_ingestion_manifest.example.json
      --pb-validation examples/readiness/pb_validation.example.json
      --pb-dry-run-manifest examples/readiness/pb_dry_run_manifest.example.json
      --pb-launch-bundle examples/readiness/pb_launch_bundle.example.json
      --paper-manifest examples/readiness/paper_manifest.example.json

Replace every example with evidence generated from the same integration as-of.
Passing readiness only permits an independent Live authorization review. It
does not grant broker or real-money authority.
