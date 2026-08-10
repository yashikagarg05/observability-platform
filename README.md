# Observability Platform

Version 1.0 is an OTLP-only Gateway plus one deployable source-host component: the OpenTelemetry Node Agent.

- Gateway: `collector/gateway`
- Node Agent release source: `collector/agent`
- Operator onboarding: `docs/node-agent-onboarding.md`
- Compatibility and releases: `docs/releases/compatibility.md`

Use `make validate` before deployment and `make package-node-agent VERSION=1.0.0` to create the distributable archive.
