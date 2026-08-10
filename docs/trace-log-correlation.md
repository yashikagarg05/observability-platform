# Trace and log correlation

The platform uses OpenTelemetry-native log trace context. The gateway accepts valid correlation fields from structured application logs and promotes them to `LogRecord.TraceId` and `LogRecord.SpanId`. It does not create trace context, guess IDs, or add a backend-specific log field.

## Supported input fields

The gateway recognizes these equivalent pairs after JSON or Serilog parsing:

- `trace_id` and `span_id`
- `traceId` and `spanId`
- `TraceId` and `SpanId`

A trace ID must be 32 hexadecimal characters and a span ID must be 16 hexadecimal characters. Invalid values remain application attributes and are not used for correlation. Native OTLP logs that already contain trace context pass through unchanged.

## Data flow

1. An application logger enriches a log event from its active OpenTelemetry context.
2. The gateway validates and promotes the IDs to native OpenTelemetry log context.
3. The OTLP/HTTP Loki exporter sends the log to Loki's native OTLP endpoint.
4. Loki writes `trace_id` and `span_id` as structured metadata, not Loki index labels.
5. Grafana's provisioned Loki derived field provides **View Trace** to Tempo.
6. Grafana's provisioned Tempo data source provides **Logs for this span**, constrained by `service.name`, `service.namespace`, and trace ID.

## Grafana provisioning

`grafana/provisioning/datasources/datasources.yaml` provisions stable Loki (`loki`) and Tempo (`tempo`) data source UIDs. It configures:

- Loki **View Trace** from structured `trace_id` metadata.
- Tempo **Logs for this span** with a two-minute context window.
- Resource identity matching through Loki's `service_name` and `service_namespace` index labels.

Restart or recreate Grafana after changing the provisioning file. Provisioned data sources are intentionally read-only in the Grafana UI; update the file instead.

## Verification after application instrumentation

1. Generate a request that creates a trace and writes a correlated log.
2. In Loki Explore, confirm the log has structured `trace_id` and `span_id` metadata.
3. Select **View Trace** on that log and confirm Tempo opens the same trace.
4. From a span in Tempo, select **Logs for this span** and confirm the Loki query returns the correlated log.

Application-side logger enrichment is intentionally outside this repository and is implemented independently in each application repository.
