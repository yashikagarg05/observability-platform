# Single-Tenant Production Deployment MVP

This profile is for one company operating one tenant on a single host or VM. It is production-like enough for a controlled pilot, but it is not highly available and is not a multi-tenant SaaS deployment.

## Architecture

```text
Node Agent -> OTLP/mTLS -> Gateway -> Loki / Tempo / Prometheus -> Grafana
                                |
Platform UI -> Control Plane API -> Enrollment / Agent Registry
```

The Node Agent collects telemetry and forwards OTLP only. Grafana remains the logs, metrics, traces, dashboards, and exploration layer.

## Supported Scope

- Single tenant configured by `CONTROL_PLANE_TENANT_ID`.
- Single-node Docker Compose deployment.
- Local Docker volumes for telemetry and control-plane state.
- Gateway mTLS enabled with plaintext OTLP kept for migration rollback.
- Local backup and restore scripts for configuration and Docker volumes.

This profile is not HA. Do not use it as a shared multi-tenant SaaS platform.

For the shortest operator path, see `docs/production-quickstart.md`.

For repeatable validation, use `docs/production-acceptance-checklist.md`.

For production enrollment and certificate lifecycle controls, see `docs/production-enrollment-lifecycle.md`.

## Prerequisites

- Linux host with Docker and Docker Compose.
- Enough disk for Loki, Tempo, Prometheus, Grafana, Gateway queue, and control-plane state.
- Production Gateway certificate/key and Agent client CA bundle installed outside the repository.
- Enrollment signing material installed outside the repository.
- A configured production external issuer command, or explicit development issuer mode for isolated validation only.
- A long random `CONTROL_PLANE_OPERATOR_TOKEN` of at least 32 characters.

## Configuration

Copy and edit:

```bash
cp deployments/production/production.env.example /etc/observability-platform/production.env
```

Replace every `changeme` value and set:

- `CONTROL_PLANE_TENANT_ID`
- `CONTROL_PLANE_OPERATOR_TOKEN`
- `GRAFANA_ADMIN_PASSWORD`
- `GATEWAY_CERTS_HOST_PATH`
- `GATEWAY_SECRETS_HOST_PATH`
- `ENROLLMENT_PKI_HOST_PATH`
- `ENROLLMENT_ISSUER_MODE`
- `ENROLLMENT_PRODUCTION_ISSUER_COMMAND` when `ENROLLMENT_ISSUER_MODE=external`

Production PKI material must not come from `scripts/dev-mtls-certs.sh`.
The production profile defaults to external issuer mode. It fails safely if no external issuer command is configured.
The Control Plane rejects placeholder or short operator tokens at startup.

Management interfaces bind to `127.0.0.1` by default:

- `GRAFANA_BIND_ADDRESS`
- `PROMETHEUS_BIND_ADDRESS`
- `CONTROL_PLANE_BIND_ADDRESS`
- `PLATFORM_UI_BIND_ADDRESS`

Keep these loopback defaults for single-host operation. To expose the Platform UI, Control Plane, Grafana, or Prometheus remotely, put them behind an HTTPS reverse proxy or equivalent network control and set the relevant bind address intentionally.

## Install

```bash
set -a
. /etc/observability-platform/production.env
set +a

docker compose \
  -f docker-compose.yml \
  -f deployments/docker-compose/production.yaml \
  up -d
```

Open:

- Grafana: `http://localhost:${GRAFANA_PORT}`
- Platform UI: `http://localhost:${PLATFORM_UI_PORT}`
- Control Plane API: `http://localhost:${CONTROL_PLANE_PORT}`

Enter the operator token in the Platform UI. In production mode, tenant identity comes from `CONTROL_PLANE_TENANT_ID`, not from caller-supplied tenant headers.

Set `FRONTEND_CORS_ORIGIN` to the exact browser origin for the Platform UI. When operator-token authentication is enabled, the Control Plane does not fall back to wildcard CORS.

## Health Checks

- Gateway: `http://localhost:${GATEWAY_HEALTH_PORT:-13133}/` checks Collector health extension.
- Grafana: `/api/health`.
- Prometheus: `/-/healthy`.
- Loki: `/ready`.
- Tempo: `/ready`.
- Control Plane API: `/healthz`.

Grafana, Prometheus, and the Control Plane use Docker health checks against HTTP endpoints. Loki, Tempo, and the Gateway use distroless images without a shell or HTTP client, so their Docker health checks are process-level binary checks; monitor their application endpoints and scrape `up` status in Grafana for runtime health. Health checks do not prove end-to-end telemetry delivery.

## Storage And Retention

| Signal | Default Retention | Storage |
| --- | --- | --- |
| Logs | `168h` / 7 days | Loki local filesystem at `/loki` |
| Traces | `168h` / 7 days | Tempo local filesystem at `/var/tempo/traces` in the `tempo-data` volume |
| Metrics | `15d` and `20GB` | Prometheus local TSDB at `/prometheus` |

