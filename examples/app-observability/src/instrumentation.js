const { getNodeAutoInstrumentations } = require("@opentelemetry/auto-instrumentations-node");
const { OTLPMetricExporter } = require("@opentelemetry/exporter-metrics-otlp-http");
const { OTLPTraceExporter } = require("@opentelemetry/exporter-trace-otlp-http");
const { resourceFromAttributes } = require("@opentelemetry/resources");
const { PeriodicExportingMetricReader } = require("@opentelemetry/sdk-metrics");
const { NodeSDK } = require("@opentelemetry/sdk-node");

const serviceName = process.env.OTEL_SERVICE_NAME || process.env.SERVICE_NAME || "orders-api";
const serviceNamespace = process.env.OTEL_SERVICE_NAMESPACE || "demo";
const deploymentEnvironment = process.env.OTEL_DEPLOYMENT_ENVIRONMENT || "development";
const serviceVersion = process.env.OTEL_SERVICE_VERSION || process.env.SERVICE_VERSION || "1.0.0";
const otlpEndpoint = (process.env.OTEL_EXPORTER_OTLP_ENDPOINT || "http://localhost:4318").replace(/\/$/, "");

const resource = resourceFromAttributes({
  "service.name": serviceName,
  "service.namespace": serviceNamespace,
  "deployment.environment": deploymentEnvironment,
  "service.version": serviceVersion
});

const sdk = new NodeSDK({
  resource,
  traceExporter: new OTLPTraceExporter({ url: `${otlpEndpoint}/v1/traces` }),
  metricReader: new PeriodicExportingMetricReader({
    exporter: new OTLPMetricExporter({ url: `${otlpEndpoint}/v1/metrics` }),
    exportIntervalMillis: 5000
  }),
  instrumentations: [
    getNodeAutoInstrumentations({
      "@opentelemetry/instrumentation-fs": { enabled: false }
    })
  ]
});

sdk.start();

process.on("SIGTERM", () => {
  sdk.shutdown().finally(() => process.exit(0));
});
