#!/usr/bin/env bash
set -euo pipefail

version=${1:?usage: verify-node-agent-release.sh <version>}
root=$(cd "$(dirname "$0")/.." && pwd)
name="otel-node-agent-${version}"
release_dir="$root/releases/$version"

for artifact in "$name.tgz" SHA256SUMS manifest.json sbom.json; do
  [[ -f "$release_dir/$artifact" ]] || {
    echo "missing release artifact: $release_dir/$artifact" >&2
    exit 1
  }
done

(
  cd "$release_dir"
  sha256sum --check SHA256SUMS
)
jq -e --arg version "$version" '.nodeAgentVersion == $version' "$release_dir/manifest.json" >/dev/null
jq -e --arg version "$version" '.metadata.component.name == "otel-node-agent" and .metadata.component.version == $version' "$release_dir/sbom.json" >/dev/null
tar -tzf "$release_dir/$name.tgz" | rg -q "^${name}/"
echo "verified preserved release: $version"
