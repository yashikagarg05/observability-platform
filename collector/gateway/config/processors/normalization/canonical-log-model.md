# Canonical log model

The gateway converts all supported sources into OpenTelemetry log records before routing to Loki.

| Concern | Canonical representation |
| --- | --- |
| Event time | OpenTelemetry log timestamp |
| Severity | `severity_text` and `severity_number` |
| Display text | Log body |
| Service identity | `service.name`, `service.namespace`, `deployment.environment` resource attributes |
| Runtime identity | `host.name` and Docker container resource attributes when available |
| Provenance | `log.source.type` log attribute |
| Trace correlation | Native OpenTelemetry `LogRecord.TraceId` and `LogRecord.SpanId` |
| Application context | Log attributes and Loki structured metadata |

Supported generic conventions:

- JSON: `timestamp`, `level`, `message`, and optional `service`
- Serilog JSON: `Timestamp`, `Level`, `Message`, `Properties`, and optional `Exception`
- Plain text: preserved as the body with its source timestamp
- Trace context: `trace_id`/`span_id`, `traceId`/`spanId`, or `TraceId`/`SpanId`

When a valid 32-character trace ID or 16-character span ID is present, the gateway promotes it to native OpenTelemetry log context and removes the input attribute. Loki's OTLP endpoint stores the native values as structured `trace_id` and `span_id` metadata; they must never be promoted to index labels.

The gateway preserves fields it does not recognize. Do not promote dynamic application properties, packet payloads, remote endpoints, message fields, trace IDs, or span IDs into Loki labels.
