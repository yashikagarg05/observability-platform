#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
usage:
  verify-mtls-cert-profile.sh --type agent|gateway --cert FILE --ca FILE [options]

options:
  --key FILE            Verify private key matches certificate.
  --expected-uri URI    Required URI SAN for agent certificates.
  --expected-dns DNS    Required DNS SAN for gateway certificates.
  --min-days DAYS       Require certificate to be valid for at least DAYS. Default: 1.
EOF
}

type=
cert=
ca=
key=
expected_uri=
expected_dns=
min_days=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --type) type=${2:?}; shift 2 ;;
    --cert) cert=${2:?}; shift 2 ;;
    --ca) ca=${2:?}; shift 2 ;;
    --key) key=${2:?}; shift 2 ;;
    --expected-uri) expected_uri=${2:?}; shift 2 ;;
    --expected-dns) expected_dns=${2:?}; shift 2 ;;
    --min-days) min_days=${2:?}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

[[ "$type" == "agent" || "$type" == "gateway" ]] || { usage; exit 2; }
[[ -f "$cert" ]] || { echo "missing cert: $cert" >&2; exit 2; }
[[ -f "$ca" ]] || { echo "missing CA bundle: $ca" >&2; exit 2; }

openssl verify -CAfile "$ca" "$cert" >/dev/null
openssl x509 -checkend "$((min_days * 86400))" -noout -in "$cert" >/dev/null

text=$(openssl x509 -noout -text -in "$cert")

require_text() {
  local needle=$1
  local message=$2
  if [[ "$text" != *"$needle"* ]]; then
    echo "$message" >&2
    exit 1
  fi
}

require_text "CA:FALSE" "certificate must be a leaf certificate with CA:FALSE"
require_text "Digital Signature" "certificate must allow Digital Signature"
require_text "Key Encipherment" "certificate must allow Key Encipherment for RSA compatibility"

case "$type" in
  agent)
    require_text "TLS Web Client Authentication" "agent certificate must have clientAuth EKU"
    [[ -n "$expected_uri" ]] || { echo "--expected-uri is required for agent certificates" >&2; exit 2; }
    require_text "URI:$expected_uri" "agent certificate missing expected URI SAN: $expected_uri"
    ;;
  gateway)
    require_text "TLS Web Server Authentication" "gateway certificate must have serverAuth EKU"
    [[ -n "$expected_dns" ]] || { echo "--expected-dns is required for gateway certificates" >&2; exit 2; }
    require_text "DNS:$expected_dns" "gateway certificate missing expected DNS SAN: $expected_dns"
    ;;
esac

if [[ -n "$key" ]]; then
  [[ -f "$key" ]] || { echo "missing key: $key" >&2; exit 2; }
  cert_pub=$(openssl x509 -pubkey -noout -in "$cert" | openssl pkey -pubin -outform DER | sha256sum | awk '{print $1}')
  key_pub=$(openssl pkey -pubout -in "$key" | openssl pkey -pubin -outform DER | sha256sum | awk '{print $1}')
  if [[ "$cert_pub" != "$key_pub" ]]; then
    echo "private key does not match certificate" >&2
    exit 1
  fi
fi

echo "verified $type certificate: $cert"
