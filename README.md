# Observability Platform

An OpenTelemetry-native, self-hosted observability platform for teams that want centralized logs, metrics, and traces without sending telemetry to a proprietary SaaS.

This repository provides a single-tenant Docker Compose deployment with:

- Node Agent for local telemetry collection.
- OTLP Gateway for centralized processing and routing.
- Loki for logs.
- Tempo for traces.
- Prometheus for metrics.
- Grafana as the primary observability UI.
- Control Plane APIs for Node Agent enrollment, registry, and fleet status.

Telemetry stays in the operator's infrastructure unless the operator configures external storage or forwarding outside this repository.

## Architecture

```text
Applications / Infrastructure
        -> Node Agent
        -> OTLP / mTLS
        -> Gateway
        -> Loki / Tempo / Prometheus
        -> Grafana
```

Control plane:

```text
Operator
        -> Control Plane API
        -> Enrollment / Agent Registry
        -> Node Agent fleet status
```

## Supported Today

- Docker stdout logs.
- File logs.
- Host metrics.
- Application OTLP logs, metrics, and traces.
- Distributed trace reference application.
- Node Agent mTLS enrollment.
- Agent registry, heartbeat, and status.
- Single-tenant operator-token authentication.
- Persistent Gateway queues.
- Local retention defaults for logs, traces, and metrics.
- Backup and restore scripts for the single-node profile.

## Deployment

Start with:

- Production quickstart: `docs/production-quickstart.md`
- Production deployment runbook: `docs/production-deployment.md`
- Node Agent onboarding: `docs/node-agent-onboarding.md`

Grafana is included in the Compose deployment and remains the primary UI for logs, metrics, traces, dashboards, and exploration.

## Limitations

The first public release is intentionally scoped:

- Single-node Docker Compose deployment.
- Single tenant.
- Local persistent storage.
- No high availability.
- No Kubernetes deployment yet.
- No managed multi-tenant SaaS mode.
- Production CA implementation is external/customer-managed.
- Certificate lifecycle controls exist, but full Gateway-side dynamic revocation is future work.

## Roadmap

Planned future work includes Kubernetes deployment, HA storage options, deeper production CA integrations, stronger Gateway-side authorization, and broader packaging.

## Repository Map

- Gateway: `collector/gateway`
- Node Agent release source: `collector/agent`
- Operator onboarding: `docs/node-agent-onboarding.md`
- Application observability reference: `docs/application-observability.md`
- Production quickstart: `docs/production-quickstart.md`
- Single-tenant production deployment: `docs/production-deployment.md`
- Compatibility and releases: `docs/releases/compatibility.md`

The single-tenant production profile sets explicit local retention defaults for logs, traces, and metrics; see `docs/production-deployment.md`.

Use `make validate` before deployment and `make package-node-agent VERSION=1.0.0` to create the distributable archive.
