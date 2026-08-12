# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please do not open a
public GitHub issue.

Please report the vulnerability privately through GitHub Security Advisories or
GitHub's private vulnerability reporting flow for this repository. If private
reporting is unavailable, contact the repository maintainer privately through
the maintainer profile listed on GitHub.

When reporting a vulnerability, please include:

- A description of the vulnerability
- The affected component or version
- Steps to reproduce the issue
- The potential security impact
- Any suggested mitigation, if available

Please avoid including credentials, private keys, personal data, or other
sensitive information in the report unless it is necessary to demonstrate the
issue.

## Supported Versions

| Version | Supported |
| --- | --- |
| `v0.1.x` | Yes |
| `< v0.1.0` | No |

Security fixes target the latest supported release line and `main` when the fix
also applies to unreleased development work.

The initial response target for vulnerability reports is 7 days. Resolution
timelines depend on severity, exploitability, and release complexity.

## Responsible Disclosure

Please allow reasonable time for the issue to be investigated and addressed
before publicly disclosing the vulnerability.

## Security Considerations

Observability Platform handles telemetry, credentials, certificates, and operator
access to infrastructure-facing services. Treat the following as sensitive:

- `CONTROL_PLANE_OPERATOR_TOKEN`, Grafana administrator credentials, enrollment
  credentials, renewal credentials, and any copied `.env` files.
- Gateway and Agent private keys, CA material, certificate bundles, and
  production issuer integration files.
- Telemetry payloads that may contain customer data, secrets, access tokens,
  headers, database queries, stack traces, or personally identifiable
  information.
- Backups created by `scripts/backup-platform.sh`, because they may include
  Grafana state, telemetry data, and Control Plane state.

Do not commit production secrets, private keys, generated certificates, local
environment files, Docker volumes, runtime state, or backups.

## Deployment Guidance

- Expose only the ports required for the deployment. Avoid exposing Grafana,
  Control Plane, OTLP, Prometheus, Loki, or Tempo endpoints directly to the
  public internet unless an appropriate network and authentication boundary is
  in place.
- Use a long random `CONTROL_PLANE_OPERATOR_TOKEN` for production-oriented
  deployments and rotate it if it is disclosed.
- Replace default Grafana credentials before using a shared host.
- Keep production PKI material outside the repository and outside generated
  release archives.
- Use `ENROLLMENT_ISSUER_MODE=external` for production-oriented enrollment. The
  development issuer mode is only for isolated validation.
- Review telemetry sources before onboarding applications. Logs and traces can
  contain sensitive application data unless instrumentation and log redaction
  policies are applied upstream.
