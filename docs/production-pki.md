# Production PKI for Node Agent mTLS

This runbook defines the Phase 1 production PKI foundation for Node Agent to Gateway mTLS. Production enrollment now uses an external issuer integration boundary documented in `docs/production-enrollment-lifecycle.md`; this repository still does not implement or operate a production CA.

## Architecture

Production mTLS uses a private PKI with an offline root CA and constrained intermediates:

```text
Offline Root CA
  ├── Gateway Server Intermediate CA
  │     └── Gateway server certificate
  └── Agent Client Intermediate CA
        └── Node Agent client certificate
```

The Gateway presents a server certificate to Node Agents. Each Node Agent presents a client certificate to the Gateway. Plaintext OTLP/gRPC remains available during migration and rollback.

## Root CA

The root CA signs only intermediate CAs.

- Basic constraints: critical CA true.
- Key usage: critical `keyCertSign`, `cRLSign`.
- Path length: `1`.
- Recommended lifetime: 10 years.
- Private key storage: offline system, HSM, or equivalent controlled custody.
- The root private key must never be stored on a Gateway, Node Agent, CI runner, release archive, or repository.

## Intermediate CAs

Use separate intermediate profiles for Gateway server certificates and Node Agent client certificates.

Gateway Server Intermediate CA:

- Basic constraints: critical CA true, `pathlen:0`.
- Key usage: critical `keyCertSign`, `cRLSign`.
- Recommended lifetime: 2 to 5 years.
- Signs only Gateway or load-balancer server certificates.

Agent Client Intermediate CA:

- Basic constraints: critical CA true, `pathlen:0`.
- Key usage: critical `keyCertSign`, `cRLSign`.
- Recommended lifetime: 1 to 3 years.
- Signs only Node Agent client certificates.
- Future tenants or sites can receive separate Agent Client Intermediate CAs to reduce revocation blast radius.

## Leaf Certificate Profiles

Gateway server certificate:

- Key usage: critical `digitalSignature`; include `keyEncipherment` for RSA keys.
- Extended key usage: `serverAuth`.
- SAN: DNS names Node Agents use, such as `otlp.example.com`.
- CN: informational only.
- Recommended Phase 1 lifetime: 180 days.

Node Agent client certificate:

- Key usage: critical `digitalSignature`; include `keyEncipherment` for RSA compatibility.
- Extended key usage: `clientAuth`.
- SAN: URI identity only.
- CN: informational agent ID only.
- Lifetime: 60 days.
- Renewal window: 20 days before expiration. Automatic renewal is a later phase.

Recommended key algorithm for Phase 1 is RSA 3072 for compatibility with the current OpenSSL helpers and Collector image.

## Agent Identity

Node Agent certificates use this URI SAN format:

```text
spiffe://observability.local/tenant/{tenant_id}/site/{site_id}/environment/{environment}/agent/{agent_id}
```

Identity rules:

- `tenant_id` is the customer or organization boundary.
- `site_id` is the stable deployment or site boundary.
- `environment` is `production`, `staging`, `development`, or similar.
- `agent_id` is immutable for the logical Node Agent and should not be a recycled hostname.
- The certificate identity is security-plane identity. Existing telemetry resource identity still uses `host.name`, `service.namespace`, and `deployment.environment`.

Do not place certificate serials, fingerprints, full subjects, or private tenant metadata into Prometheus labels.

## Runtime File Layout

Node Agent host:

```text
/etc/otel-node-agent/
  certs/
    ca-bundle.pem
    client.crt
    client.csr
    agent-identity.uri
  secrets/
    client.key
```

Gateway host:

```text
/etc/otel-gateway/
  certs/
    gateway.crt
    gateway-ca-bundle.pem
    agent-ca-bundle.pem
  secrets/
    gateway.key
```

Permissions:

- Secret directories: `0700`, owned by root.
- Private keys: `0600`, owned by root.
- Certificates and CA bundles: `0644` or stricter.
- Container mounts remain read-only at `/tls/certs` and `/tls/secrets`.

## Initial Production Issuance

1. Create the offline root CA using the approved ceremony and template.
2. Create Gateway Server and Agent Client Intermediate CAs.
3. Issue the Gateway server certificate for the exact DNS name Node Agents use.
4. Install Gateway certificate and key under `/etc/otel-gateway`.
5. Install the trusted Agent Client Intermediate bundle as `/etc/otel-gateway/certs/agent-ca-bundle.pem`.
6. On each pilot Node Agent host, run `bin/enroll-node-agent.sh request` to generate the private key and CSR locally.
7. Submit the CSR through an approved authenticated channel to the CA operator or certificate platform.
8. Validate tenant, site, environment, agent ID, and URI SAN before signing.
9. Sign the CSR with the approved Agent Client Intermediate CA.
10. Transfer only `client.crt` and `ca-bundle.pem` back to the Node Agent host.
11. Install the signed cert and CA bundle with `bin/enroll-node-agent.sh install`.
12. Enable `NODE_AGENT_TRANSPORT_SUFFIX=-mtls` and include `config/compose/mtls.yaml`.

The Node Agent private key must never leave the Node Agent host.

## Secure Transfer

Approved transfer methods:

- SSH or SFTP to the target host.
- Secret manager delivery with access logs.
- Configuration management with secret handling.
- Authenticated internal certificate portal.

Do not transfer production certificates or CA bundles through chat, email attachments, public links, or release artifacts. Do not transfer private keys off-host.

## Development vs Production

Development PKI is generated by `scripts/dev-mtls-certs.sh` and is only for local validation. Development CA material must not be trusted by production Gateways or Node Agents.

Production PKI uses offline root custody, controlled intermediates, production certificate profiles, and runtime-mounted certs. Production keys and issued certs are never committed to this repository.

## Package Boundary

The Node Agent `.tgz` may include:

- Collector config.
- Compose overlays.
- Non-secret helper scripts.
- Non-secret documentation.
- Non-secret PKI templates.

The package must not include:

- Root or intermediate private keys.
- Gateway or Node Agent private keys.
- Issued production certificates.
- Tenant-specific CA bundles.
- Enrollment tokens.
- CA databases, serial files, CRLs, or production CSRs.

## Migration From Development Certificates

1. Create production CA hierarchy.
2. Install production Gateway server cert and trusted Agent Client Intermediate bundle.
3. Deploy the Gateway mTLS overlay while keeping plaintext enabled.
4. Generate new Node Agent CSRs on the target hosts.
5. Sign production client certificates.
6. Install production client certs and CA bundles.
7. Enable the Node Agent mTLS overlay.
8. Validate telemetry over mTLS.
9. Remove development cert directories from hosts.
10. Confirm production Gateway trust stores do not include development CA material.

## Rollback

If production mTLS validation fails, keep plaintext enabled and roll the affected Node Agent back by removing `NODE_AGENT_TRANSPORT_SUFFIX=-mtls` and omitting `config/compose/mtls.yaml`. If Gateway mTLS configuration fails, redeploy the default Gateway config. Backend routing and telemetry pipelines are unchanged.

## Current Limitations

- Production CA implementation remains external/customer-managed.
- Certificate renewal uses one-time credentials and the external issuer boundary; full automated rotation policy is future work.
- Control-plane disablement prevents heartbeat and renewal, but Gateway-side dynamic revocation requires future authorization work or CA trust removal.
- No fleet management.
