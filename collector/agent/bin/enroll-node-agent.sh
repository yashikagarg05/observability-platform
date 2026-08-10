#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
usage:
  enroll-node-agent.sh enroll
  enroll-node-agent.sh renew
  enroll-node-agent.sh heartbeat
  enroll-node-agent.sh request
  enroll-node-agent.sh install

enroll creates a private key and CSR, sends only the CSR to the enrollment API,
and installs the returned certificate and CA bundle.
heartbeat updates this Agent's last_seen_at in the Agent Registry.
renew requests a replacement certificate without overwriting the current
working certificate until the replacement certificate matches the new key and
expected Agent identity.
request creates a private key and CSR for this Node Agent.
install installs a signed client certificate and CA bundle.

Required for enroll:
  NODE_AGENT_ENROLLMENT_ENDPOINT
  NODE_AGENT_ENROLLMENT_CREDENTIAL

Required for heartbeat:
  NODE_AGENT_ENROLLMENT_ENDPOINT

Required for renew:
  NODE_AGENT_ENROLLMENT_ENDPOINT
  NODE_AGENT_RENEWAL_CREDENTIAL

Required for request:
  NODE_AGENT_AGENT_ID
  NODE_AGENT_TENANT_ID
  NODE_AGENT_SITE_ID
  NODE_AGENT_ENVIRONMENT

Optional for request:
  NODE_AGENT_IDENTITY_DOMAIN=observability.local
  NODE_AGENT_SECRET_DIR=/etc/otel-node-agent/secrets
  NODE_AGENT_CERT_DIR=/etc/otel-node-agent/certs

Required for install:
  NODE_AGENT_SIGNED_CERT=/path/to/client.crt
  NODE_AGENT_CA_BUNDLE=/path/to/ca-bundle.pem
EOF
}

mode=${1:-}
if [[ -z "$mode" || "$mode" == "-h" || "$mode" == "--help" ]]; then
  usage
  exit 0
fi

secret_dir=${NODE_AGENT_SECRET_DIR:-/etc/otel-node-agent/secrets}
cert_dir=${NODE_AGENT_CERT_DIR:-/etc/otel-node-agent/certs}
key_file="$secret_dir/client.key"
csr_file="$cert_dir/client.csr"
cert_file="$cert_dir/client.crt"
ca_file="$cert_dir/ca-bundle.pem"
identity_file="$cert_dir/agent-identity.uri"
agent_id_file="$cert_dir/agent-id"

case "$mode" in
  enroll)
    : "${NODE_AGENT_ENROLLMENT_ENDPOINT:?set NODE_AGENT_ENROLLMENT_ENDPOINT}"
    : "${NODE_AGENT_ENROLLMENT_CREDENTIAL:?set NODE_AGENT_ENROLLMENT_CREDENTIAL}"
    csr_config="$cert_dir/client-enrollment-csr.openssl.cnf"
    response_file="$cert_dir/enrollment-response.json"

    install -d -m 0700 "$secret_dir"
    install -d -m 0755 "$cert_dir"

    if [[ ! -f "$key_file" ]]; then
      openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$key_file"
      chmod 0600 "$key_file"
    fi

    cat > "$csr_config" <<'EOF'
[ req ]
prompt = no
distinguished_name = dn
req_extensions = v3_node_agent_client_csr

[ dn ]
O = Observability Platform
CN = pending-node-agent

[ v3_node_agent_client_csr ]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = clientAuth
EOF

    openssl req -new -key "$key_file" -out "$csr_file" -config "$csr_config"

    NODE_AGENT_ENROLLMENT_ENDPOINT="$NODE_AGENT_ENROLLMENT_ENDPOINT" \
    NODE_AGENT_ENROLLMENT_CREDENTIAL="$NODE_AGENT_ENROLLMENT_CREDENTIAL" \
    CSR_FILE="$csr_file" \
    RESPONSE_FILE="$response_file" \
    python3 - <<'PY'
