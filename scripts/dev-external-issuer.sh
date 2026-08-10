#!/usr/bin/env bash
set -euo pipefail

# Development-only external issuer shim.
# This exercises the production issuer boundary with throwaway CA material.
# Do not use this script as a production CA integration.

: "${ENROLLMENT_CSR_FILE:?set ENROLLMENT_CSR_FILE}"
: "${ENROLLMENT_CERTIFICATE_FILE:?set ENROLLMENT_CERTIFICATE_FILE}"
: "${ENROLLMENT_AGENT_URI:?set ENROLLMENT_AGENT_URI}"
: "${ENROLLMENT_DEVELOPMENT_AGENT_CA_CERT:?set ENROLLMENT_DEVELOPMENT_AGENT_CA_CERT}"
: "${ENROLLMENT_DEVELOPMENT_AGENT_CA_KEY:?set ENROLLMENT_DEVELOPMENT_AGENT_CA_KEY}"

days=${ENROLLMENT_AGENT_CERT_DAYS:-60}
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

ext_file="$tmp_dir/client.ext.cnf"
cat > "$ext_file" <<EOF
[ v3_node_agent_client ]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = clientAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
subjectAltName = @agent_alt_names

[ agent_alt_names ]
URI.1 = ${ENROLLMENT_AGENT_URI}
EOF

serial="0x$(python3 - <<'PY'
import uuid
print(uuid.uuid4().hex)
PY
)"

openssl x509 -req \
  -in "$ENROLLMENT_CSR_FILE" \
  -CA "$ENROLLMENT_DEVELOPMENT_AGENT_CA_CERT" \
  -CAkey "$ENROLLMENT_DEVELOPMENT_AGENT_CA_KEY" \
  -set_serial "$serial" \
  -out "$ENROLLMENT_CERTIFICATE_FILE" \
  -days "$days" \
  -sha256 \
  -extfile "$ext_file" \
  -extensions v3_node_agent_client >/dev/null 2>&1
