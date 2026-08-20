# Docker logging runbook

The Node Agent discovers local Docker containers with the Docker socket, tails Docker `json-file` logs, unwraps their envelopes, and exports OTLP to the gateway. The gateway normalizes and exports to Loki.

```bash
cd collector/agent
cp .env.example .env
# Set GATEWAY_OTLP_GRPC_ENDPOINT, AGENT_HOST_NAME, namespace, and environment.

docker compose -f compose.yaml -f config/compose/docker.yaml up -d
```

Use `config/compose/docker-hostmetrics.yaml` instead when Docker logs and host metrics should be collected together.

The Node Agent requires read-only `/var/lib/docker/containers` and `/var/run/docker.sock` mounts. Do not run a second Docker log reader on the same host.

In Grafana Explore, query by the service labels emitted by your workloads. For the reference application, use:

```logql
{service_namespace="demo"}
```

or:

```logql
{service_name="orders-api"}
```
