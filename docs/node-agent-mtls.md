# Node Agent to Gateway mTLS

The Node Agent supports mTLS as an OTLP/gRPC transport option. It remains a local telemetry collector and exporter only; it does not know about Loki, Tempo, Prometheus, or Grafana.

For production CA hierarchy, certificate profiles, issuance ceremony, and migration from development certificates, see `docs/production-pki.md`.

## Trust Model

Production deployments should use a private PKI with an offline or tightly controlled root CA and an issuing intermediate CA. Gateway server certificates and Node Agent client certificates may be issued by separate constrained intermediates or by one intermediate with separate issuance profiles.

Node Agent client certificates identify agents with a URI SAN:

```text
spiffe://observability.local/tenant/<tenant_id>/site/<site_id>/environment/<environment>/agent/<agent_id>
```

The CN is informational only. The Gateway authenticates the client certificate chain, expiration, and client certificate trust root. Authorization should use the URI SAN identity and the issuing CA boundary.

## Certificate Defaults

- Node Agent client certificate lifetime: 60 days.
- Renewal window: start renewal when 20 days remain, with jitter in production automation.
- Gateway certificate lifetime: up to 365 days for the first implementation.
- Development certificates are generated from a local development CA and must not be reused in production.

## Agent Secret Layout

Store certificate material on the Linux host outside the release archive:

```text
/etc/otel-node-agent/certs/ca-bundle.pem
/etc/otel-node-agent/certs/client.crt
/etc/otel-node-agent/secrets/client.key
```

Recommended permissions:

- `/etc/otel-node-agent/secrets`: `0700`, owned by root.
- `client.key`: `0600`, owned by root.
- certificates and CA bundles: `0644` or stricter.

The compose mTLS overlay mounts these directories read-only into the Collector container.

## Node Agent Configuration

Set the normal source profile, then add the mTLS transport suffix and mTLS overlay:

```bash
NODE_AGENT_TRANSPORT_SUFFIX=-mtls
NODE_AGENT_CERTS_HOST_PATH=/etc/otel-node-agent/certs
NODE_AGENT_SECRETS_HOST_PATH=/etc/otel-node-agent/secrets
GATEWAY_OTLP_GRPC_ENDPOINT=gateway.example.com:4319

docker compose \
  -f compose.yaml \
  -f config/compose/docker-hostmetrics.yaml \
  -f config/compose/mtls.yaml \
  up -d
```

The source profile is unchanged. `docker-hostmetrics` still controls local collection. The suffix selects `config/generated/docker-hostmetrics-mtls.yaml`, which uses the secure Gateway exporter.

## Enrollment Helper

The package includes `bin/enroll-node-agent.sh`.

Create a private key and CSR:

```bash
sudo NODE_AGENT_TENANT_ID=tenant-a \
  NODE_AGENT_SITE_ID=site-1 \
  NODE_AGENT_ENVIRONMENT=production \
  NODE_AGENT_AGENT_ID=node-001 \
  bin/enroll-node-agent.sh request
```

Send the CSR to the approved enrollment or CA service. After receiving a signed client certificate and CA bundle:

```bash
sudo NODE_AGENT_SIGNED_CERT=/path/to/client.crt \
  NODE_AGENT_CA_BUNDLE=/path/to/ca-bundle.pem \
  bin/enroll-node-agent.sh install
```

The helper does not embed enrollment secrets and does not issue production certificates.

## Gateway Migration Mode

Use the Gateway mTLS overlay to add an mTLS OTLP/gRPC listener on `4319` while preserving the existing plaintext listener on `4317`:

```bash
GATEWAY_CERTS_HOST_PATH=/etc/otel-gateway/certs \
GATEWAY_SECRETS_HOST_PATH=/etc/otel-gateway/secrets \
docker compose \
  -f docker-compose.yml \
  -f deployments/docker-compose/gateway-mtls.yaml \
  up -d otel-collector
```

The mTLS Gateway config receives from both `otlp` and `otlp/mtls`, then uses the existing normalization, enrichment, batching, and backend export pipelines.

## Development Certificates

For local validation only:

```bash
GATEWAY_DNS=otel-collector \
NODE_AGENT_TENANT_ID=dev-tenant \
NODE_AGENT_SITE_ID=dev-site \
NODE_AGENT_ENVIRONMENT=development \
NODE_AGENT_AGENT_ID=dev-agent-01 \
./scripts/dev-mtls-certs.sh /tmp/otel-dev-mtls
```

Use the printed paths in the Gateway and Node Agent compose commands. Do not commit or reuse generated development keys.

## Authorization MVP

The initial authorization boundary is:

- Gateway trusts only the approved Node Agent client CA bundle.
- Issued client certificates contain tenant, site, environment, and agent ID in URI SAN.
- Unknown agents are denied by not issuing certificates or by removing trust for their issuer during incident response.

The next authorization step should add a registry check for active, disabled, and revoked agent identities before plaintext migration is complete.

## Failure Behavior

- Invalid Gateway certificate: Node Agent refuses the connection and keeps retrying with its persistent queue.
- Expired or untrusted client certificate: Gateway rejects the agent; local queue and retry continue until cert recovery.
- Gateway unreachable or network outage: existing retry and persistent queue behavior remains unchanged.
- CA rollover: deploy overlapping trust bundles before rotating certificates.

## Private And Public Networks

mTLS is required for production even on private networks, VPNs, and private load balancers. Network placement limits exposure, but mTLS authenticates the agent and encrypts OTLP traffic.
