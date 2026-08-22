# Agent Management Lifecycle

The management path is optional for collecting telemetry, but it becomes important when operators need to onboard and operate Node Agents across hosts.

Core telemetry moves observability data:

```text
Applications / infrastructure -> Node Agent -> Gateway -> Loki / Prometheus / Tempo -> Grafana
```

The management path controls who can join that telemetry path:

```text
Operator -> Platform Console -> Control Plane API -> Agent Registry
                                      ^
                                      |
                                  Node Agent
```

## Use Case: Onboard A New VM

Suppose a new VM named `payments-vm-1` needs to send telemetry to the platform.

Without the management path, an operator would need to manually distribute certificates, configuration, and identity metadata.

With the management path:

1. The operator creates a one-time enrollment credential for a tenant, site, environment, and capability set.
2. The Node Agent generates its private key locally on the VM.
3. The Node Agent sends a CSR to the Control Plane API.
4. The Control Plane issues a short-lived certificate and returns the Gateway trust bundle.
5. The Agent Registry records the agent identity, certificate metadata, capabilities, and lifecycle state.
6. The Node Agent sends heartbeats so operators can see whether it is healthy, stale, offline, or disabled.

The private key never leaves the node.

## What Operators Get

- Controlled onboarding with one-time credentials.
- Inventory of enrolled agents by tenant, site, and environment.
- Certificate identity, issuer, expiry, and fingerprint visibility.
- Heartbeat-based health state.
- Disable state for agents that should no longer participate.
- Links back into Grafana for investigation workflows.

## Example Flow

For the integrated local demo, start the telemetry stack and management services together:

```bash
make demo-up
make demo-management-up
make demo-management-agent
```

Open:

```text
Grafana:        http://localhost:3000
Platform UI:    http://localhost:4173
Control API:    http://localhost:8080
Operator token: local-management-operator-token-1234567890
```

The `demo-management-agent` target enrolls a sample managed Node Agent named `payments-vm-1` and sends a heartbeat.

The manual API flow is:

Create an enrollment credential:

```bash
curl -sS \
  -H "Authorization: Bearer $CONTROL_PLANE_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  "http://localhost:${CONTROL_PLANE_PORT}/v1/enrollment/credentials?tenant_id=${CONTROL_PLANE_TENANT_ID}" \
  -d '{"site_id":"site-1","environment":"production","capabilities":["otlp","hostmetrics"]}'
```

Enroll the Node Agent on the target VM from inside the extracted `otel-node-agent-<version>` release artifact:

```bash
NODE_AGENT_SECRET_DIR=/etc/otel-node-agent/secrets \
NODE_AGENT_CERT_DIR=/etc/otel-node-agent/certs \
NODE_AGENT_ENROLLMENT_ENDPOINT=http://localhost:${CONTROL_PLANE_PORT} \
NODE_AGENT_ENROLLMENT_CREDENTIAL=<credential> \
bin/enroll-node-agent.sh enroll
```

Send a heartbeat:

```bash
NODE_AGENT_SECRET_DIR=/etc/otel-node-agent/secrets \
NODE_AGENT_CERT_DIR=/etc/otel-node-agent/certs \
NODE_AGENT_ENROLLMENT_ENDPOINT=http://localhost:${CONTROL_PLANE_PORT} \
AGENT_HOST_NAME=payments-vm-1 \
NODE_AGENT_VERSION=1.1.0 \
NODE_AGENT_CAPABILITIES=otlp,hostmetrics \
bin/enroll-node-agent.sh heartbeat
```

List enrolled agents:

```bash
curl -sS \
  -H "Authorization: Bearer $CONTROL_PLANE_OPERATOR_TOKEN" \
  "http://localhost:${CONTROL_PLANE_PORT}/v1/node-agents?tenant_id=${CONTROL_PLANE_TENANT_ID}"
```

Expected result:

```json
{
  "agent_id": "agent-...",
  "tenant_id": "tenant-a",
  "site_id": "site-1",
  "environment": "production",
  "host_name": "payments-vm-1",
  "status": "healthy",
  "certificate_status": "valid",
  "capabilities": ["otlp", "hostmetrics"]
}
```

## Why This Differentiates The Platform

Many local observability stacks show dashboards once telemetry arrives. The management path adds the operational layer needed to run collectors across hosts:

- Telemetry flow answers: "Where do logs, metrics, and traces go?"
- Management flow answers: "Which agents are trusted, alive, and allowed to send telemetry?"

That distinction keeps application teams focused on emitting OpenTelemetry while operators manage collector identity, lifecycle, and health centrally.
