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
| Application context | Log attributes and Loki structured metadata |

Supported generic conventions:

- JSON: `timestamp`, `level`, `message`, and optional `service`
- Serilog JSON: `Timestamp`, `Level`, `Message`, `Properties`, and optional `Exception`
- Plain text: preserved as the body with its source timestamp

The gateway preserves fields it does not recognize. Do not promote dynamic application properties, packet payloads, remote endpoints, or message fields into Loki labels.
