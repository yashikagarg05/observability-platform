# Production Acceptance Checklist

Use this checklist for a clean single-tenant production-style deployment validation. It is intentionally focused on operator-visible outcomes.

## Platform Startup

- [ ] Platform starts with a unique `COMPOSE_PROJECT_NAME`.
- [ ] Gateway container is running and healthy.
- [ ] Loki container is running and healthy.
- [ ] Tempo container is running and healthy.
- [ ] Prometheus container is running and healthy.
- [ ] Grafana container is running and healthy.
- [ ] Control Plane API `/healthz` returns success.
- [ ] Platform UI starts.

## Authentication

- [ ] Unauthenticated management API request is rejected.
- [ ] Invalid operator token is rejected.
- [ ] Valid operator token is accepted.
- [ ] Tenant context comes from `CONTROL_PLANE_TENANT_ID`.

## Agent Enrollment

- [ ] Enrollment credential can be created by an authenticated operator.
- [ ] Fresh Node Agent enrollment generates a local private key.
- [ ] Private key is not sent to the Control Plane API.
- [ ] Client certificate is issued with expected URI SAN.
- [ ] Client certificate chain validates against the Gateway trusted Agent CA bundle.
- [ ] Agent Registry shows certificate serial, fingerprint, issuer, issue time, expiry time, and certificate status.
- [ ] Private key permissions are `0600`.
- [ ] Agent appears in `GET /v1/node-agents`.
- [ ] Heartbeat updates `last_seen_at`.
- [ ] Agent becomes `healthy`.
- [ ] Reusing the enrollment credential fails.
- [ ] Invalid enrollment credential fails.
- [ ] Renewal credential can be created for the Agent.
- [ ] Renewal installs a replacement only after validation.
- [ ] Previous working certificate/key are preserved with `.previous` suffixes.
- [ ] Disabled Agent cannot heartbeat.
- [ ] Disabled Agent cannot renew.

## Telemetry

- [ ] Application logs from `orders-api` reach Loki.
- [ ] Application metrics reach Prometheus.
- [ ] Application traces reach Tempo.
- [ ] Intentional application error is visible in logs and traces.
- [ ] Logs contain trace/span correlation metadata.
- [ ] Distributed trace contains `orders-api` and `payment-api`.
- [ ] Host CPU metrics reach Prometheus.
- [ ] Host memory metrics reach Prometheus.
- [ ] Host filesystem metrics reach Prometheus.
- [ ] Host network metrics reach Prometheus.
- [ ] Grafana datasources are provisioned.
- [ ] Grafana dashboards load.

## Source Ownership

- [ ] Node Agent owns local Docker/file/host/OTLP source collection.
- [ ] Gateway owns OTLP processing and backend export.
- [ ] Gateway Docker/file receivers are not enabled.
- [ ] No second production Docker/file reader is started.

## Recovery

- [ ] Gateway restart recovers.
- [ ] Loki restart recovers.
- [ ] Tempo restart recovers.
- [ ] Prometheus restart recovers.
- [ ] Grafana restart recovers.
- [ ] Control Plane restart recovers.
- [ ] Node Agent restart recovers.
- [ ] Temporary Loki outage queues log export.
- [ ] Loki queue drains after recovery.

## Backup And Restore

- [ ] `scripts/backup-platform.sh` completes for the intended project.
- [ ] Backup includes configuration.
- [ ] Backup includes Docker volume archives.
- [ ] `scripts/restore-platform.sh --force` restores into an isolated project.
- [ ] Restored Control Plane starts.
- [ ] Restored Agent Registry contains the enrolled Agent.
- [ ] Restored Grafana starts with dashboards and datasources.
- [ ] Restored Loki data is queryable where supported.
- [ ] Restored Tempo data is queryable where supported.
- [ ] Restored Prometheus data is queryable where supported.

## Cleanup

- [ ] Validation app project is stopped.
- [ ] Validation platform project is stopped.
- [ ] Restore validation project is stopped.
- [ ] Only validation project volumes are removed.
- [ ] `releases/` remains unchanged.
