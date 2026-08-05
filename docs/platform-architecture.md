# Observability platform architecture

The platform is organized around telemetry lifecycle, not applications or Collector component names:

```text
Ingestion -> Normalization -> Enrichment -> Routing -> Backends -> Grafana
```

## Gateway

`collector/gateway` is application-agnostic. It accepts OTLP from remote agents and applications, and can optionally collect Docker stdout or generic file paths on its own host.

It normalizes generic JSON, Serilog JSON, and plain-text records into the canonical OpenTelemetry log model, adds only missing identity, then routes:

- logs to Loki over OTLP/HTTP;
- traces to Tempo over OTLP/gRPC;
- OTLP metrics to a Prometheus scrape endpoint.

## Agents

`collector/agents` contains minimal source-host collectors:

- `docker`: reads local Docker JSON log files, unwraps the Docker envelope, and forwards OTLP;
- `file`: tails an explicitly mounted log directory and forwards raw log bodies over OTLP;
- `otlp`: receives local OTLP telemetry and forwards it with batching and retry.

Agents do not parse application schemas. The gateway performs normalization. EOSIM is deployed with the generic file agent by mounting its `/app/logs` Docker volume and supplying service identity through environment variables.

## Deployment boundaries

The gateway cannot read remote host files. Deploy an agent on every remote VM or node that owns Docker logs, application log files, or local OTLP traffic.

TCP 4317 is currently plaintext OTLP/gRPC. Restrict it to trusted source networks and add TLS/mTLS or a private VPN before production rollout.
