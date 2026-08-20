.PHONY: help setup demo-certs demo-up demo-down demo-ps demo-traffic validate validate-production-compose validate-mtls test lint frontend-build acceptance package-node-agent verify-node-agent-release

DEMO_MTLS_DIR := $(CURDIR)/.tmp/app-observability-mtls
DEMO_GATEWAY_CERTS := $(DEMO_MTLS_DIR)/gateway/certs
DEMO_GATEWAY_SECRETS := $(DEMO_MTLS_DIR)/gateway/secrets
DEMO_AGENT_CERTS := $(DEMO_MTLS_DIR)/agent/certs
DEMO_AGENT_SECRETS := $(DEMO_MTLS_DIR)/agent/secrets
PLATFORM_COMPOSE := docker compose -f docker-compose.yml -f deployments/docker-compose/gateway-mtls.yaml
DEMO_APP_COMPOSE := docker compose -f examples/app-observability/docker-compose.yaml

help:
	@printf '%s\n' \
		'Observability Platform developer commands:' \
		'  make setup                         Copy .env.example to .env when missing' \
		'  make demo-up                       Generate dev certs and start the local demo stack' \
		'  make demo-traffic                  Generate deterministic reference app traffic' \
		'  make demo-ps                       Show platform and demo application containers' \
		'  make demo-down                     Stop the local demo stack' \
		'  make validate                      Validate base Compose and Gateway Collector config' \
		'  make validate-production-compose   Validate production Compose interpolation' \
		'  make validate-mtls                 Validate mTLS cert profiles and generated Agent configs' \
		'  make test                          Run Python unit tests' \
		'  make lint                          Compile Python files for syntax validation' \
		'  make frontend-build                Install and build the Platform Management Console' \
		'  make acceptance                    Run non-destructive acceptance checks against a running stack' \
		'  make package-node-agent VERSION=x  Build Node Agent release artifacts' \
		'  make verify-node-agent-release VERSION=x  Verify Node Agent release artifacts'

setup:
	@test -f .env || cp .env.example .env

demo-certs:
	@test -f "$(DEMO_GATEWAY_CERTS)/gateway.crt" -a -f "$(DEMO_AGENT_CERTS)/client.crt" || \
		GATEWAY_DNS=otel-collector \
		NODE_AGENT_AGENT_ID=app-observability-agent \
		NODE_AGENT_TENANT_ID=demo-tenant \
		NODE_AGENT_SITE_ID=demo-site \
		NODE_AGENT_ENVIRONMENT=development \
		./scripts/dev-mtls-certs.sh "$(DEMO_MTLS_DIR)"

demo-up: setup demo-certs
	GATEWAY_CERTS_HOST_PATH="$(DEMO_GATEWAY_CERTS)" \
	GATEWAY_SECRETS_HOST_PATH="$(DEMO_GATEWAY_SECRETS)" \
	$(PLATFORM_COMPOSE) up -d
	NODE_AGENT_CERTS_HOST_PATH="$(DEMO_AGENT_CERTS)" \
	NODE_AGENT_SECRETS_HOST_PATH="$(DEMO_AGENT_SECRETS)" \
	$(DEMO_APP_COMPOSE) up -d --build

demo-down:
	NODE_AGENT_CERTS_HOST_PATH="$(DEMO_AGENT_CERTS)" \
	NODE_AGENT_SECRETS_HOST_PATH="$(DEMO_AGENT_SECRETS)" \
	$(DEMO_APP_COMPOSE) down
	GATEWAY_CERTS_HOST_PATH="$(DEMO_GATEWAY_CERTS)" \
	GATEWAY_SECRETS_HOST_PATH="$(DEMO_GATEWAY_SECRETS)" \
	$(PLATFORM_COMPOSE) down

demo-ps:
	GATEWAY_CERTS_HOST_PATH="$(DEMO_GATEWAY_CERTS)" \
	GATEWAY_SECRETS_HOST_PATH="$(DEMO_GATEWAY_SECRETS)" \
	$(PLATFORM_COMPOSE) ps
	NODE_AGENT_CERTS_HOST_PATH="$(DEMO_AGENT_CERTS)" \
	NODE_AGENT_SECRETS_HOST_PATH="$(DEMO_AGENT_SECRETS)" \
	$(DEMO_APP_COMPOSE) ps

demo-traffic:
	NODE_AGENT_CERTS_HOST_PATH="$(DEMO_AGENT_CERTS)" \
	NODE_AGENT_SECRETS_HOST_PATH="$(DEMO_AGENT_SECRETS)" \
	$(DEMO_APP_COMPOSE) exec -T -e ORDERS_API_URL=http://localhost:8080 orders-api npm run traffic

validate:
	docker compose --env-file .env.example config --quiet
	docker run --rm --entrypoint /otelcol-contrib -v "$(CURDIR)/collector/gateway:/etc/otelcol:ro" otel/opentelemetry-collector-contrib:0.156.0@sha256:125bdbeb7590cc1952c5b3430ecf14063568980c2c93d5b38676cc0446ed8108 validate --config=/etc/otelcol/config.yaml

validate-production-compose:
	set -a; . deployments/production/production.env.example; set +a; \
	docker compose -f docker-compose.yml -f deployments/docker-compose/production.yaml config --quiet

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
		otel/opentelemetry-collector-contrib:0.156.0@sha256:125bdbeb7590cc1952c5b3430ecf14063568980c2c93d5b38676cc0446ed8108 validate --config=/etc/otelcol/config-mtls.yaml; \
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
			otel/opentelemetry-collector-contrib:0.156.0@sha256:125bdbeb7590cc1952c5b3430ecf14063568980c2c93d5b38676cc0446ed8108 validate --config="/etc/otelcol/config/generated/$$(basename "$$config")" || exit 1; \
	done

test:
	python3 -m unittest discover -s tests -p 'test_*.py'

lint:
	python3 -m compileall services scripts collector/agent/tools tests

frontend-build:
	npm --prefix frontend ci
	npm --prefix frontend run build

acceptance:
	python3 scripts/acceptance-check.py

package-node-agent:
	@test -n "$(VERSION)" || (echo "VERSION is required"; exit 1)
	./scripts/package-node-agent.sh "$(VERSION)"

verify-node-agent-release:
	@test -n "$(VERSION)" || (echo "VERSION is required"; exit 1)
	./scripts/verify-node-agent-release.sh "$(VERSION)"
