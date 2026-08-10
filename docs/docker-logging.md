# Docker logging runbook

The Node Agent discovers local Docker containers with the Docker socket, tails Docker `json-file` logs, unwraps their envelopes, and exports OTLP to the gateway. The gateway normalizes and exports to Loki.

```bash
cd collector/agent
cp .env.example .env
docker compose up -d
```

The Node Agent requires read-only `/var/lib/docker/containers` and `/var/run/docker.sock` mounts. Do not run a second Docker log reader on the same host. In Grafana Explore, query `{service_name="nodejs-demo"}`.
