# Node Agent Enrollment MVP

This MVP adds enrollment, registry visibility, and basic certificate lifecycle controls for Node Agent mTLS. Production CA signing is not implemented in this repository; production mode uses the external issuer boundary documented in `docs/production-enrollment-lifecycle.md`.

## Flow

```text
one-time enrollment credential
  -> bin/enroll-node-agent.sh enroll
  -> local private key
  -> CSR
  -> POST /v1/node-agents/enroll
  -> API assigns agent_id
  -> configured CertificateIssuer signs client cert
  -> cert and CA bundle installed locally
  -> Node Agent connects to Gateway with mTLS
```

The private key is generated on the Node Agent host and is never sent to the API. The enrollment request body contains only `csr_pem`.

## Endpoint

```text
POST /v1/node-agents/enroll
Authorization: Bearer <one-time enrollment credential>
Content-Type: application/json

{
  "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----..."
}
```

The response contains:

- `agent_id`
- `agent_uri`
- `certificate_pem`
- `ca_bundle_pem`

The API marks the credential as used after successful issuance. Reuse fails.

Successful enrollment also creates or updates a record in the persistent Agent Registry.

## Agent Registry

The registry is a JSON file configured with `ENROLLMENT_REGISTRY_FILE`. If unset, it is created next to the credential file as `agent-registry.json`.

Schema:

```json
{
  "agents": {
    "agent-id": {
      "agent_id": "agent-id",
      "tenant_id": "tenant-a",
      "site_id": "site-1",
      "environment": "validation",
      "host_name": "node-1",
      "agent_version": "1.1.0",
      "capabilities": ["otlp", "hostmetrics"],
      "created_at": 0,
      "last_seen_at": null,
      "certificate_identity": "spiffe://...",
      "certificate_fingerprint": "sha256-hex",
      "certificate_serial": "hex-serial",
      "certificate_issuer": "external-command",
      "certificate_issued_at": 0,
      "certificate_expires_at": 0,
      "certificate_status": "valid",
      "disabled_at": null,
      "disabled_reason": null
    }
  }
}
```

Enrollment does not mark an Agent healthy. Status is computed from heartbeat `last_seen_at`.

## Heartbeat

The helper can send an explicit heartbeat:

```bash
NODE_AGENT_ENROLLMENT_ENDPOINT=http://enrollment.example.net:8080 \
AGENT_HOST_NAME=node-1 \
NODE_AGENT_VERSION=1.1.0 \
NODE_AGENT_CAPABILITIES=otlp,hostmetrics \
bin/enroll-node-agent.sh heartbeat
```

Default status thresholds:

- `healthy`: heartbeat seen within `AGENT_STALE_AFTER_SECONDS`, default 90 seconds.
- `stale`: heartbeat older than stale threshold but within `AGENT_OFFLINE_AFTER_SECONDS`, default 300 seconds.
- `offline`: no heartbeat or heartbeat older than offline threshold.

Tests may lower these thresholds with environment variables on the API process.

## Registry API

List agents:

```text
GET /v1/node-agents?tenant_id=<tenant>[&site_id=...][&environment=...][&status=...]
```

Get agent detail:

```text
GET /v1/node-agents/{agent_id}?tenant_id=<tenant>
```

Heartbeat:

```text
POST /v1/node-agents/{agent_id}/heartbeat
X-Tenant-ID: <tenant>
Content-Type: application/json
```

Renew certificate:

```text
POST /v1/node-agents/{agent_id}/renew
Authorization: Bearer <one-time renewal credential>
Content-Type: application/json

{
  "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----..."
}
```

Disable Agent:

```text
POST /v1/node-agents/{agent_id}/disable?tenant_id=<tenant>
Authorization: Bearer <operator token>
Content-Type: application/json

{
  "reason": "operator disabled"
}
```

Minimal HTML workspace:

```text
GET /agents?tenant_id=<tenant>
```

Tenant isolation is enforced at the API boundary by requiring a tenant context through `X-Tenant-ID` or `tenant_id` query parameter and returning only matching records.

## Issuer Modes

`services/enrollment/enrollment_api.py` uses a `CertificateIssuer` abstraction.

- `external`: production path. Calls `ENROLLMENT_PRODUCTION_ISSUER_COMMAND` and fails safely if it is not configured.
- `development`: validation only. Requires `ENROLLMENT_ALLOW_DEVELOPMENT_ISSUER=true`.

Do not use the development issuer as production PKI. The repository provides the integration boundary, not a production CA.

## Agent Command

```bash
NODE_AGENT_SECRET_DIR=/etc/otel-node-agent/secrets \
NODE_AGENT_CERT_DIR=/etc/otel-node-agent/certs \
NODE_AGENT_ENROLLMENT_ENDPOINT=http://enrollment.example.net:8080 \
NODE_AGENT_ENROLLMENT_CREDENTIAL=<credential> \
bin/enroll-node-agent.sh enroll
```

Renew without replacing the current working certificate until the new certificate is validated:

```bash
NODE_AGENT_SECRET_DIR=/etc/otel-node-agent/secrets \
NODE_AGENT_CERT_DIR=/etc/otel-node-agent/certs \
NODE_AGENT_ENROLLMENT_ENDPOINT=http://enrollment.example.net:8080 \
NODE_AGENT_RENEWAL_CREDENTIAL=<credential> \
bin/enroll-node-agent.sh renew
```

After enrollment, use the existing mTLS overlay:

```bash
NODE_AGENT_TRANSPORT_SUFFIX=-mtls
NODE_AGENT_CERTS_HOST_PATH=/etc/otel-node-agent/certs
NODE_AGENT_SECRETS_HOST_PATH=/etc/otel-node-agent/secrets
docker compose -f compose.yaml -f config/compose/otlp-hostmetrics.yaml -f config/compose/mtls.yaml up -d
```

## Credential Store

Development credentials use a JSON file:

```json
{
  "tokens": {
    "example-token": {
      "tenant_id": "tenant-a",
      "site_id": "site-1",
      "environment": "development",
      "identity_domain": "observability.local",
      "used": false
    }
  }
}
```

Use `scripts/create-dev-enrollment-credential.py` to create one-time development enrollment credentials for tests.

## Out Of Scope

- Production CA automation.
- Full automatic rotation policy.
- CRL/OCSP infrastructure.
- Fleet upgrades or remote configuration.
- Sophisticated Agent Registry.
- Per-agent revocation beyond one-time credential use and CA trust boundaries.
