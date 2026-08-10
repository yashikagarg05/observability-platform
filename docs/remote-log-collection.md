# Node Agent migration

`collector/agent` is the new source-host package. Deploy it one node at a time, including the central VM, but keep the legacy source agent or gateway receiver active until its replacement has been validated.

```bash
cd collector/agent
cp .env.example .env
# Set the gateway endpoint, host identity, service fallback, and log directory.
docker compose up -d
```

Validate the Node Agent, then stop the replaced legacy reader before enabling Node Agent collection for the same paths. The gateway continues to normalize schemas and route telemetry. The current gRPC transport is plaintext; restrict TCP 4317 to trusted private networks until TLS/mTLS is added.
