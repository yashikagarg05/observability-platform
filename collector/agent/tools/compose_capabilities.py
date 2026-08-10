#!/usr/bin/env python3
"""Generate immutable Collector configs from capability profile manifests."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "config"
PROFILES = ROOT / "profile-manifests"
OUTPUT = ROOT / "generated"
KNOWN_CAPABILITIES = {"otlp", "docker", "filelog", "hostmetrics", "prometheus"}


def generate(name: str, exporter: str = "gateway") -> str:
    manifest = json.loads((PROFILES / f"{name}.json").read_text())
    capabilities = manifest["capabilities"]
    unknown = set(capabilities) - KNOWN_CAPABILITIES
    if unknown or len(capabilities) != len(set(capabilities)):
        raise ValueError(f"invalid capabilities for {name}: {unknown}")
    if "otlp" not in capabilities:
        raise ValueError(f"{name} must include otlp")

    docker = "docker" in capabilities
    filelog = "filelog" in capabilities
    hostmetrics = "hostmetrics" in capabilities
    prometheus = "prometheus" in capabilities

    extensions = [
        "  file_storage/queue:",
        "    directory: /var/lib/otelcol/queue",
        "    create_directory: true",
    ]
    receivers = ["  otlp: ${file:/etc/otelcol/config/capabilities/otlp/receiver.yaml}"]
    log_receivers = ["otlp"]
    metric_receivers = ["otlp"]

    if docker:
        extensions += [
            "  docker_observer: ${file:/etc/otelcol/config/capabilities/docker/observer.yaml}",
            "  file_storage/offsets:",
            "    directory: /var/lib/otelcol/offsets",
            "    create_directory: true",
        ]
        receivers.append(
            "  receiver_creator/docker: ${file:/etc/otelcol/config/capabilities/docker/receiver.yaml}"
        )
        log_receivers.insert(0, "receiver_creator/docker")
    if filelog:
        if not docker:
            extensions += [
                "  file_storage/offsets:",
                "    directory: /var/lib/otelcol/offsets",
                "    create_directory: true",
            ]
        receivers.append(
            "  file_log/application: ${file:/etc/otelcol/config/capabilities/filelog/receiver.yaml}"
        )
        log_receivers.insert(0, "file_log/application")
    if hostmetrics:
        receivers.append(
            "  host_metrics: ${file:/etc/otelcol/config/capabilities/hostmetrics/receiver.yaml}"
        )
        metric_receivers.insert(0, "host_metrics")
    if prometheus:
        receivers.append(
            "  prometheus: ${file:/etc/otelcol/config/capabilities/prometheus/receiver.yaml}"
        )
        metric_receivers.insert(0, "prometheus")

    extension_ids = ["file_storage/queue"]
    if docker:
        extension_ids += ["docker_observer", "file_storage/offsets"]
    elif filelog:
        extension_ids.append("file_storage/offsets")

    return "\n".join(
        [
            "extensions:",
            *extensions,
            "",
            "receivers:",
            *receivers,
            "",
            "processors:",
            "  resource/host: ${file:/etc/otelcol/config/common/processors/resource.yaml}",
            "  batch: ${file:/etc/otelcol/config/common/processors/batch.yaml}",
            "",
            "exporters:",
            f"  otlp_grpc/gateway: ${{file:/etc/otelcol/config/common/exporters/{exporter}.yaml}}",
            "",
            "service:",
            f"  extensions: [{', '.join(extension_ids)}]",
            "  pipelines:",
            "    logs:",
            f"      receivers: [{', '.join(log_receivers)}]",
            "      processors: [resource/host, batch]",
            "      exporters: [otlp_grpc/gateway]",
            "    traces:",
            "      receivers: [otlp]",
            "      processors: [resource/host, batch]",
            "      exporters: [otlp_grpc/gateway]",
            "    metrics:",
            f"      receivers: [{', '.join(metric_receivers)}]",
            "      processors: [resource/host, batch]",
            "      exporters: [otlp_grpc/gateway]",
            "",
        ]
    )


def main() -> None:
    names = sys.argv[1:] or sorted(path.stem for path in PROFILES.glob("*.json"))
    OUTPUT.mkdir(exist_ok=True)
    for name in names:
        (OUTPUT / f"{name}.yaml").write_text(generate(name))
        (OUTPUT / f"{name}-mtls.yaml").write_text(generate(name, exporter="gateway-mtls"))


if __name__ == "__main__":
    main()
