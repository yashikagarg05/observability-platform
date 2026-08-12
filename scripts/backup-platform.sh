#!/usr/bin/env bash
set -euo pipefail

backup_root=${1:-backups}
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir="$backup_root/platform-$timestamp"
project=${COMPOSE_PROJECT_NAME:-observability-platform}

mkdir -p "$backup_dir/config" "$backup_dir/volumes"

cp -R \
  docker-compose.yml \
  deployments \
  collector/gateway \
  grafana/provisioning \
  grafana/dashboards \
  prometheus \
  loki \
  tempo \
  "$backup_dir/config/"

volumes=(
  grafana-data
  prometheus-data
  loki-data
  tempo-data
  gateway-queue-data
  control-plane-data
)

for volume in "${volumes[@]}"; do
  full_name="${project}_${volume}"
  if docker volume inspect "$full_name" >/dev/null 2>&1; then
    docker run --rm \
      -v "$full_name:/data:ro" \
      -v "$PWD/$backup_dir/volumes:/backup" \
      busybox:1.36@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662 \
      tar -czf "/backup/${volume}.tgz" -C /data .
  else
    echo "Skipping missing volume: $full_name" >&2
  fi
done

cat > "$backup_dir/README.txt" <<EOF
Observability Platform backup created at $timestamp.

This backup contains repository configuration and local Docker volume snapshots.
It is suitable for the single-node production profile only.
It is not a high-availability backup and does not provide point-in-time consistency
for high-write telemetry workloads unless the platform was stopped or quiesced.
EOF

echo "$backup_dir"
