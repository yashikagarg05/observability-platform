# Visual Assets

This directory stores checked-in documentation visuals.

Current assets:

- `application-dashboard.png`: Grafana dashboard after demo traffic.
- `application-logs.png`: Grafana Explore showing Loki application logs.
- `application-metrics.png`: Grafana Explore showing Prometheus application metrics.
- `application-trace.png`: Grafana Explore showing Tempo application traces.
- `management-control-plane.svg`: optional management and agent lifecycle overview used by the README.
- `observability-platform-overview.svg`: architecture overview used by the README.

## Screenshot Checklist

Before the next public release, capture optimized PNG or WebP screenshots for:

1. `application-dashboard.png`: Grafana dashboard after demo traffic.
2. `application-logs.png`: Grafana Explore showing Loki application logs.
3. `application-metrics.png`: Grafana Explore showing Prometheus application metrics.
4. `application-trace.png`: Grafana Explore showing Tempo application traces.
5. `management-agent-lifecycle.png`: Console enrollment, healthy agent registry state, or both from the production-style profile.

Guidelines:

- Avoid secrets, tokens, private hostnames, and personal data.
- Prefer a clean local demo tenant such as `demo-tenant`.
- Keep files reasonably small for GitHub rendering.
- Use stable filenames so README links do not churn.