import json
import os
import urllib.error
import urllib.request

endpoint = os.environ["NODE_AGENT_ENROLLMENT_ENDPOINT"].rstrip("/") + "/v1/node-agents/enroll"
credential = os.environ["NODE_AGENT_ENROLLMENT_CREDENTIAL"]
csr_pem = open(os.environ["CSR_FILE"], encoding="utf-8").read()
body = json.dumps({"csr_pem": csr_pem}).encode()
request = urllib.request.Request(
    endpoint,
    data=body,
    headers={
        "authorization": f"Bearer {credential}",
        "content-type": "application/json",
    },
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
except urllib.error.HTTPError as exc:
    raise SystemExit(f"enrollment failed: HTTP {exc.code} {exc.reason}") from exc
open(os.environ["RESPONSE_FILE"], "wb").write(payload)
PY

    RESPONSE_FILE="$response_file" CERT_FILE="$cert_file" CA_FILE="$ca_file" IDENTITY_FILE="$identity_file" python3 - <<'PY'
import json
import os
from pathlib import Path

response = json.loads(Path(os.environ["RESPONSE_FILE"]).read_text())
Path(os.environ["CERT_FILE"]).write_text(response["certificate_pem"])
Path(os.environ["CA_FILE"]).write_text(response["ca_bundle_pem"])
Path(os.environ["IDENTITY_FILE"]).write_text(response["agent_uri"] + "\n")
Path(os.environ["IDENTITY_FILE"]).with_name("agent-id").write_text(response["agent_id"] + "\n")
print(f"Installed {os.environ['CERT_FILE']}")
print(f"Installed {os.environ['CA_FILE']}")
print(f"Agent ID: {response['agent_id']}")
print(f"Agent identity: {response['agent_uri']}")
PY
    chmod 0600 "$key_file"
    chmod 0644 "$cert_file" "$ca_file" "$identity_file"
    chmod 0644 "$agent_id_file"
    echo "Private key remained local at $key_file"
    ;;
  heartbeat)
    : "${NODE_AGENT_ENROLLMENT_ENDPOINT:?set NODE_AGENT_ENROLLMENT_ENDPOINT}"
    [[ -f "$identity_file" ]] || { echo "missing identity file: $identity_file" >&2; exit 2; }
    [[ -f "$agent_id_file" ]] || { echo "missing agent id file: $agent_id_file" >&2; exit 2; }
    NODE_AGENT_ENROLLMENT_ENDPOINT="$NODE_AGENT_ENROLLMENT_ENDPOINT" \
    IDENTITY_FILE="$identity_file" \
    AGENT_ID_FILE="$agent_id_file" \
    AGENT_HOST_NAME="${AGENT_HOST_NAME:-${HOSTNAME:-unknown}}" \
    NODE_AGENT_VERSION="${NODE_AGENT_VERSION:-unknown}" \
    NODE_AGENT_CAPABILITIES="${NODE_AGENT_CAPABILITIES:-}" \
    python3 - <<'PY'
import json
import os
import urllib.request

identity = open(os.environ["IDENTITY_FILE"], encoding="utf-8").read().strip()
agent_id = open(os.environ["AGENT_ID_FILE"], encoding="utf-8").read().strip()
parts = [part for part in identity.split("/", 3)[3].split("/") if part]
identity_values = dict(zip(parts[0::2], parts[1::2]))
capabilities = [item for item in os.environ["NODE_AGENT_CAPABILITIES"].split(",") if item]
payload = {
    "tenant_id": identity_values["tenant"],
    "host_name": os.environ["AGENT_HOST_NAME"],
    "agent_version": os.environ["NODE_AGENT_VERSION"],
    "capabilities": capabilities,
}
endpoint = os.environ["NODE_AGENT_ENROLLMENT_ENDPOINT"].rstrip("/") + f"/v1/node-agents/{agent_id}/heartbeat"
request = urllib.request.Request(
    endpoint,
    data=json.dumps(payload).encode(),
    headers={"content-type": "application/json", "x-tenant-id": identity_values["tenant"]},
    method="POST",
)
with urllib.request.urlopen(request, timeout=30) as response:
    body = json.loads(response.read())
