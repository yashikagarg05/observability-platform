#!/usr/bin/env bash
set -euo pipefail

out_dir=${1:-dev-mtls}
gateway_dns=${GATEWAY_DNS:-localhost}
agent_id=${NODE_AGENT_AGENT_ID:-dev-agent-01}
tenant_id=${NODE_AGENT_TENANT_ID:-dev-tenant}
site_id=${NODE_AGENT_SITE_ID:-dev-site}
environment=${NODE_AGENT_ENVIRONMENT:-development}
identity_domain=${NODE_AGENT_IDENTITY_DOMAIN:-observability.local}
agent_uri="spiffe://${identity_domain}/tenant/${tenant_id}/site/${site_id}/environment/${environment}/agent/${agent_id}"
root=$(cd "$(dirname "$0")/.." && pwd)

root_dir="$out_dir/ca"
templates="$root/pki/templates"
gateway_certs="$out_dir/gateway/certs"
gateway_secrets="$out_dir/gateway/secrets"
agent_certs="$out_dir/agent/certs"
agent_secrets="$out_dir/agent/secrets"

mkdir -p "$root_dir" "$gateway_certs" "$gateway_secrets" "$agent_certs" "$agent_secrets"
chmod 0700 "$gateway_secrets" "$agent_secrets"

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$root_dir/dev-root-ca.key"
openssl req -x509 -new -nodes -key "$root_dir/dev-root-ca.key" -sha256 -days 3650 \
  -config "$templates/root-ca.openssl.cnf" \
  -extensions v3_root_ca \
  -out "$root_dir/dev-root-ca.pem"

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$root_dir/dev-gateway-intermediate-ca.key"
openssl req -new -key "$root_dir/dev-gateway-intermediate-ca.key" \
  -config "$templates/gateway-server-intermediate.openssl.cnf" \
  -out "$root_dir/dev-gateway-intermediate-ca.csr"
openssl x509 -req -in "$root_dir/dev-gateway-intermediate-ca.csr" \
  -CA "$root_dir/dev-root-ca.pem" -CAkey "$root_dir/dev-root-ca.key" -CAcreateserial \
  -out "$root_dir/dev-gateway-intermediate-ca.pem" -days 1095 -sha256 \
  -extfile "$templates/gateway-server-intermediate.openssl.cnf" \
  -extensions v3_gateway_server_intermediate_ca

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$root_dir/dev-agent-intermediate-ca.key"
openssl req -new -key "$root_dir/dev-agent-intermediate-ca.key" \
  -config "$templates/agent-client-intermediate.openssl.cnf" \
  -out "$root_dir/dev-agent-intermediate-ca.csr"
openssl x509 -req -in "$root_dir/dev-agent-intermediate-ca.csr" \
  -CA "$root_dir/dev-root-ca.pem" -CAkey "$root_dir/dev-root-ca.key" -CAcreateserial \
  -out "$root_dir/dev-agent-intermediate-ca.pem" -days 730 -sha256 \
  -extfile "$templates/agent-client-intermediate.openssl.cnf" \
  -extensions v3_agent_client_intermediate_ca

gateway_ext="$out_dir/gateway-server.ext.cnf"
cat > "$gateway_ext" <<EOF
[ v3_gateway_server ]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
subjectAltName = @gateway_alt_names

[ gateway_alt_names ]
DNS.1 = ${gateway_dns}
DNS.2 = otel-collector
DNS.3 = localhost
IP.1 = 127.0.0.1
EOF

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$gateway_secrets/gateway.key"
openssl req -new -key "$gateway_secrets/gateway.key" -subj "/CN=${gateway_dns}" \
  -addext "subjectAltName=DNS:${gateway_dns},DNS:otel-collector,DNS:localhost,IP:127.0.0.1" \
  -out "$gateway_certs/gateway.csr"
openssl x509 -req -in "$gateway_certs/gateway.csr" \
  -CA "$root_dir/dev-gateway-intermediate-ca.pem" -CAkey "$root_dir/dev-gateway-intermediate-ca.key" \
  -CAcreateserial -out "$gateway_certs/gateway.crt" -days 180 -sha256 \
  -extfile "$gateway_ext" -extensions v3_gateway_server

agent_ext="$out_dir/node-agent-client.ext.cnf"
cat > "$agent_ext" <<EOF
[ v3_node_agent_client ]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = clientAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
subjectAltName = @agent_alt_names

[ agent_alt_names ]
URI.1 = ${agent_uri}
EOF

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$agent_secrets/client.key"
openssl req -new -key "$agent_secrets/client.key" -subj "/CN=${agent_id}" \
  -addext "subjectAltName=URI:${agent_uri}" \
  -out "$agent_certs/client.csr"
openssl x509 -req -in "$agent_certs/client.csr" \
  -CA "$root_dir/dev-agent-intermediate-ca.pem" -CAkey "$root_dir/dev-agent-intermediate-ca.key" \
  -CAcreateserial -out "$agent_certs/client.crt" -days 60 -sha256 \
  -extfile "$agent_ext" -extensions v3_node_agent_client

cat "$root_dir/dev-gateway-intermediate-ca.pem" "$root_dir/dev-root-ca.pem" > "$agent_certs/ca-bundle.pem"
cat "$root_dir/dev-agent-intermediate-ca.pem" "$root_dir/dev-root-ca.pem" > "$gateway_certs/agent-ca-bundle.pem"
cat "$root_dir/dev-gateway-intermediate-ca.pem" "$root_dir/dev-root-ca.pem" > "$gateway_certs/gateway-ca-bundle.pem"
chmod 0600 "$root_dir"/*.key "$gateway_secrets/gateway.key" "$agent_secrets/client.key"
chmod 0644 "$root_dir"/*.pem "$gateway_certs/gateway.crt" "$gateway_certs/agent-ca-bundle.pem" "$gateway_certs/gateway-ca-bundle.pem" "$agent_certs/client.crt" "$agent_certs/ca-bundle.pem"

cat <<EOF
Development mTLS material written under $out_dir

Gateway:
  GATEWAY_CERTS_HOST_PATH=$(cd "$gateway_certs" && pwd)
  GATEWAY_SECRETS_HOST_PATH=$(cd "$gateway_secrets" && pwd)

Node Agent:
  NODE_AGENT_CERTS_HOST_PATH=$(cd "$agent_certs" && pwd)
  NODE_AGENT_SECRETS_HOST_PATH=$(cd "$agent_secrets" && pwd)
  NODE_AGENT_TRANSPORT_SUFFIX=-mtls
  GATEWAY_OTLP_GRPC_ENDPOINT=${gateway_dns}:4319

Agent identity:
  ${agent_uri}
EOF
