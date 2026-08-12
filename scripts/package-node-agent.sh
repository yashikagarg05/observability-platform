#!/usr/bin/env bash
set -euo pipefail

force=false
if [[ ${1:-} == "--force" ]]; then
  force=true
  shift
fi
version=${1:?usage: package-node-agent.sh [--force] <version>}
root=$(cd "$(dirname "$0")/.." && pwd)
name="otel-node-agent-${version}"
release_dir="$root/releases/$version"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT

if [[ -e "$release_dir" && $force != true ]]; then
  echo "release already exists: $release_dir" >&2
  exit 1
fi

python3 "$root/collector/agent/tools/compose_capabilities.py"
mkdir -p "$stage/$name"
cp "$root/collector/agent/compose.yaml" "$stage/$name/compose.yaml"
cp "$root/collector/agent/.env.example" "$stage/$name/.env.example"
cp "$root/collector/agent/README.md" "$stage/$name/README.md"
cp -R "$root/collector/agent/config" "$stage/$name/config"
cp -R "$root/collector/agent/bin" "$stage/$name/bin"

tar -C "$stage" -czf "$stage/$name.tgz" "$name"
(
  cd "$stage"
  sha256sum "$name.tgz" > SHA256SUMS
)
printf '{"nodeAgentVersion":"%s","collectorImage":"otel/opentelemetry-collector-contrib:0.156.0@sha256:125bdbeb7590cc1952c5b3430ecf14063568980c2c93d5b38676cc0446ed8108","gatewayCompatibility":">=1.0.0 <2.0.0"}\n' "$version" > "$stage/manifest.json"
printf '{"bomFormat":"CycloneDX","specVersion":"1.5","version":1,"metadata":{"component":{"type":"application","name":"otel-node-agent","version":"%s"}},"components":[{"type":"container","name":"otel/opentelemetry-collector-contrib","version":"0.156.0"}]}\n' "$version" > "$stage/sbom.json"

jq -e . "$stage/manifest.json" >/dev/null
jq -e . "$stage/sbom.json" >/dev/null
(
  cd "$stage"
  sha256sum --check SHA256SUMS
)

if [[ -e "$release_dir" ]]; then
  rm -rf "$release_dir"
fi
mkdir -p "$release_dir"
cp "$stage/$name.tgz" "$stage/SHA256SUMS" "$stage/manifest.json" "$stage/sbom.json" "$release_dir/"
