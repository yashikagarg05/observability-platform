# Node Agent onboarding

1. Download `otel-node-agent-<version>.tgz` and its `.sha256` file; verify the checksum.
2. Extract it, then run `cp .env.example .env`.
3. Set `GATEWAY_OTLP_GRPC_ENDPOINT`, `AGENT_HOST_NAME`, namespace, and environment.
4. Select one source profile without editing YAML:

```bash
# Local OTLP intake
docker compose -f compose.yaml -f config/compose/otlp.yaml up -d

# Docker stdout
docker compose -f compose.yaml -f config/compose/docker.yaml up -d

# Docker stdout plus one application file directory
# Also set APP_LOG_HOST_PATH, APP_LOG_GLOB, and OTEL_SERVICE_NAME in .env.
docker compose -f compose.yaml -f config/compose/docker-file.yaml up -d
```

5. Verify `docker compose ps`, then query Grafana Explore using `service_name` and `host_name`.

## Upgrade and rollback

Keep `.env` and the `otel-node-agent-state` volume outside release archives. Validate the next release with the same Compose command, recreate the service, and retain the previous extracted release. Roll back by recreating the prior release with the same `.env` and state volume. Never run two Node Agent releases against the same source paths.
