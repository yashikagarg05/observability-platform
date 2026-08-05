# Remote log collection runbook

## Architecture

The central Collector can only read Docker files and application files on its own host. Run a Collector agent on every remote host and forward logs to the central Collector through OTLP/gRPC.

```text
Remote Docker host -> Docker log agent -> central Collector -> Loki -> Grafana Explore
Remote application host -> file log agent -> central Collector -> Loki -> Grafana Explore
```

The central logs pipeline accepts both its local Docker logs and OTLP logs sent by remote agents. Agents only access local sources and forward records; the central gateway normalizes log schemas and enriches missing identity before it exports to Loki.

## Remote Docker hosts

On a host using rootful Docker with the `json-file` logging driver:

```bash
cd collector/agents/docker
# Set GATEWAY_OTLP_GRPC_ENDPOINT and AGENT_HOST_NAME.
docker compose up -d
```

The Docker agent reads `/var/lib/docker/containers` and discovers containers through `/var/run/docker.sock`. It adds:

- `host.name`
- `container.id`
- `container.name`
- `container.image.name`
- `service.namespace`
- `deployment.environment`

It persists file offsets and its retry queue in the `otel-docker-agent-state` volume. The initial `start_at: end` setting intentionally avoids backfilling historic logs when an agent is first installed.

Rootless Docker or a non-`json-file` logging driver needs a different log mount and receiver configuration.

## Remote application log files

Use one file agent per trusted application log directory and service identity. Do not mount broad directories such as all of `/var/log`.

```bash
cd collector/agents/file
# Set APP_LOG_HOST_PATH, APP_LOG_GLOB, service identity, and gateway endpoint.
docker compose up -d
```

The mounted host directory appears in the agent as `/var/log/application`. The file agent forwards raw records. The central gateway normalizes generic JSON fields such as `timestamp`, `level`, `service`, `endpoint`, and `message`, Serilog JSON fields such as `Timestamp`, `Level`, and `Message`, and plain text. The configured `OTEL_SERVICE_NAME` is the fallback service identity.

## Grafana and Loki queries

Select the Loki datasource in Grafana Explore and use the service label:

```logql
{service_name="my-application"}
```

Narrow to a remote host with structured metadata in Explore, such as `host.name`, or to a Docker workload using `container.name`. Loki indexes the service labels configured in `loki/config.yaml`; host and container details remain structured metadata to avoid high-cardinality indexes.

## Networking and security

Remote agents must be able to reach the central Collector's OTLP/gRPC listener on TCP 4317. Restrict the central host firewall or security group to known agent egress addresses and do not expose the endpoint to arbitrary internet clients.

The initial agent configuration deliberately uses plaintext OTLP/gRPC (`tls.insecure: true`) because TLS is not currently available. This is not production-safe on any public path:

- log bodies and metadata can be read or modified in transit;
- senders are not authenticated, so an attacker can inject telemetry;
- disk-backed queues and file offsets may contain sensitive data.

TLS with client authentication, or a private network/VPN, is mandatory before production rollout. Secure agent state directories and client credentials, limit who can edit Collector configuration, and scrub secrets or personal data before application logs are emitted.

## Validation

On each remote host:

```bash
docker compose config
docker compose logs --tail=100
```

Generate an application log, then query Loki by `service_name`. Confirm `host.name`, the configured environment and namespace, and either container metadata (Docker agent) or file metadata (file agent). If delivery is interrupted, the disk-backed agent queue retries until the central Collector becomes reachable.
