# Production Quickstart

This is the shortest supported path for a single-tenant production-style deployment. For details and limitations, see `docs/production-deployment.md`.

## 1. Prerequisites

- Linux host with Docker and Docker Compose.
- Checked-out repository.
- Production PKI material prepared outside the repository.
- One long random operator token of at least 32 characters.

For isolated validation only, `scripts/dev-mtls-certs.sh` may generate throwaway certificates. Do not use those certificates for production.

## 2. Configure Environment

```bash
cp deployments/production/production.env.example /etc/observability-platform/production.env
```

Edit the file and set at minimum:

```text
CONTROL_PLANE_TENANT_ID
CONTROL_PLANE_OPERATOR_TOKEN
GRAFANA_ADMIN_PASSWORD
GATEWAY_CERTS_HOST_PATH
GATEWAY_SECRETS_HOST_PATH
ENROLLMENT_PKI_HOST_PATH
ENROLLMENT_ISSUER_MODE
ENROLLMENT_PRODUCTION_ISSUER_COMMAND
TRACE_RETENTION_HOURS
```

For production, use `ENROLLMENT_ISSUER_MODE=external` and configure the command that integrates with the customer-managed CA. The platform fails closed if the external issuer command is missing. For isolated validation only, use `ENROLLMENT_ISSUER_MODE=development` with `ENROLLMENT_ALLOW_DEVELOPMENT_ISSUER=true` and throwaway certificates.

The default production profile retains traces for `168` hours. Change `TRACE_RETENTION_HOURS` to adjust Tempo trace retention. This is a time-based retention limit on local filesystem storage, not a hard disk-capacity guarantee.

Management interfaces bind to `127.0.0.1` by default. Keep that default for single-host use, or expose them only through an HTTPS reverse proxy or equivalent network control.

## 3. Start Platform

```bash
set -a
. /etc/observability-platform/production.env
set +a

docker compose \
  -f docker-compose.yml \
  -f deployments/docker-compose/production.yaml \
  up -d
```

## 4. Verify Health

```bash
docker compose -f docker-compose.yml -f deployments/docker-compose/production.yaml ps
```

Check:

- Grafana: `http://localhost:${GRAFANA_PORT}/api/health`
- Prometheus: `http://localhost:${PROMETHEUS_PORT}/-/healthy`
- Control Plane: `http://localhost:${CONTROL_PLANE_PORT}/healthz`
- Gateway: `http://localhost:${GATEWAY_HEALTH_PORT:-13133}/`

## 5. Create Enrollment Credential

```bash
curl -sS \
  -H "Authorization: Bearer $CONTROL_PLANE_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  "http://localhost:${CONTROL_PLANE_PORT}/v1/enrollment/credentials?tenant_id=${CONTROL_PLANE_TENANT_ID}" \
  -d '{"site_id":"site-1","environment":"production","capabilities":["otlp","hostmetrics"]}'
```

Save the returned `enrollment_credential`. It is displayed only when created and fails after successful use.

## 6. Enroll Node Agent

On the application host, download and extract the `otel-node-agent-<version>.tgz` artifact from the matching GitHub Release. Run enrollment from inside the extracted directory:

```bash
NODE_AGENT_SECRET_DIR=/etc/otel-node-agent/secrets \
NODE_AGENT_CERT_DIR=/etc/otel-node-agent/certs \
NODE_AGENT_ENROLLMENT_ENDPOINT=http://localhost:${CONTROL_PLANE_PORT} \
NODE_AGENT_ENROLLMENT_CREDENTIAL=<credential> \
bin/enroll-node-agent.sh enroll
```

Then send a heartbeat:

```bash
NODE_AGENT_SECRET_DIR=/etc/otel-node-agent/secrets \
NODE_AGENT_CERT_DIR=/etc/otel-node-agent/certs \
NODE_AGENT_ENROLLMENT_ENDPOINT=http://localhost:${CONTROL_PLANE_PORT} \
AGENT_HOST_NAME=$(hostname) \
NODE_AGENT_VERSION=1.1.0 \
NODE_AGENT_CAPABILITIES=otlp,hostmetrics \
bin/enroll-node-agent.sh heartbeat
```

## 7. Verify Agent

```bash
curl -sS \
  -H "Authorization: Bearer $CONTROL_PLANE_OPERATOR_TOKEN" \
  "http://localhost:${CONTROL_PLANE_PORT}/v1/node-agents?tenant_id=${CONTROL_PLANE_TENANT_ID}"
```

## 8. Run Reference Application

```bash
OBSERVABILITY_NETWORK=${COMPOSE_PROJECT_NAME:-observability-platform}_observability \
NODE_AGENT_CERTS_HOST_PATH=/etc/otel-node-agent/certs \
NODE_AGENT_SECRETS_HOST_PATH=/etc/otel-node-agent/secrets \
docker compose -f examples/app-observability/docker-compose.yaml up -d --build
```

Generate traffic:

```bash
OBSERVABILITY_NETWORK=${COMPOSE_PROJECT_NAME:-observability-platform}_observability \
NODE_AGENT_CERTS_HOST_PATH=/etc/otel-node-agent/certs \
NODE_AGENT_SECRETS_HOST_PATH=/etc/otel-node-agent/secrets \
docker compose -f examples/app-observability/docker-compose.yaml exec -T \
  -e ORDERS_API_URL=http://localhost:8080 \
  orders-api npm run traffic
```

## 9. Open Grafana

Open `http://localhost:${GRAFANA_PORT}` and check:

- `Application Observability Reference`
- `Platform Self-Monitoring`

Verify logs in Loki, metrics in Prometheus, traces in Tempo, and log-to-trace correlation.

## Isolated Validation Notes

To run this quickstart beside another deployment, set a unique `COMPOSE_PROJECT_NAME` and non-default host ports in the environment file, including `GATEWAY_HEALTH_PORT`. The reference application can join that isolated network with:

```bash
OBSERVABILITY_NETWORK=${COMPOSE_PROJECT_NAME}_observability
ORDERS_API_HOST_PORT=<unused-port>
```
