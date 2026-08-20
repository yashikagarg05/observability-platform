# Node Agent migration from legacy local readers

This runbook is for operators migrating from legacy gateway-local Docker or file log readers to the source-host Node Agent. Greenfield deployments should start with [Node Agent onboarding](node-agent-onboarding.md).

`collector/agent` is the source-host package. Deploy it one node at a time, including the central VM, but keep the legacy source agent or gateway receiver active until its replacement has been validated.

```bash
cd collector/agent
cp .env.example .env
# Set GATEWAY_OTLP_GRPC_ENDPOINT, AGENT_HOST_NAME, namespace, and environment.

# Example: Docker stdout logs plus host metrics.
docker compose -f compose.yaml -f config/compose/docker-hostmetrics.yaml up -d
```

Validate the Node Agent, then stop the replaced legacy reader before enabling Node Agent collection for the same paths. The gateway continues to normalize schemas and route telemetry.

Plaintext OTLP/gRPC remains available for migration compatibility. For production transport, install client certificates and include the mTLS overlay:

```bash
NODE_AGENT_TRANSPORT_SUFFIX=-mtls
NODE_AGENT_CERTS_HOST_PATH=/etc/otel-node-agent/certs
NODE_AGENT_SECRETS_HOST_PATH=/etc/otel-node-agent/secrets

docker compose \
  -f compose.yaml \
  -f config/compose/docker-hostmetrics.yaml \
  -f config/compose/mtls.yaml \
  up -d
```
