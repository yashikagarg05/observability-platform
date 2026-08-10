const express = require("express");
const { context, SpanStatusCode, trace } = require("@opentelemetry/api");
const { metrics } = require("@opentelemetry/api");

const serviceName = process.env.OTEL_SERVICE_NAME || process.env.SERVICE_NAME || "orders-api";
const serviceNamespace = process.env.OTEL_SERVICE_NAMESPACE || "demo";
const environment = process.env.OTEL_DEPLOYMENT_ENVIRONMENT || "development";
const serviceVersion = process.env.OTEL_SERVICE_VERSION || process.env.SERVICE_VERSION || "1.0.0";
const port = Number(process.env.PORT || 8080);
const downstreamUrl = process.env.DOWNSTREAM_URL;
const otlpEndpoint = (process.env.OTEL_EXPORTER_OTLP_ENDPOINT || "http://localhost:4318").replace(/\/$/, "");

const tracer = trace.getTracer("reference-app");
const meter = metrics.getMeter("reference-app");

const requestCounter = meter.createCounter("demo_http_requests", {
  description: "Application HTTP requests"
});
const errorCounter = meter.createCounter("demo_http_errors", {
  description: "Application HTTP errors"
});
const durationHistogram = meter.createHistogram("demo_http_request_duration_ms", {
  description: "Application HTTP request duration",
  unit: "ms"
});
const ordersCounter = meter.createCounter("demo_orders_created", {
  description: "Demo orders created"
});
const paymentsCounter = meter.createCounter("demo_payments_processed", {
  description: "Demo payments processed"
});

const app = express();
app.use(express.json());

app.use((req, res, next) => {
  const started = process.hrtime.bigint();
  res.on("finish", () => {
    const durationMs = Number(process.hrtime.bigint() - started) / 1_000_000;
    const attributes = commonAttributes(req, res.statusCode);
    requestCounter.add(1, attributes);
    durationHistogram.record(durationMs, attributes);
    if (res.statusCode >= 500) {
      errorCounter.add(1, attributes);
    }
  });
  next();
});

app.get("/", (req, res) => {
  log("INFO", "Reference application request", { route: "/" });
  res.json({
    service: serviceName,
    namespace: serviceNamespace,
    environment,
    version: serviceVersion
  });
});

app.get("/health", (_req, res) => {
  res.json({ status: "ok", service: serviceName });
});

app.get("/api/orders", async (req, res, next) => {
  tracer.startActiveSpan("orders.create", async (span) => {
    try {
      span.setAttribute("app.order.id", "order-demo-001");
      span.setAttribute("app.customer.tier", "demo");
      log("INFO", "Creating demo order", { route: "/api/orders", order_id: "order-demo-001" });

      let payment = null;
      if (downstreamUrl) {
        payment = await callPaymentService();
        span.setAttribute("app.payment.status", payment.status);
      }

      ordersCounter.add(1, { "service.name": serviceName, "deployment.environment": environment });
      log("INFO", "Demo order created", { route: "/api/orders", order_id: "order-demo-001" });
      res.json({ order_id: "order-demo-001", status: "created", payment });
    } catch (error) {
      span.recordException(error);
      span.setStatus({ code: SpanStatusCode.ERROR, message: error.message });
      next(error);
    } finally {
      span.end();
    }
  });
});

app.get("/api/payments", (_req, res) => {
  tracer.startActiveSpan("payments.authorize", (span) => {
    span.setAttribute("app.payment.provider", "demo-bank");
    paymentsCounter.add(1, { "service.name": serviceName, "deployment.environment": environment });
    log("INFO", "Payment authorized", { route: "/api/payments", payment_id: "payment-demo-001" });
    span.end();
    res.json({ payment_id: "payment-demo-001", status: "authorized" });
  });
});

app.get("/api/error", (_req, _res, next) => {
  tracer.startActiveSpan("orders.intentional_error", (span) => {
    const error = new Error("Intentional demo failure");
    span.setAttribute("app.error.expected", true);
    span.recordException(error);
    span.setStatus({ code: SpanStatusCode.ERROR, message: error.message });
    log("ERROR", "Intentional demo error", { route: "/api/error", error_type: "demo_failure" });
    span.end();
    next(error);
  });
});

app.use((error, req, res, _next) => {
  log("ERROR", error.message, { route: req.path, error_type: error.name });
  res.status(500).json({ error: error.message, service: serviceName });
});

app.listen(port, () => {
  log("INFO", "Reference application started", { port });
  console.log(JSON.stringify({ level: "info", message: "Reference application started", serviceName, port }));
});

async function callPaymentService() {
  const response = await fetch(`${downstreamUrl}/api/payments`);
  if (!response.ok) {
    throw new Error(`payment service failed with ${response.status}`);
  }
  return response.json();
}

function commonAttributes(req, statusCode) {
  return {
    "service.name": serviceName,
    "service.namespace": serviceNamespace,
    "deployment.environment": environment,
    "http.request.method": req.method,
    "http.route": req.route?.path || req.path,
    "http.response.status_code": statusCode
  };
}

function log(severityText, message, attributes = {}) {
  const span = trace.getSpan(context.active());
  const spanContext = span?.spanContext();
  const logAttributes = {
    "service.name": serviceName,
    "service.namespace": serviceNamespace,
    "deployment.environment": environment,
    "service.version": serviceVersion,
    ...attributes
  };

  if (spanContext) {
    logAttributes.trace_id = spanContext.traceId;
    logAttributes.span_id = spanContext.spanId;
  }

  emitOtlpLog(severityText, message, logAttributes, spanContext);

  console.log(
    JSON.stringify({
      timestamp: new Date().toISOString(),
      severity: severityText,
      message,
      trace_id: spanContext?.traceId,
      span_id: spanContext?.spanId,
      service_name: serviceName,
      service: serviceName,
      service_namespace: serviceNamespace,
      deployment_environment: environment,
      ...attributes
    })
  );
}

function emitOtlpLog(severityText, message, attributes, spanContext) {
  const logRecord = {
    timeUnixNano: String(Date.now() * 1_000_000),
    severityText,
    severityNumber: severityText === "ERROR" ? 17 : 9,
    body: {
      stringValue: JSON.stringify({
        message,
        trace_id: spanContext?.traceId,
        span_id: spanContext?.spanId,
        severity: severityText,
        service_name: serviceName,
        service_namespace: serviceNamespace,
        deployment_environment: environment
      })
    },
    attributes: Object.entries(attributes).map(([key, value]) => ({ key, value: otlpValue(value) }))
  };

  if (spanContext) {
    logRecord.traceId = spanContext.traceId;
    logRecord.spanId = spanContext.spanId;
  }

  const body = {
    resourceLogs: [
      {
        resource: {
          attributes: [
            { key: "service.name", value: { stringValue: serviceName } },
            { key: "service.namespace", value: { stringValue: serviceNamespace } },
            { key: "deployment.environment", value: { stringValue: environment } },
            { key: "service.version", value: { stringValue: serviceVersion } }
          ]
        },
        scopeLogs: [
          {
            scope: { name: "reference-app" },
            logRecords: [logRecord]
          }
        ]
      }
    ]
  };

  fetch(`${otlpEndpoint}/v1/logs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  }).catch((error) => {
    console.error(JSON.stringify({ severity: "ERROR", message: "OTLP log export failed", error: error.message }));
  });
}

function otlpValue(value) {
  if (typeof value === "number") return Number.isInteger(value) ? { intValue: String(value) } : { doubleValue: value };
  if (typeof value === "boolean") return { boolValue: value };
  return { stringValue: String(value) };
}
