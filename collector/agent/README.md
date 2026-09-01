# OpenTelemetry Node Agent

The Node Agent is the single source-host Collector deployment. It knows local telemetry sources and exports only OTLP to the central Gateway. It has no Loki, Tempo, Prometheus, or Grafana configuration.

## Source profiles

- `config/compose/otlp.yaml`: local OTLP logs, traces, and metrics.
- `config/compose/docker.yaml`: Docker `json-file` stdout/stderr logs.
- `config/compose/docker-file.yaml`: Docker logs plus one explicitly mounted application log directory.
- `config/compose/otlp-hostmetrics.yaml`: local OTLP plus host infrastructure metrics.
- `config/compose/docker-hostmetrics.yaml`: Docker logs plus host infrastructure metrics.
- `config/compose/docker-file-hostmetrics.yaml`: Docker and file logs plus host infrastructure metrics.

The Prometheus receiver module is packaged but intentionally inactive. Host metrics are enabled only by selecting a hostmetrics profile; the default profile is unchanged.

## Deploy

```bash
cp .env.example .env
# Select one profile; for example, Docker logs:
docker compose -f compose.yaml -f config/compose/docker.yaml up -d
```

The OTLP profiles publish local intake ports. Docker and file profiles do not publish ports or mount unrelated sources. Do not run this alongside another reader for the same Docker or file source paths.

Hostmetrics profiles mount the host root filesystem read-only at `/hostfs`. The Collector runs as root in the container so it can read Linux host `/proc`, `/sys`, and filesystem statistics through that mount.

The distributable archive contains `compose.yaml`, `config/`, `.env.example`, `bin/`, and this README.

## Capability model

Capabilities are reusable release-author building blocks: `otlp`, `docker`, `filelog`, `hostmetrics`, and `prometheus`. Profiles are the supported operator-facing combinations.

The current profiles are:

- `otlp`: `otlp`
- `docker`: `otlp` + `docker`
- `docker-file`: `otlp` + `docker` + `filelog`
- `otlp-hostmetrics`: `otlp` + `hostmetrics`
- `docker-hostmetrics`: `otlp` + `docker` + `hostmetrics`
- `docker-file-hostmetrics`: `otlp` + `docker` + `filelog` + `hostmetrics`

`prometheus` remains a disabled capability with no supported profile. Generated configs are in `config/generated/`, while `config/profiles/` remains as the V1 compatibility layer.

## Hostmetrics Capability

`hostmetrics` collects baseline Linux machine metrics from the local node and exports them only as OTLP metrics to the Gateway. The Node Agent does not contain Prometheus, Grafana, Loki, or Tempo configuration; the Gateway exposes metrics through its existing Prometheus exporter, and Prometheus scrapes the Gateway.

The receiver uses a 60 second collection interval and collects:

- CPU utilization and time.
- Memory usage.
- Disk I/O, excluding loop, RAM, and zram devices.
- Filesystem usage, excluding pseudo filesystems, container runtime mounts, overlays, and snap mounts.
- Network I/O, excluding loopback, veth, Docker bridge, and bridge interfaces.
- System load and paging.

Resource identity follows the existing Node Agent convention. Set `AGENT_HOST_NAME` to the stable node name; the resource processor upserts it as `host.name` on metrics, logs, and traces. `OTEL_SERVICE_NAMESPACE` and `OTEL_DEPLOYMENT_ENVIRONMENT` are also preserved as resource attributes.

To verify hostmetrics after deployment, query Prometheus for metrics from the Gateway scrape path. Metric names are exported using Prometheus naming, for example:

```promql
system_cpu_time_seconds_total
system_memory_usage_bytes
system_filesystem_usage_bytes
system_network_io_bytes_total
```

Use the resource-derived labels to confirm `host_name`, `service_namespace`, and `deployment_environment` identify the node. Expected overhead is low for general Linux nodes: one hostmetrics scrape per minute, no per-process metrics, and filters for common high-cardinality container and pseudo-filesystem labels.

## mTLS Transport

The default transport remains plaintext OTLP/gRPC for migration compatibility. To use mTLS, install client certificate material outside the release archive and set:

```bash
NODE_AGENT_TRANSPORT_SUFFIX=-mtls
NODE_AGENT_CERTS_HOST_PATH=/etc/otel-node-agent/certs
NODE_AGENT_SECRETS_HOST_PATH=/etc/otel-node-agent/secrets
```

Then include `config/compose/mtls.yaml` after the selected source profile:

```bash
docker compose -f compose.yaml -f config/compose/docker-hostmetrics.yaml -f config/compose/mtls.yaml up -d
```

The package includes `bin/enroll-node-agent.sh` to create a local private key and CSR, enroll against the MVP enrollment API, or install a signed client certificate and CA bundle. See `docs/node-agent-mtls.md` and `docs/node-agent-enrollment-mvp.md` in the repository for the full enrollment and Gateway migration model.

## Uninstrumented local processes

Use `bin/otel-run` when a local process only writes stdout/stderr and is not otherwise instrumented: it is not running in Docker, does not write application log files, and does not emit OTLP itself.

```bash
bin/otel-run npm run dev
bin/otel-run python app.py
bin/otel-run java -jar app.jar
bin/otel-run --service orders-api -- npm run dev
```

`otel-run` keeps the child's output on the terminal and sends each line to the Node Agent as an OTLP log. It requires Python 3. The Node Agent must expose OTLP HTTP on `localhost:4318`, which is published by the `otlp` and `otlp-hostmetrics` profiles. Docker-only and file profiles do not publish that port, so `otel-run` cannot reach the agent with those profiles.
