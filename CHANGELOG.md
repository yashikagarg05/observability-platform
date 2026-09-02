# Changelog

All notable changes to this project will be documented in this file.

This project uses semantic versioning for platform releases. Component-specific release artifacts may use their own tags when documented in `docs/releases/compatibility.md`.

## Unreleased

### Added

- Root `.env.example` for fresh-clone local evaluation.
- Open-source contributor documentation and project templates.

### Changed

- README quick start now leads with the local evaluation workflow before the production-oriented path.

## v0.1.0

Initial public release scope:

- Docker Compose observability stack with Grafana, Prometheus, Loki, Tempo, node-exporter, and OpenTelemetry Collector Gateway.
- Node Agent profiles for OTLP, Docker logs, file logs, host metrics, and mTLS transport.
- Production-oriented single-tenant deployment overlay with local persistence, Gateway queues, health checks, backup/restore scripts, and acceptance tooling.
- Control Plane API and Platform Management Console for enrollment, registry, lifecycle, and fleet visibility workflows.
- Reference `orders-api` / `payment-api` application for validating logs, metrics, traces, and log-to-trace correlation.
- Production PKI templates and development certificate helpers.

Known limits:

- Single-host, single-tenant deployment profile.
- No high availability, Kubernetes deployment, multi-tenant isolation, bundled production CA, or remote agent upgrade system.
