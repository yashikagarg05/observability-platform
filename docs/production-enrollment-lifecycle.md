# Production Enrollment And Certificate Lifecycle MVP

This MVP adds a production-safe enrollment boundary and basic certificate lifecycle controls. It does not implement a production CA. Production certificate signing remains the responsibility of a customer-managed CA, internal PKI service, or external certificate platform.

## Architecture

```text
Node Agent
  -> local private key
  -> CSR only
  -> Control Plane enrollment API
  -> CertificateIssuer boundary
  -> external/customer-managed CA integration
  -> signed client certificate
  -> Agent Registry lifecycle state
```

The Node Agent private key never leaves the Agent host. The API rejects request bodies containing private key material.

## Issuer Modes

- `ENROLLMENT_ISSUER_MODE=external`: production path. Requires `ENROLLMENT_PRODUCTION_ISSUER_COMMAND`. The Control Plane fails to start if the command is missing.
- `ENROLLMENT_ISSUER_MODE=development`: local validation only. Requires `ENROLLMENT_ALLOW_DEVELOPMENT_ISSUER=true` and development CA files. Do not use this mode for production.

The external issuer command receives:

```text
ENROLLMENT_CSR_FILE
ENROLLMENT_REQUEST_FILE
ENROLLMENT_CERTIFICATE_FILE
ENROLLMENT_AGENT_URI
ENROLLMENT_AGENT_ID
ENROLLMENT_TENANT_ID
ENROLLMENT_SITE_ID
ENROLLMENT_ENVIRONMENT
```

It must write the signed certificate PEM to `ENROLLMENT_CERTIFICATE_FILE`.

If `ENROLLMENT_PRODUCTION_ISSUER_CA_BUNDLE` is set, the Control Plane validates the returned client certificate chain and profile before accepting it.

## Certificate Profile Validation

Issued certificates are accepted only if they:

- contain the expected Agent URI SAN
- include client authentication EKU
- validate against the configured issuer CA bundle when provided

## Lifecycle State

Certificate state is stored in the Agent Registry:

- `valid`: certificate exists and is not close to expiry
- `expiring_soon`: certificate expires within 20 days
- `expired`: certificate expiry time has passed
- `disabled`: operator explicitly disabled the Agent
- `unknown`: legacy or incomplete certificate metadata

Agent health state remains based on heartbeat, except disabled Agents report `disabled`.

## Renewal

Renewal uses a one-time renewal credential:

1. Operator creates a renewal credential for an Agent.
2. Node Agent runs `bin/enroll-node-agent.sh renew`.
3. The helper creates a replacement private key and CSR in temporary files.
4. The API signs the CSR through the configured issuer boundary.
5. The helper validates that the returned certificate matches the replacement private key and expected Agent URI SAN.
6. Only after validation, the helper installs the replacement key/cert and preserves the previous working files with `.previous` suffixes.

Renewal does not destroy a working certificate before the replacement is validated.

## Disable / Deny

Operators can disable an Agent:

```text
POST /v1/node-agents/{agent_id}/disable
```

Disabled Agents:

- show `status=disabled`
- show `certificate_status=disabled`
- cannot heartbeat
- cannot renew certificates

This MVP does not implement CRL, OCSP, or Gateway-side dynamic revocation. To deny telemetry transport for an already issued certificate, operators must remove trust for the issuing CA or update Gateway-side authorization in a future milestone.

## Audit Schema

Certificate issuance and renewal audit records include:

- `event`
- `agent_id`
- `tenant_id`
- `site_id`
- `environment`
- `agent_uri`
- `csr_sha256`
- `certificate_fingerprint`
- `certificate_serial`
- `certificate_issuer`
- `certificate_issued_at`
- `certificate_expires_at`
- `result`
- `private_key_present`
- `token_sha256`

Credentials are never logged in plaintext.

## Out Of Scope

- Production CA implementation
- CA administration UI
- OCSP or CRL infrastructure
- Full IAM/RBAC
- Fleet upgrades
- Remote configuration
