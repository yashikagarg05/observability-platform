.PHONY: validate validate-mtls package-node-agent verify-node-agent-release

validate:
	docker compose config --quiet
	docker run --rm --entrypoint /otelcol-contrib -v "$(CURDIR)/collector/gateway:/etc/otelcol:ro" otel/opentelemetry-collector-contrib:0.156.0 validate --config=/etc/otelcol/config.yaml

validate-mtls:
	tmp_dir=$$(mktemp -d); \
	trap 'rm -rf "$$tmp_dir"' EXIT; \
	GATEWAY_DNS=otel-collector ./scripts/dev-mtls-certs.sh "$$tmp_dir" >/dev/null; \
	./scripts/verify-mtls-cert-profile.sh --type gateway \
		--cert "$$tmp_dir/gateway/certs/gateway.crt" \
		--ca "$$tmp_dir/gateway/certs/gateway-ca-bundle.pem" \
		--key "$$tmp_dir/gateway/secrets/gateway.key" \
		--expected-dns otel-collector \
		--min-days 30; \
	./scripts/verify-mtls-cert-profile.sh --type agent \
		--cert "$$tmp_dir/agent/certs/client.crt" \
		--ca "$$tmp_dir/gateway/certs/agent-ca-bundle.pem" \
		--key "$$tmp_dir/agent/secrets/client.key" \
		--expected-uri spiffe://observability.local/tenant/dev-tenant/site/dev-site/environment/development/agent/dev-agent-01 \
		--min-days 20; \
	python3 collector/agent/tools/compose_capabilities.py; \
	docker run --rm --entrypoint /otelcol-contrib \
		-v "$(CURDIR)/collector/gateway:/etc/otelcol:ro" \
		-v "$$tmp_dir/gateway/certs:/tls/certs:ro" \
		-v "$$tmp_dir/gateway/secrets:/tls/secrets:ro" \
		-e GATEWAY_TLS_CERT_FILE=/tls/certs/gateway.crt \
		-e GATEWAY_TLS_KEY_FILE=/tls/secrets/gateway.key \
		-e GATEWAY_CLIENT_CA_FILE=/tls/certs/agent-ca-bundle.pem \
		otel/opentelemetry-collector-contrib:0.156.0 validate --config=/etc/otelcol/config-mtls.yaml; \
	for config in collector/agent/config/generated/*-mtls.yaml; do \
		extra_mount=; \
		case "$$config" in *hostmetrics*) extra_mount='-v /:/hostfs:ro' ;; esac; \
		docker run --rm --entrypoint /otelcol-contrib \
			-v "$(CURDIR)/collector/agent/config:/etc/otelcol/config:ro" \
			-v "$$tmp_dir/agent/certs:/tls/certs:ro" \
			-v "$$tmp_dir/agent/secrets:/tls/secrets:ro" \
			$$extra_mount \
			-e GATEWAY_OTLP_GRPC_ENDPOINT=otel-collector:4319 \
			-e NODE_AGENT_TLS_CA_FILE=/tls/certs/ca-bundle.pem \
			-e NODE_AGENT_TLS_CERT_FILE=/tls/certs/client.crt \
			-e NODE_AGENT_TLS_KEY_FILE=/tls/secrets/client.key \
			-e AGENT_HOST_NAME=validation-node \
			-e OTEL_SERVICE_NAMESPACE=applications \
			-e OTEL_DEPLOYMENT_ENVIRONMENT=validation \
			otel/opentelemetry-collector-contrib:0.156.0 validate --config="/etc/otelcol/config/generated/$$(basename "$$config")" || exit 1; \
	done

package-node-agent:
	@test -n "$(VERSION)" || (echo "VERSION is required"; exit 1)
	./scripts/package-node-agent.sh "$(VERSION)"

verify-node-agent-release:
	@test -n "$(VERSION)" || (echo "VERSION is required"; exit 1)
	./scripts/verify-node-agent-release.sh "$(VERSION)"
