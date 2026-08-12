# Application Observability Reference

This reference demonstrates application logs, metrics, and traces flowing through the platform without sending telemetry to a proprietary SaaS.

```text
orders-api -> OpenTelemetry OTLP -> Node Agent -> Gateway -> Loki / Tempo / Prometheus -> Grafana
              |
              +-> payment-api for distributed trace validation
```

Grafana remains the visualization and exploration layer. The platform UI manages fleet, enrollment, and control-plane workflows.

## Reference Applications

`examples/app-observability` contains one instrumented Node.js application that can run as two services:

- `orders-api`
- `payment-api`

Endpoints:

- `GET /`
- `GET /health`
- `GET /api/orders`
- `GET /api/payments`
- `GET /api/error`

`orders-api` calls `payment-api` from `/api/orders`, creating a distributed trace across both services.

## Service Identity

The demo uses OpenTelemetry resource attributes:

```text
service.name=orders-api or payment-api
service.namespace=demo
deployment.environment=development
service.version=1.0.0
```

These follow the platform resource identity model. Do not create a separate application identity model.

## Telemetry

Application telemetry:

- Logs: structured OTLP logs with severity, service identity, and trace/span correlation attributes.
- Metrics: request count, request duration, error count, and demo business counters.
- Traces: HTTP server spans, outgoing HTTP spans, manual application spans, and error spans.

Host telemetry:

- Collected separately by the Node Agent `hostmetrics` capability.
- Used to understand node CPU, memory, disk/filesystem, and network.

## Run The Demo

Create the local Compose environment file:

```bash
cp .env.example .env
```

Create development mTLS certificates for the demo:

```bash
GATEWAY_DNS=otel-collector \
NODE_AGENT_AGENT_ID=app-observability-agent \
NODE_AGENT_TENANT_ID=demo-tenant \
NODE_AGENT_SITE_ID=demo-site \
NODE_AGENT_ENVIRONMENT=development \
./scripts/dev-mtls-certs.sh .tmp/app-observability-mtls
```

Start the platform with the Gateway mTLS listener:

```bash
GATEWAY_CERTS_HOST_PATH=$PWD/.tmp/app-observability-mtls/gateway/certs \
GATEWAY_SECRETS_HOST_PATH=$PWD/.tmp/app-observability-mtls/gateway/secrets \
docker compose -f docker-compose.yml -f deployments/docker-compose/gateway-mtls.yaml up -d
```

Start the reference applications and demo Node Agent:

```bash
NODE_AGENT_CERTS_HOST_PATH=$PWD/.tmp/app-observability-mtls/agent/certs \
NODE_AGENT_SECRETS_HOST_PATH=$PWD/.tmp/app-observability-mtls/agent/secrets \
docker compose -f examples/app-observability/docker-compose.yaml up -d --build
```

Generate deterministic traffic:

```bash
docker compose -f examples/app-observability/docker-compose.yaml exec orders-api npm run traffic
```

Open Grafana:

```text
http://localhost:3000
```

Default local credentials from `.env.example`:

```text
admin / admin
```

Dashboard:

```text
Application Observability Reference
```

## Verification

Logs in Loki:

```logql
{service_namespace="demo"}
```

Application metrics in Prometheus:

```promql
demo_http_requests_total{service_namespace="demo"}
demo_http_errors_total{service_namespace="demo"}
demo_http_request_duration_ms_milliseconds_bucket{service_namespace="demo"}
demo_orders_created_total{service_name="orders-api"}
demo_payments_processed_total{service_name="payment-api"}
```

Traces in Tempo:

- Open Grafana Explore.
- Select Tempo.
- Search recent traces for `orders-api` or open a trace from a correlated Loki log.

Correlation:

- Logs include valid `trace_id` and `span_id` metadata.
- The Gateway promotes valid trace/span fields to OpenTelemetry log context.
- Loki stores trace context as structured metadata.
- Grafana's Loki datasource provides **View Trace**.
- Grafana's Tempo datasource provides related logs through the existing `tracesToLogsV2` provisioning.

## Troubleshooting

If application telemetry is missing:

1. Confirm the demo Node Agent is running.
2. Confirm the applications use `OTEL_EXPORTER_OTLP_ENDPOINT=http://app-node-agent:4318`.
3. Confirm the Gateway is running.
4. Confirm Grafana datasources `loki`, `tempo`, and `prometheus` are provisioned.
5. Query Prometheus for `up{job="otel-collector"}`.

If logs do not link to traces:

1. Confirm the log record contains a valid 32-character `trace_id`.
2. Confirm the trace exists in Tempo.
3. Confirm Grafana datasource provisioning still includes Loki derived fields and Tempo traces-to-logs configuration.

## Customer Instrumentation Model

For a customer application:

1. Add OpenTelemetry instrumentation in the application runtime.
2. Set stable service identity attributes.
3. Configure OTLP export to the local Node Agent.
4. Deploy the Node Agent with the appropriate capability profile.
5. Open Grafana for logs, metrics, traces, dashboards, and correlation.

The application should not know about Loki, Tempo, Prometheus, or Grafana. It emits OpenTelemetry to the Node Agent.
