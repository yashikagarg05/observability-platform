# Node Agent onboarding

The Node Agent is installed from a release artifact on each application host. Application hosts should not clone the full Observability Platform repository.

1. Download `otel-node-agent-<version>.tgz` and `SHA256SUMS` from the matching GitHub Release; verify the checksum.
2. Extract it, then run `cp .env.example .env`.
3. Set `GATEWAY_OTLP_GRPC_ENDPOINT`, `AGENT_HOST_NAME`, namespace, and environment.
4. If using managed enrollment, run `bin/enroll-node-agent.sh enroll` before starting the agent.
5. Select one source profile without editing YAML:

```bash
# Local OTLP intake
docker compose -f compose.yaml -f config/compose/otlp.yaml up -d

# Docker stdout
docker compose -f compose.yaml -f config/compose/docker.yaml up -d

# Docker stdout plus one application file directory
# Also set APP_LOG_HOST_PATH, APP_LOG_GLOB, and OTEL_SERVICE_NAME in .env.
docker compose -f compose.yaml -f config/compose/docker-file.yaml up -d

# Local OTLP intake plus host metrics
docker compose -f compose.yaml -f config/compose/otlp-hostmetrics.yaml up -d

# Docker stdout plus host metrics
docker compose -f compose.yaml -f config/compose/docker-hostmetrics.yaml up -d

# Docker stdout, one application file directory, and host metrics
# Also set APP_LOG_HOST_PATH, APP_LOG_GLOB, and OTEL_SERVICE_NAME in .env.
docker compose -f compose.yaml -f config/compose/docker-file-hostmetrics.yaml up -d
```

6. Verify `docker compose ps`, then query Grafana Explore using `service_name` and `host_name` for logs/traces. For hostmetrics profiles, query Prometheus for metrics such as `system_cpu_time_seconds_total`, `system_memory_usage_bytes`, `system_filesystem_usage_bytes`, and `system_network_io_bytes_total`.

For a local process that only emits stdout/stderr and is not otherwise instrumented, wrap it with `bin/otel-run npm run dev` (or `python app.py`, `java -jar app.jar`). The Node Agent must expose OTLP HTTP on `localhost:4318`, so use the `otlp` or `otlp-hostmetrics` profile. Docker-only and file profiles do not publish that port.

For a complete remote application host walkthrough, see [Integrate Your Application](integrate-your-application.md).

## mTLS transport

Plaintext OTLP/gRPC remains the migration default. To enable mTLS after certificates are installed:

```bash
NODE_AGENT_TRANSPORT_SUFFIX=-mtls
NODE_AGENT_CERTS_HOST_PATH=/etc/otel-node-agent/certs
NODE_AGENT_SECRETS_HOST_PATH=/etc/otel-node-agent/secrets

docker compose \
  -f compose.yaml \
  -f config/compose/docker-hostmetrics.yaml \
  -f config/compose/mtls.yaml \
  up -d
```

Use `bin/enroll-node-agent.sh enroll` with a one-time enrollment credential to create the node private key locally, submit the CSR, and install the signed certificate and CA bundle.

## Upgrade and rollback

Keep `.env` and the `otel-node-agent-state` volume outside release archives. Validate the next release with the same Compose command, recreate the service, and retain the previous extracted release. Roll back by recreating the prior release with the same `.env` and state volume. Never run two Node Agent releases against the same source paths.
