# Docker logging runbook

## Architecture

The OpenTelemetry Collector discovers running Docker containers through the Docker socket. It creates one `filelog` receiver for each container and tails the matching Docker JSON log file.

```text
Docker container stdout/stderr
  -> Docker JSON log file
  -> OpenTelemetry Collector (Docker observer + filelog)
  -> JSON/plain-text routing and enrichment
  -> OTLP/HTTP
  -> Loki
  -> Grafana Explore
```

The Collector image is excluded through Docker image metadata. This prevents the Collector from ingesting the output it generates and avoids a recursive log loop without relying on generated container IDs.

## Log processing

- Docker JSON is parsed by the Collector's container parser. Its timestamp is the fallback record timestamp for plain-text logs.
- Bodies beginning with `{` are parsed as application JSON. The sample application's `timestamp` becomes the OpenTelemetry log timestamp and `INFO`, `WARN`, and `ERROR` are converted to OpenTelemetry severity.
- JSON fields remain searchable log attributes: `timestamp`, `level`, `service`, `endpoint`, and `message`. `message` is also the log body.
- Plain-text log bodies bypass the JSON parser and remain searchable without parsing failures.

Each log record includes these resource attributes:

| Attribute | Source |
| --- | --- |
| `service.name` | Application JSON `service`, or Docker container name for plain text |
| `service.namespace` | `observability-demo` |
| `deployment.environment` | `docker` |
| `container.id` | Docker observer |
| `container.name` | Docker observer |
| `container.image.name` | Docker observer |

Loki promotes `service.name`, `service.namespace`, and `service.instance.id` to index labels according to `loki/config.yaml`. Other fields are stored as structured metadata.

## Start and validate

From the project root:

```bash
docker compose config
docker compose up -d --force-recreate otel-collector
docker compose logs --tail=100 otel-collector
```

The Collector needs `/var/run/docker.sock` to discover container names and labels. Access to this socket effectively grants Docker-daemon control to the Collector process. Keep its configuration mounted read-only, restrict who can change the Compose project, and do not expose the Collector administration surface publicly.

Generate a sample JSON event from the externally managed application:

```bash
docker exec nodejs-demo wget -qO- http://127.0.0.1:3001/hello
```

In Grafana Explore, select the Loki datasource and query:

```logql
{service_name="nodejs-demo"}
```

Inspect a result for the application timestamp, `severity_text=INFO`, `endpoint=/hello`, and the Docker container resource attributes. In Grafana's label selector UI, the same label appears as `service.name="nodejs-demo"`.

## Kubernetes migration gate

Do not begin Kubernetes migration until all of these Docker checks pass:

1. JSON Node.js logs appear in Loki with the expected timestamp, severity, service, endpoint, and message.
2. A plain-text record from another Docker service appears without Collector parser errors.
3. Collector logs are absent from Loki, and Collector output has no recursive log growth.
4. Grafana Explore can query the Node.js logs by `service.name`.
5. Existing traces in Tempo and Prometheus metrics remain healthy after the Collector recreation.

Kubernetes will replace Docker discovery and file paths with a DaemonSet and Kubernetes-native container log collection while preserving the common parsing, enrichment, OTLP export, and Grafana queries.
