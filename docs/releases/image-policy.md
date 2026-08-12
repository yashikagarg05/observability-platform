# Container Image Policy

Runtime container images in Compose files, Dockerfiles, Makefile validation commands, and operational scripts should be pinned with immutable digests.

Use the `name:tag@sha256:<digest>` form when a human-readable version tag is useful:

```text
otel/opentelemetry-collector-contrib:0.156.0@sha256:<digest>
```

## Third-Party Images

Do not republish third-party images such as Grafana, Prometheus, Loki, Tempo, OpenTelemetry Collector, Python, Node.js, or BusyBox under this project. Reference the upstream image by digest.

When updating third-party images:

1. Resolve the new digest from the upstream registry.
2. Update every runtime reference.
3. Run `make validate`, `make validate-mtls`, and the frontend build when Node.js images change.
4. Include the image change in `CHANGELOG.md` when it affects a release.

## First-Party Images

Future project-owned images, such as a packaged Control Plane API or Platform UI image, should be published under a project-owned registry namespace such as GitHub Container Registry.

Use version tags for discoverability and digests for deployment reproducibility.

## Non-Runtime Image Matchers

Docker observer `excluded_images` entries are image-name matchers, not runtime pull references. They may remain tag-based when the Collector needs to recognize containers by their original image name.
