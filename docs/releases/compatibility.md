# Release compatibility

The current public release line uses a single platform tag, such as `v0.1.0`, for the tested repository state.

Component-specific tags are reserved for future releases when components are shipped independently.

| Component | Release tag | Compatibility contract |
| --- | --- | --- |
| Platform | `vX.Y.Z` | Tested repository state for the Compose stack, Gateway, Node Agent, dashboards, Control Plane, UI, and docs |
| Node Agent | future `node-agent/vX.Y.Z` | OTLP/gRPC to Gateway, profile and `.env` contract |
| Gateway | future `gateway/vX.Y.Z` | OTLP ingest, canonical log model, backend exporters |
| Grafana observability | future `grafana-observability/vX.Y.Z` | Stable datasource UIDs: `loki`, `tempo`, `prometheus` |
| Documentation | future `docs/vX.Y.Z` | Installation and migration procedures |

Changes to telemetry schema, datasource UIDs, profiles, or environment keys require an explicit compatibility review.

## Release artifact retention

Node Agent release artifacts are generated locally during release preparation and should be attached to the corresponding GitHub Release unless a future release explicitly commits `releases/<version>/` artifacts to the repository.

```text
otel-node-agent-<version>.tgz
SHA256SUMS
manifest.json
sbom.json
```

`dist/` is disposable staging only. Create a release with `./scripts/package-node-agent.sh <version>` and verify it with `./scripts/verify-node-agent-release.sh <version>`. The build fails when the requested version already exists; use `--force` only for an explicitly authorized replacement.

See [release process](release-process.md) for the maintainer checklist.