print(f"Heartbeat accepted for {body['agent_id']} with status {body['status']}")
PY
    ;;
  renew)
    : "${NODE_AGENT_ENROLLMENT_ENDPOINT:?set NODE_AGENT_ENROLLMENT_ENDPOINT}"
    : "${NODE_AGENT_RENEWAL_CREDENTIAL:?set NODE_AGENT_RENEWAL_CREDENTIAL}"
    [[ -f "$identity_file" ]] || { echo "missing identity file: $identity_file" >&2; exit 2; }
    [[ -f "$agent_id_file" ]] || { echo "missing agent id file: $agent_id_file" >&2; exit 2; }

    install -d -m 0700 "$secret_dir"
    install -d -m 0755 "$cert_dir"

    renewal_key="$secret_dir/client.key.renewal"
    renewal_csr="$cert_dir/client.csr.renewal"
    renewal_cert="$cert_dir/client.crt.renewal"
    renewal_ca="$cert_dir/ca-bundle.pem.renewal"
    renewal_response="$cert_dir/renewal-response.json"
    renewal_config="$cert_dir/client-renewal-csr.openssl.cnf"

    agent_uri=$(tr -d '\n' < "$identity_file")
    agent_id=$(tr -d '\n' < "$agent_id_file")

    openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$renewal_key"
    chmod 0600 "$renewal_key"

    cat > "$renewal_config" <<EOF
[ req ]
prompt = no
distinguished_name = dn
req_extensions = v3_node_agent_client_csr

[ dn ]
O = Observability Platform
CN = ${agent_id}

[ v3_node_agent_client_csr ]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = clientAuth
subjectAltName = @agent_alt_names

[ agent_alt_names ]
URI.1 = ${agent_uri}
EOF

    openssl req -new -key "$renewal_key" -out "$renewal_csr" -config "$renewal_config"

    NODE_AGENT_ENROLLMENT_ENDPOINT="$NODE_AGENT_ENROLLMENT_ENDPOINT" \
    NODE_AGENT_RENEWAL_CREDENTIAL="$NODE_AGENT_RENEWAL_CREDENTIAL" \
    AGENT_ID="$agent_id" \
    CSR_FILE="$renewal_csr" \
    RESPONSE_FILE="$renewal_response" \
    python3 - <<'PY'
import json
import os
import urllib.error
import urllib.request