- Grafana: local Docker volume.
- Gateway queue: local Docker volume mounted at `/var/lib/otelcol`.
- Control plane: local JSON files in `control-plane-data`.

Trace retention is configured with `TRACE_RETENTION_HOURS`, default `168`. The pinned Tempo image is `v3.0.0`; retention is applied through the supported backend worker and backend scheduler compaction retention flags:

```text
-backend-worker.compaction.block-retention=${TRACE_RETENTION_HOURS}h
-backend-scheduler.provider.work.compaction.block-retention=${TRACE_RETENTION_HOURS}h
```

Retention is a time limit, not a hard disk-capacity guarantee. Local disk usage still depends on trace volume, span size, indexing overhead, and compaction timing. If storage fills, ingestion may fail, queues may stop accepting data, and data loss is possible. Monitor disk capacity and choose retention based on expected telemetry volume.

## Gateway Reliability

Production Gateway config uses:

- `memory_limiter`
- persistent file storage for Loki and Tempo exporter queues
- retry with `max_elapsed_time: 0s`
- health check extension

Recoverable:

- Temporary Loki outage for queued logs while queue disk remains available.
- Temporary Tempo outage for queued traces while queue disk remains available.

Not fully recoverable:

- Metrics exposed through the Prometheus pull exporter are in-memory and are not durably queued for Prometheus outages.
- Gateway process crash can lose in-flight telemetry not yet persisted.
- Disk-full queue state can still cause data loss.

## Self-Monitoring

Grafana dashboard:

```text
Platform Self-Monitoring
```

It shows scrape health, Gateway accepted/exported telemetry, export failures, queue size, CPU, and memory where metrics are available.

## Agent Enrollment

Create credentials through the Platform UI or API with:

```bash
curl -sS \
  -H "Authorization: Bearer $CONTROL_PLANE_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  "http://localhost:${CONTROL_PLANE_PORT}/v1/enrollment/credentials?tenant_id=${CONTROL_PLANE_TENANT_ID}" \
  -d '{"site_id":"site-1","environment":"production","capabilities":["otlp","hostmetrics"]}'
```

Run the returned enrollment command on the node. Private keys remain local to the node.

## Backup

Configuration backup and telemetry data backup are different.

Run:

```bash
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-observability-platform} \
./scripts/backup-platform.sh backups
```

This snapshots repository configuration and local Docker volumes. For high-write production data, stop or quiesce the platform first for a more consistent backup.
Trace data in the `tempo-data` volume is included. Backup size grows with retained trace volume.

## Restore

Stop the platform, then restore:

```bash
docker compose -f docker-compose.yml -f deployments/docker-compose/production.yaml down
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-observability-platform} \
./scripts/restore-platform.sh --force backups/platform-<timestamp>
docker compose -f docker-compose.yml -f deployments/docker-compose/production.yaml up -d
```

Restore replaces local Docker volume contents. Test restore procedures before relying on them.
Restored Tempo starts with the retention configuration from the restored repository/configuration. Traces older than the configured retention should not be expected to remain available after Tempo performs retention work.

## Upgrade

1. Back up configuration and volumes.
2. Validate Compose rendering.
3. Validate Collector production config.
4. Pull/build updated images.
5. Recreate services.
6. Verify health checks.
7. Verify logs, metrics, traces, enrollment, and Grafana dashboards.

Rollback by restoring the previous repository version/configuration and recreating services. If data schema changes occur in future versions, follow release-specific rollback notes.

## Known Limitations

- Single-node only.
- No backend HA or replication.
- No true multi-tenant telemetry isolation.
- JSON registry is supported only for small single-tenant pilots and requires file backup.
- Certificate renewal is supported through one-time renewal credentials, but production CA signing remains external.
- Disable/deny is enforced in the control plane; Gateway-side dynamic revocation still requires future authorization work or CA trust removal.
- No Kubernetes deployment.
- No package signing or OS packages yet.

## Cleanup

For a temporary validation deployment, stop only the intended Compose project:

```bash
COMPOSE_PROJECT_NAME=<project> docker compose \
  -f docker-compose.yml \
  -f deployments/docker-compose/production.yaml \
  down
```

Remove that project's volumes only after confirming the project name:

```bash
docker volume ls --format '{{.Name}}' | grep '^<project>_'
```

Then remove the matching validation volumes. Do not remove shared production or development volumes.

## Acceptance Check

Use the non-destructive acceptance script after startup:

```bash
CONTROL_PLANE_OPERATOR_TOKEN=$CONTROL_PLANE_OPERATOR_TOKEN \
CONTROL_PLANE_TENANT_ID=$CONTROL_PLANE_TENANT_ID \
GRAFANA_URL=http://localhost:${GRAFANA_PORT} \
PROMETHEUS_URL=http://localhost:${PROMETHEUS_PORT} \
CONTROL_PLANE_URL=http://localhost:${CONTROL_PLANE_PORT} \
python3 scripts/acceptance-check.py
```

The script verifies platform health, operator-token enforcement, Gateway self-metrics, and Grafana dashboard provisioning. It does not generate telemetry or modify state.
