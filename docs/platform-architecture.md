# Observability platform architecture

`Node Agent -> OTLP -> Gateway -> Loki, Tempo, Prometheus -> Grafana`

## Migration status

The Node Agent package is ready for staged deployment. Existing gateway-local Docker/file receivers and legacy agent packages remain active until each node has been migrated and verified. Do not run a legacy source reader and Node Agent source reader against the same paths at the same time.

## Node Agent

`collector/agent` is the future single source-host deployment. It collects local Docker stdout, explicitly mounted files, and local OTLP telemetry, then exports OTLP/gRPC only to the gateway. It contains no backend configuration. Its hostmetrics and Prometheus modules are packaged but inactive, preserving the current Node Exporter to Prometheus path.

## Gateway

The Gateway is now OTLP-only. It receives OTLP, then normalizes, enriches, batches, and routes telemetry without Docker socket, container-log, or local-file mounts.

## Rollback

The prior Gateway Docker and local-file receiver fragments remain under `collector/gateway/config/receivers/`. To roll back one source, stop the matching Node Agent profile, restore only that receiver in `collector/gateway/config.yaml` and `collector/gateway/config/service/logs.yaml`, restore any required host mount in `docker-compose.yml`, and recreate the Gateway Collector.
