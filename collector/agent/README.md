# OpenTelemetry Node Agent

The Node Agent is the single source-host Collector deployment. It knows local telemetry sources and exports only OTLP to the central Gateway. It has no Loki, Tempo, Prometheus, or Grafana configuration.

## Source profiles

- `config/compose/otlp.yaml`: local OTLP logs, traces, and metrics.
- `config/compose/docker.yaml`: Docker `json-file` stdout/stderr logs.
- `config/compose/docker-file.yaml`: Docker logs plus one explicitly mounted application log directory.

Host metrics and Prometheus receiver modules are packaged but intentionally inactive, preserving the existing Node Exporter to Prometheus path.

## Deploy

```bash
cp .env.example .env
# Select one profile; for example, Docker logs:
docker compose -f compose.yaml -f config/compose/docker.yaml up -d
```

The OTLP profile publishes local intake ports. Docker and file-only profiles do not publish ports or mount unrelated sources. Do not run this alongside another reader for the same source paths.

The distributable archive contains only `compose.yaml`, `config/`, `.env.example`, and this README.

## Capability model

Capabilities are reusable release-author building blocks: `otlp`, `docker`, `filelog`, `hostmetrics`, and `prometheus`. Profiles are the supported operator-facing combinations.

The current profiles are:

- `otlp`: `otlp`
- `docker`: `otlp` + `docker`
- `docker-file`: `otlp` + `docker` + `filelog`

`hostmetrics` and `prometheus` are present as disabled capabilities; they have no supported profile yet. Generated configs are in `config/generated/`, while `config/profiles/` remains as the V1 compatibility layer.
