# Contributing

Thank you for improving Observability Platform. This project is a self-hosted telemetry stack built around Docker Compose, OpenTelemetry Collector, Grafana, Prometheus, Loki, Tempo, a Python control plane, and a React/Vite management UI.

## Development Setup

Prerequisites:

- Linux host or VM.
- Docker Engine with the Docker Compose v2 plugin.
- OpenSSL for development mTLS certificate generation.
- Node.js and npm for frontend work.
- Python 3 for scripts and control-plane development.

Start from a clean branch:

```bash
git switch -c <type>/<short-description>
cp .env.example .env
```

For the local evaluation stack, follow the [application observability guide](docs/application-observability.md).

## Useful Commands

Validate the base Compose and Gateway Collector configuration:

```bash
make validate
```

Validate mTLS certificates and generated Node Agent Collector profiles:

```bash
make validate-mtls
```

Build the management UI:

```bash
npm --prefix frontend ci
npm --prefix frontend run build
```

Package and verify a Node Agent release:

```bash
make package-node-agent VERSION=<version>
make verify-node-agent-release VERSION=<version>
```

## Pull Requests

- Keep PRs focused and reviewable.
- Include documentation updates when commands, environment variables, ports, dashboards, or deployment behavior change.
- Do not commit generated secrets, private keys, local `.env` files, Docker volumes, or runtime state.
- Run the relevant validation commands before opening a PR.
- Mention any tests or validation that could not be run.

## Documentation

Operator-facing docs live in `docs/`. Component-specific notes live next to the component, such as `collector/agent/README.md`, `grafana/README.md`, and `pki/README.md`.

Prefer relative Markdown links so docs are clickable on GitHub.
