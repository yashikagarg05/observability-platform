# Visual Assets

This directory stores checked-in documentation visuals.

Current assets:

- `observability-platform-overview.svg`: architecture overview used by the README.

## Screenshot Checklist

Before the next public release, capture optimized PNG or WebP screenshots for:

1. `application-observability-reference`: Grafana dashboard after demo traffic.
2. `log-trace-correlation`: Grafana Explore showing a Loki log with a trace link.
3. `orders-payment-trace`: Tempo trace showing `orders-api` calling `payment-api`.
4. `platform-management-console`: Console overview or enrollment workflow from the production-style profile.

Guidelines:

- Avoid secrets, tokens, private hostnames, and personal data.
- Prefer a clean local demo tenant such as `demo-tenant`.
- Keep files reasonably small for GitHub rendering.
- Use stable filenames so README links do not churn.
