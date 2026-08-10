#!/usr/bin/env bash
set -euo pipefail

cert_file=${NODE_AGENT_TLS_CERT_FILE:-/etc/otel-node-agent/certs/client.crt}
renewal_days=${NODE_AGENT_CERT_RENEWAL_DAYS:-20}

if [[ ! -f "$cert_file" ]]; then
  echo "missing certificate: $cert_file" >&2
  exit 2
fi

if openssl x509 -checkend "$((renewal_days * 86400))" -noout -in "$cert_file" >/dev/null; then
  openssl x509 -enddate -noout -in "$cert_file"
  echo "certificate is outside the renewal window"
  exit 0
fi

openssl x509 -enddate -noout -in "$cert_file"
echo "certificate is inside the renewal window"
exit 1
