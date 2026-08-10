# Component compatibility

| Component | Release tag | Compatibility contract |
| --- | --- | --- |
| Node Agent | `node-agent/vX.Y.Z` | OTLP/gRPC to Gateway, profile and `.env` contract |
| Gateway | `gateway/vX.Y.Z` | OTLP ingest, canonical log model, backend exporters |
| Grafana observability | `grafana-observability/vX.Y.Z` | Stable datasource UIDs: `loki`, `tempo`, `prometheus` |
| Documentation | `docs/vX.Y.Z` | Installation and migration procedures |

A `platform/vX.Y.Z` annotated tag records the tested component versions. Changes to telemetry schema, datasource UIDs, profiles, or environment keys require an explicit compatibility review.

## Release artifact retention

Preserved Node Agent releases live at `releases/<version>/`:

```text
releases/<version>/
  otel-node-agent-<version>.tgz
  SHA256SUMS
  manifest.json
  sbom.json
```

`dist/` is disposable staging only. Create a release with `./scripts/package-node-agent.sh <version>` and verify it with `./scripts/verify-node-agent-release.sh <version>`. The build fails when the requested version already exists; use `--force` only for an explicitly authorized replacement.
