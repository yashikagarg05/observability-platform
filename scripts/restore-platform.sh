#!/usr/bin/env bash
set -euo pipefail

if [[ ${1:-} != "--force" || -z ${2:-} ]]; then
  echo "usage: restore-platform.sh --force <backup-dir>" >&2
  echo "This replaces local Docker volume contents for the single-node production profile." >&2
  exit 2
fi

backup_dir=$2
project=${COMPOSE_PROJECT_NAME:-observability-platform}

[[ -d "$backup_dir/volumes" ]] || { echo "missing backup volumes directory: $backup_dir/volumes" >&2; exit 1; }

volumes=(
  grafana-data
  prometheus-data
  loki-data
  tempo-data
  gateway-queue-data
  control-plane-data
)

for volume in "${volumes[@]}"; do
  archive="$backup_dir/volumes/${volume}.tgz"
  [[ -f "$archive" ]] || { echo "Skipping missing archive: $archive" >&2; continue; }
  full_name="${project}_${volume}"
  docker volume create "$full_name" >/dev/null
  docker run --rm \
    -v "$full_name:/data" \
    -v "$PWD/$backup_dir/volumes:/backup:ro" \
    busybox:1.36@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662 \
    sh -c "rm -rf /data/* /data/..?* /data/.[!.]* 2>/dev/null || true; tar -xzf /backup/${volume}.tgz -C /data"
done

echo "Restore completed from $backup_dir"
