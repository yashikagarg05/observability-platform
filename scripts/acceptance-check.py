#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def get(url: str, headers: dict[str, str] | None = None) -> tuple[int, str]:
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, response.read().decode(errors="ignore")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="ignore")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def prom_query(base_url: str, expression: str) -> int:
    status, body = get(f"{base_url.rstrip('/')}/api/v1/query?{urllib.parse.urlencode({'query': expression})}")
    if status != 200:
        return 0
    return len(json.loads(body).get("data", {}).get("result", []))


def main() -> int:
    control_plane = os.environ.get("CONTROL_PLANE_URL", "http://localhost:8080").rstrip("/")
    prometheus = os.environ.get("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
    grafana = os.environ.get("GRAFANA_URL", "http://localhost:3000").rstrip("/")
    tenant = os.environ.get("CONTROL_PLANE_TENANT_ID", "tenant-a")
    token = os.environ.get("CONTROL_PLANE_OPERATOR_TOKEN", "")
    grafana_user = os.environ.get("GRAFANA_ADMIN_USER", "admin")
    grafana_password = os.environ.get("GRAFANA_ADMIN_PASSWORD", "admin")

    checks: list[tuple[str, bool, str]] = []

    status, _ = get(f"{control_plane}/healthz")
    checks.append(("Control Plane healthz", status == 200, f"status={status}"))

    status, _ = get(f"{control_plane}/v1/overview?tenant_id={tenant}")
    checks.append(("Control Plane rejects unauthenticated overview", status == 403, f"status={status}"))

    status, _ = get(
        f"{control_plane}/v1/overview?tenant_id={tenant}",
        {"authorization": f"Bearer {token}"},
    )
    checks.append(("Control Plane accepts operator token", status == 200, f"status={status}"))

    status, _ = get(f"{prometheus}/-/healthy")
    checks.append(("Prometheus healthy", status == 200, f"status={status}"))

    checks.append(("Gateway self target scraped", prom_query(prometheus, 'up{job="gateway-self"}') > 0, "query=up{job=\"gateway-self\"}"))
    checks.append(("Gateway queue metric present", prom_query(prometheus, "otelcol_exporter_queue_size") > 0, "query=otelcol_exporter_queue_size"))

    auth = base64.b64encode(f"{grafana_user}:{grafana_password}".encode()).decode()
    status, _ = get(f"{grafana}/api/health", {"authorization": f"Basic {auth}"})
    checks.append(("Grafana healthy", status == 200, f"status={status}"))

    status, body = get(f"{grafana}/api/search?query=Platform", {"authorization": f"Basic {auth}"})
    dashboards = json.loads(body) if status == 200 else []
    checks.append(("Platform dashboard available", any(item.get("uid") == "platform-self-monitoring" for item in dashboards), "uid=platform-self-monitoring"))

    failed = False
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name} ({detail})")
        failed = failed or not ok

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
