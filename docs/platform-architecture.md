# Observability platform architecture

`Node Agent -> OTLP -> Gateway -> Loki, Tempo, Prometheus -> Grafana`

## Deployment model

The Node Agent package is the supported source-host deployment model. During staged migrations, existing gateway-local Docker/file receivers and legacy agent packages may remain active until each node has been migrated and verified. Do not run a legacy source reader and Node Agent source reader against the same paths at the same time.

## Node Agent

`collector/agent` is the single source-host deployment. It collects local Docker stdout, explicitly mounted files, local OTLP telemetry, and optional hostmetrics, then exports OTLP/gRPC only to the gateway. It contains no backend configuration. Its Prometheus receiver module is packaged but inactive, preserving backend routing ownership in the gateway.

The current plaintext OTLP/gRPC transport remains available for migration. mTLS is implemented as an opt-in transport variant using generated `-mtls` Node Agent configs and the Gateway `config-mtls.yaml` migration listener; it does not change source capabilities or backend routing.

## Gateway

The Gateway is now OTLP-only. It receives OTLP, then normalizes, enriches, batches, and routes telemetry without Docker socket, container-log, or local-file mounts.

## Rollback

The prior Gateway Docker and local-file receiver fragments remain under `collector/gateway/config/receivers/`. To roll back one source, stop the matching Node Agent profile, restore only that receiver in `collector/gateway/config.yaml` and `collector/gateway/config/service/logs.yaml`, restore any required host mount in `docker-compose.yml`, and recreate the Gateway Collector.
