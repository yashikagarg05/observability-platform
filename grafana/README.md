# Grafana observability artifact

Release Grafana provisioning and dashboard JSON as `grafana-observability/vX.Y.Z`.

Dashboards must use the stable provisioned datasource UIDs: `loki`, `tempo`, and `prometheus`. The Compose deployment mounts `provisioning/` and `dashboards/` read-only into Grafana.