endpoint = os.environ["NODE_AGENT_ENROLLMENT_ENDPOINT"].rstrip("/") + f"/v1/node-agents/{os.environ['AGENT_ID']}/renew"
credential = os.environ["NODE_AGENT_RENEWAL_CREDENTIAL"]
csr_pem = open(os.environ["CSR_FILE"], encoding="utf-8").read()
body = json.dumps({"csr_pem": csr_pem}).encode()
request = urllib.request.Request(
    endpoint,
    data=body,
    headers={"authorization": f"Bearer {credential}", "content-type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
except urllib.error.HTTPError as exc:
    raise SystemExit(f"renewal failed: HTTP {exc.code} {exc.reason}") from exc
open(os.environ["RESPONSE_FILE"], "wb").write(payload)
PY

    RESPONSE_FILE="$renewal_response" RENEWAL_CERT="$renewal_cert" RENEWAL_CA="$renewal_ca" python3 - <<'PY'
import json
import os
from pathlib import Path

response = json.loads(Path(os.environ["RESPONSE_FILE"]).read_text())
Path(os.environ["RENEWAL_CERT"]).write_text(response["certificate_pem"])
Path(os.environ["RENEWAL_CA"]).write_text(response["ca_bundle_pem"])
print(f"Received renewed certificate for {response['agent_id']}")
PY

    cert_modulus=$(openssl x509 -noout -modulus -in "$renewal_cert" | openssl sha256)
    key_modulus=$(openssl rsa -noout -modulus -in "$renewal_key" 2>/dev/null | openssl sha256)
    [[ "$cert_modulus" == "$key_modulus" ]] || { echo "renewed certificate does not match renewal private key" >&2; exit 1; }
    openssl x509 -in "$renewal_cert" -noout -text | grep -F "URI:${agent_uri}" >/dev/null || {
      echo "renewed certificate does not contain expected Agent URI SAN" >&2
      exit 1
    }

    if [[ -f "$key_file" ]]; then cp "$key_file" "$key_file.previous"; chmod 0600 "$key_file.previous"; fi
    if [[ -f "$cert_file" ]]; then cp "$cert_file" "$cert_file.previous"; chmod 0644 "$cert_file.previous"; fi
    install -m 0600 "$renewal_key" "$key_file"
    install -m 0644 "$renewal_cert" "$cert_file"
    install -m 0644 "$renewal_ca" "$ca_file"
    rm -f "$renewal_key" "$renewal_csr" "$renewal_cert" "$renewal_ca"
    echo "Renewed certificate installed at $cert_file"
    echo "Previous working certificate and key preserved with .previous suffix"
    echo "Private key remained local at $key_file"
    ;;
  request)
    : "${NODE_AGENT_AGENT_ID:?set NODE_AGENT_AGENT_ID}"
    : "${NODE_AGENT_TENANT_ID:?set NODE_AGENT_TENANT_ID}"
    : "${NODE_AGENT_SITE_ID:?set NODE_AGENT_SITE_ID}"
    : "${NODE_AGENT_ENVIRONMENT:?set NODE_AGENT_ENVIRONMENT}"
    site_id=${NODE_AGENT_SITE_ID}
    environment=${NODE_AGENT_ENVIRONMENT}
    identity_domain=${NODE_AGENT_IDENTITY_DOMAIN:-observability.local}
    agent_uri="spiffe://${identity_domain}/tenant/${NODE_AGENT_TENANT_ID}/site/${site_id}/environment/${environment}/agent/${NODE_AGENT_AGENT_ID}"
    csr_config="$cert_dir/client-csr.openssl.cnf"

    install -d -m 0700 "$secret_dir"
    install -d -m 0755 "$cert_dir"

    if [[ ! -f "$key_file" ]]; then
      openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$key_file"
      chmod 0600 "$key_file"
    fi

    cat > "$csr_config" <<EOF
[ req ]
prompt = no
distinguished_name = dn
req_extensions = v3_node_agent_client_csr

[ dn ]
O = Observability Platform
CN = ${NODE_AGENT_AGENT_ID}

[ v3_node_agent_client_csr ]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = clientAuth
subjectAltName = @agent_alt_names

[ agent_alt_names ]
URI.1 = ${agent_uri}
EOF

    openssl req -new -key "$key_file" -out "$csr_file" -config "$csr_config"
    printf '%s\n' "$agent_uri" > "$identity_file"

    echo "CSR written to $csr_file"
    echo "Agent identity: $agent_uri"
    ;;
  install)
    : "${NODE_AGENT_SIGNED_CERT:?set NODE_AGENT_SIGNED_CERT}"
    : "${NODE_AGENT_CA_BUNDLE:?set NODE_AGENT_CA_BUNDLE}"

    install -d -m 0700 "$secret_dir"
    install -d -m 0755 "$cert_dir"
    install -m 0644 "$NODE_AGENT_SIGNED_CERT" "$cert_file"
    install -m 0644 "$NODE_AGENT_CA_BUNDLE" "$ca_file"

    if [[ -f "$key_file" ]]; then
      chmod 0600 "$key_file"
    fi

    echo "Installed $cert_file"
    echo "Installed $ca_file"
    ;;
  *)
    usage
    exit 2
    ;;
esac
