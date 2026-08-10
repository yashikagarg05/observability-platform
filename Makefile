.PHONY: validate package-node-agent verify-node-agent-release

validate:
	docker compose config --quiet
	docker run --rm --entrypoint /otelcol-contrib -v "$(CURDIR)/collector/gateway:/etc/otelcol:ro" otel/opentelemetry-collector-contrib:0.156.0 validate --config=/etc/otelcol/config.yaml

package-node-agent:
	@test -n "$(VERSION)" || (echo "VERSION is required"; exit 1)
	./scripts/package-node-agent.sh "$(VERSION)"

verify-node-agent-release:
	@test -n "$(VERSION)" || (echo "VERSION is required"; exit 1)
	./scripts/verify-node-agent-release.sh "$(VERSION)"
