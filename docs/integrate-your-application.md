# Integrate Your Application

This guide is for users who already have one or more applications and want to send telemetry to Observability Platform without cloning this repository onto every application server.

## Deployment Model

Run the full platform once on a central host:

```text
Gateway -> Loki / Prometheus / Tempo -> Grafana
Control Plane API and Platform UI are optional for managed enrollment.
```

Run a lightweight Node Agent package on each application host:

```text
Application host:
app-1, app-2, worker -> localhost:4318 -> Node Agent -> central Gateway
```

Applications send OpenTelemetry to their local Node Agent. They do not need to know about Loki, Tempo, Prometheus, or Grafana.

## 1. Start The Platform

For local evaluation:

```bash
make demo-up
make demo-management-up
```

For production-style deployment, follow [Production quickstart](production-quickstart.md).

## 2. Create An Enrollment Credential

Use the Platform UI or Control Plane API to create a one-time credential for the application host:

```bash
curl -sS \
  -H "Authorization: Bearer $CONTROL_PLANE_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  "https://platform.example.com/v1/enrollment/credentials?tenant_id=tenant-a" \
  -d '{"site_id":"site-1","environment":"production","capabilities":["otlp","hostmetrics"]}'
```

Save the returned `enrollment_credential`. It is only shown once.

## 3. Install The Node Agent Package On The Application Host

Do not clone the full repository onto every application host. Download the Node Agent release artifact instead:

```bash
curl -LO https://github.com/yashikagarg05/observability-platform/releases/download/v0.1.0/otel-node-agent-v0.1.0.tgz
curl -LO https://github.com/yashikagarg05/observability-platform/releases/download/v0.1.0/SHA256SUMS
sha256sum --check SHA256SUMS

tar -xzf otel-node-agent-v0.1.0.tgz
cd otel-node-agent-v0.1.0
cp .env.example .env
```

For unreleased local validation, a maintainer can build the artifact from the repository:

```bash
make package-node-agent VERSION=v0.1.0
```

## 4. Enroll The Node Agent

Run enrollment on the application host:

```bash
NODE_AGENT_SECRET_DIR=/etc/otel-node-agent/secrets \
NODE_AGENT_CERT_DIR=/etc/otel-node-agent/certs \
NODE_AGENT_ENROLLMENT_ENDPOINT=https://platform.example.com \
NODE_AGENT_ENROLLMENT_CREDENTIAL=<credential> \
bin/enroll-node-agent.sh enroll
```

The private key stays on the application host. The Control Plane receives only a CSR and returns the signed certificate plus CA bundle.

## 5. Start The Node Agent

For application OTLP plus host metrics:

```bash
NODE_AGENT_CERTS_HOST_PATH=/etc/otel-node-agent/certs \
NODE_AGENT_SECRETS_HOST_PATH=/etc/otel-node-agent/secrets \
NODE_AGENT_TRANSPORT_SUFFIX=-mtls \
docker compose \
  -f compose.yaml \
  -f config/compose/otlp-hostmetrics.yaml \
  -f config/compose/mtls.yaml \
  up -d
```

For Docker stdout collection, use `config/compose/docker.yaml` or `config/compose/docker-hostmetrics.yaml` instead.

## 6. Configure One Or More Applications

On the same application host, point every application at the local Node Agent:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_SERVICE_NAMESPACE=my-team
OTEL_DEPLOYMENT_ENVIRONMENT=production
```

Use a different service name per application:

```bash
# orders-api
OTEL_SERVICE_NAME=orders-api

# payments-api
OTEL_SERVICE_NAME=payments-api

# worker
OTEL_SERVICE_NAME=worker
```

All three applications can use the same local Node Agent endpoint:

```text
orders-api   -> localhost:4318
payments-api -> localhost:4318
worker       -> localhost:4318
```

## 7. Verify In Grafana

Logs:

```logql
{service_namespace="my-team"}
```

Metrics:

```promql
{service_namespace="my-team"}
```

Traces:

Search Tempo for `orders-api`, `payments-api`, or the service name you configured.

## When To Use Management

Use the management path when you want controlled agent onboarding and fleet visibility:

- one-time enrollment credentials
- local private key generation
- certificate issuance and expiry tracking
- heartbeat status
- disable state
- agent registry by tenant, site, and environment

For the full lifecycle, see [Agent Management Lifecycle](agent-management-lifecycle.md).
