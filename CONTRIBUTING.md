# Contributing

Thank you for improving Observability Platform. This project is a self-hosted telemetry stack built around Docker Compose, OpenTelemetry Collector, Grafana, Prometheus, Loki, Tempo, a Python control plane, and a React/Vite management UI.

## Getting Started

Prerequisites:

- Linux host or VM.
- Docker Engine with the Docker Compose v2 plugin.
- OpenSSL for development mTLS certificate generation.
- Node.js and npm for frontend work.
- Python 3.12 or compatible Python 3 for scripts and control-plane development.

Fork the repository on GitHub, then clone your fork:

```bash
git clone git@github.com:<your-user>/observability-platform.git
cd observability-platform

git switch -c feature/<short-description>
cp .env.example .env

make help
make demo-up
make demo-traffic
make validate
make test
```

For the local evaluation stack, follow the [application observability guide](docs/application-observability.md).

## Branch Naming

Use short, descriptive branch names:

- `feature/<name>`
- `fix/<name>`
- `docs/<name>`
- `refactor/<name>`

## Commit Conventions

Use clear, imperative commit subjects. Prefer prefixes that describe intent:

- `feat: add ...`
- `fix: correct ...`
- `docs: update ...`
- `test: cover ...`
- `chore: maintain ...`

Keep commits focused. Do not include generated secrets, local `.env` files, runtime state, build outputs, Docker volumes, private keys, or generated certificates.

## Useful Commands

Show available commands:

```bash
make help
```

Start the local evaluation stack and generate demo telemetry:

```bash
make demo-up
make demo-traffic
```

Validate base Compose and Gateway Collector configuration:

```bash
make validate
```

Validate mTLS certificates and generated Node Agent Collector profiles:

```bash
make validate-mtls
```

Run Python unit tests:

```bash
make test
```

Run Python syntax validation:

```bash
make lint
```

Build the management UI:

```bash
make frontend-build
```

Run non-destructive acceptance checks against a running stack:

```bash
make acceptance
```

Package and verify a Node Agent release:

```bash
make package-node-agent VERSION=<version>
make verify-node-agent-release VERSION=<version>
```

## Coding Standards

- Prefer small, reviewable changes over broad rewrites.
- Keep runtime behavior, deployment behavior, and public configuration contracts documented when they change.
- Use existing OpenTelemetry Collector, Docker Compose, Python, and React/Vite patterns already present in the repository.
- Keep generated files, credentials, private keys, local state, and build artifacts out of commits.
- Prefer relative Markdown links in repository documentation.

## Testing Requirements

Run validation based on the files you changed:

| Change area | Expected validation |
| --- | --- |
| Gateway, Compose, or Collector config | `make validate` |
| mTLS, PKI, or Node Agent generated profiles | `make validate-mtls` |
| Control Plane, scripts, or Python helpers | `make lint` and `make test` |
| Frontend | `make frontend-build` |
| Production deployment behavior | Relevant docs plus `make validate`; run `make acceptance` against a running stack when practical |
| Documentation only | Check links and commands touched by the change |

Mention any validation that could not be run in the pull request.

## Pull Requests

- Keep PRs focused and reviewable.
- Explain what changed and why.
- Include documentation updates when commands, environment variables, ports, dashboards, or deployment behavior change.
- Run the relevant validation commands before opening a PR.
- Mention any tests or validation that could not be run.
- Call out breaking changes, migration steps, and operational impact.

## Issue Reporting

Use the repository issue templates for bugs, features, and documentation issues. For security vulnerabilities, do not open a public issue; follow [SECURITY.md](SECURITY.md).

## Documentation

Operator-facing docs live in `docs/`. Component-specific notes live next to the component, such as `collector/agent/README.md`, `grafana/README.md`, and `pki/README.md`.

Prefer relative Markdown links so docs are clickable on GitHub.
