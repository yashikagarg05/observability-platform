#!/usr/bin/env python3
"""Minimal Node Agent enrollment API for development and MVP validation."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shlex
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen


@dataclass(frozen=True)
class CertificateIssueResult:
    certificate_pem: str
    issuer: str
    serial: str
    issued_at: float
    expires_at: float


class CertificateIssuer:
    name = "unknown"

    def issue(self, csr_pem: str, agent_uri: str, context: dict[str, Any]) -> CertificateIssueResult:
        raise NotImplementedError


class DevelopmentCertificateIssuer(CertificateIssuer):
    name = "development-local-ca"

    def __init__(self, ca_cert: Path, ca_key: Path, days: int = 60, ca_bundle: Path | None = None) -> None:
        self.ca_cert = ca_cert
        self.ca_key = ca_key
        self.days = days
        self.ca_bundle = ca_bundle

    def issue(self, csr_pem: str, agent_uri: str, context: dict[str, Any]) -> CertificateIssueResult:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csr_file = tmp_path / "client.csr"
            cert_file = tmp_path / "client.crt"
            ext_file = tmp_path / "client.ext.cnf"
            csr_file.write_text(csr_pem)
            ext_file.write_text(
                "\n".join(
                    [
                        "[ v3_node_agent_client ]",
                        "basicConstraints = critical,CA:false",
                        "keyUsage = critical,digitalSignature,keyEncipherment",
                        "extendedKeyUsage = clientAuth",
                        "subjectKeyIdentifier = hash",
                        "authorityKeyIdentifier = keyid,issuer",
                        "subjectAltName = @agent_alt_names",
                        "",
                        "[ agent_alt_names ]",
                        f"URI.1 = {agent_uri}",
                        "",
                    ]
                )
            )
            serial = "0x" + uuid.uuid4().hex
            subprocess.run(
                [
                    "openssl",
                    "x509",
                    "-req",
                    "-in",
                    str(csr_file),
                    "-CA",
                    str(self.ca_cert),
                    "-CAkey",
                    str(self.ca_key),
                    "-set_serial",
                    serial,
                    "-out",
                    str(cert_file),
                    "-days",
                    str(self.days),
                    "-sha256",
                    "-extfile",
                    str(ext_file),
                    "-extensions",
                    "v3_node_agent_client",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return issue_result_from_certificate(cert_file.read_text(), self.name, agent_uri, self.ca_bundle)


class ExternalCommandCertificateIssuer(CertificateIssuer):
    """Production issuer boundary for customer-managed CA integration.

    The command receives request metadata through environment variables and writes
    the signed certificate PEM to ENROLLMENT_CERTIFICATE_FILE. This repository
    does not implement the production CA itself.
    """

    name = "external-command"

    def __init__(self, command: str, ca_bundle: Path | None) -> None:
        if not command:
            raise RuntimeError("ENROLLMENT_PRODUCTION_ISSUER_COMMAND is required in external issuer mode")
        self.command = command
        self.ca_bundle = ca_bundle

    def issue(self, csr_pem: str, agent_uri: str, context: dict[str, Any]) -> CertificateIssueResult:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csr_file = tmp_path / "client.csr"
            request_file = tmp_path / "request.json"
            cert_file = tmp_path / "client.crt"
            csr_file.write_text(csr_pem)
            request_file.write_text(json.dumps({**context, "agent_uri": agent_uri}, indent=2, sort_keys=True) + "\n")
            env = {
                **os.environ,
                "ENROLLMENT_CSR_FILE": str(csr_file),
                "ENROLLMENT_REQUEST_FILE": str(request_file),
                "ENROLLMENT_CERTIFICATE_FILE": str(cert_file),
                "ENROLLMENT_AGENT_URI": agent_uri,
                "ENROLLMENT_AGENT_ID": str(context.get("agent_id", "")),
                "ENROLLMENT_TENANT_ID": str(context.get("tenant_id", "")),
                "ENROLLMENT_SITE_ID": str(context.get("site_id", "")),
                "ENROLLMENT_ENVIRONMENT": str(context.get("environment", "")),
            }
            completed = subprocess.run(
                shlex.split(self.command),
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"external issuer failed: {completed.stderr.strip() or completed.stdout.strip()}")
            if not cert_file.exists():
                raise RuntimeError("external issuer did not write ENROLLMENT_CERTIFICATE_FILE")
            return issue_result_from_certificate(cert_file.read_text(), self.name, agent_uri, self.ca_bundle)


def env_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return Path(value)


def optional_env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def control_plane_cors_origin(operator_token: str | None) -> str | None:
    origin = os.environ.get("FRONTEND_CORS_ORIGIN", "").strip()
    if origin:
        return origin
    return None if operator_token else "*"


def validate_operator_token(token: str | None) -> str | None:
    if not token:
        return None
    weak_markers = ("changeme", "change-me", "replace-me")
    if any(marker in token.lower() for marker in weak_markers):
        raise RuntimeError("CONTROL_PLANE_OPERATOR_TOKEN must be replaced with a long random secret")
    if len(token) < 32:
        raise RuntimeError("CONTROL_PLANE_OPERATOR_TOKEN must be at least 32 characters")
    return token


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {"tokens": {}}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def build_issuer() -> CertificateIssuer:
    mode = os.environ.get("ENROLLMENT_ISSUER_MODE", "external").strip().lower()
    if mode == "external":
        return ExternalCommandCertificateIssuer(
            command=os.environ.get("ENROLLMENT_PRODUCTION_ISSUER_COMMAND", ""),
            ca_bundle=optional_env_path("ENROLLMENT_PRODUCTION_ISSUER_CA_BUNDLE"),
        )
    if mode == "development":
        if os.environ.get("ENROLLMENT_ALLOW_DEVELOPMENT_ISSUER") != "true":
            raise RuntimeError("development issuer requires ENROLLMENT_ALLOW_DEVELOPMENT_ISSUER=true")
        return DevelopmentCertificateIssuer(
            ca_cert=env_path("ENROLLMENT_DEVELOPMENT_AGENT_CA_CERT"),
            ca_key=env_path("ENROLLMENT_DEVELOPMENT_AGENT_CA_KEY"),
            days=int(os.environ.get("ENROLLMENT_AGENT_CERT_DAYS", "60")),
            ca_bundle=optional_env_path("ENROLLMENT_DEVELOPMENT_AGENT_CA_BUNDLE"),
        )
    raise RuntimeError(f"unsupported ENROLLMENT_ISSUER_MODE: {mode}")


def validate_csr(csr_pem: str) -> str:
    if "PRIVATE KEY" in csr_pem:
        raise ValueError("request must not contain a private key")
    with tempfile.TemporaryDirectory() as tmp:
        csr_file = Path(tmp) / "client.csr"
        csr_file.write_text(csr_pem)
        subprocess.run(
            ["openssl", "req", "-verify", "-noout", "-in", str(csr_file)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["openssl", "req", "-noout", "-pubkey", "-in", str(csr_file)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return hashlib.sha256(csr_pem.encode()).hexdigest()


def parse_openssl_time(value: str) -> float:
    return datetime.strptime(value, "%b %d %H:%M:%S %Y GMT").replace(tzinfo=timezone.utc).timestamp()


def certificate_fingerprint(certificate_pem: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        cert_file = Path(tmp) / "client.crt"
        der_file = Path(tmp) / "client.der"
        cert_file.write_text(certificate_pem)
        subprocess.run(
            ["openssl", "x509", "-in", str(cert_file), "-outform", "DER", "-out", str(der_file)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return hashlib.sha256(der_file.read_bytes()).hexdigest()


def certificate_metadata(certificate_pem: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        cert_file = Path(tmp) / "client.crt"
        cert_file.write_text(certificate_pem)
        text = subprocess.check_output(
            ["openssl", "x509", "-in", str(cert_file), "-noout", "-serial", "-issuer", "-dates"],
            text=True,
        )
        metadata: dict[str, Any] = {}
        for line in text.splitlines():
            key, _, value = line.partition("=")
            metadata[key] = value
        return {
            "serial": str(metadata["serial"]).lower(),
            "issuer_subject": metadata["issuer"],
            "issued_at": parse_openssl_time(metadata["notBefore"]),
            "expires_at": parse_openssl_time(metadata["notAfter"]),
        }


def validate_certificate_profile(certificate_pem: str, agent_uri: str, ca_bundle: Path | None) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cert_file = Path(tmp) / "client.crt"
        cert_file.write_text(certificate_pem)
        cert_text = subprocess.check_output(
            ["openssl", "x509", "-in", str(cert_file), "-noout", "-text"],
            text=True,
        )
        if f"URI:{agent_uri}" not in cert_text:
            raise ValueError("issued certificate does not contain expected agent URI SAN")
        if "TLS Web Client Authentication" not in cert_text:
            raise ValueError("issued certificate is missing clientAuth EKU")
        if ca_bundle:
            subprocess.run(
                ["openssl", "verify", "-CAfile", str(ca_bundle), str(cert_file)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def issue_result_from_certificate(
    certificate_pem: str,
    issuer: str,
    agent_uri: str,
    ca_bundle: Path | None,
) -> CertificateIssueResult:
    validate_certificate_profile(certificate_pem, agent_uri, ca_bundle)
    metadata = certificate_metadata(certificate_pem)
    return CertificateIssueResult(
        certificate_pem=certificate_pem,
        issuer=issuer,
        serial=metadata["serial"],
        issued_at=metadata["issued_at"],
        expires_at=metadata["expires_at"],
    )


def parse_agent_uri(agent_uri: str) -> dict[str, str]:
    parsed = urlparse(agent_uri)
    parts = [part for part in parsed.path.split("/") if part]
    values = dict(zip(parts[0::2], parts[1::2], strict=False))
    return {
        "tenant_id": values["tenant"],
        "site_id": values["site"],
        "environment": values["environment"],
        "agent_id": values["agent"],
    }


class AgentRegistry:
    def __init__(self, path: Path, stale_after_seconds: int, offline_after_seconds: int) -> None:
        self.path = path
        self.stale_after_seconds = stale_after_seconds
        self.offline_after_seconds = offline_after_seconds

    def _load(self) -> dict[str, Any]:
        data = json.loads(self.path.read_text()) if self.path.exists() else {"agents": {}}
        data.setdefault("agents", {})
        return data

    def _save(self, data: dict[str, Any]) -> None:
        save_json(self.path, data)

    def _refresh_statuses(self, data: dict[str, Any]) -> None:
        now = time.time()
        changed = False
        for agent in data["agents"].values():
            status = self._status(agent, now)
            if agent.get("status") != status:
                agent["status"] = status
                changed = True
        if changed:
            self._save(data)

    def _status(self, agent: dict[str, Any], now: float | None = None) -> str:
        now = now or time.time()
        if agent.get("disabled_at"):
            return "disabled"
        last_seen = agent.get("last_seen_at")
        if not last_seen:
            return "offline"
        age = now - float(last_seen)
        if age <= self.stale_after_seconds:
            return "healthy"
        if age <= self.offline_after_seconds:
            return "stale"
        return "offline"

    def upsert_from_enrollment(
        self,
        *,
        agent_id: str,
        tenant_id: str,
        site_id: str,
        environment: str,
        host_name: str | None,
        agent_version: str | None,
        capabilities: list[str],
        agent_uri: str,
        fingerprint: str,
        certificate_serial: str,
        certificate_issuer: str,
        certificate_issued_at: float,
        certificate_expires_at: float,
    ) -> dict[str, Any]:
        data = self._load()
        now = time.time()
        existing = data["agents"].get(agent_id, {})
        agent = {
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "site_id": site_id,
            "environment": environment,
            "host_name": host_name,
            "agent_version": agent_version,
            "capabilities": capabilities,
            "status": existing.get("status", "offline"),
            "created_at": existing.get("created_at", now),
            "last_seen_at": existing.get("last_seen_at"),
            "certificate_identity": agent_uri,
            "certificate_fingerprint": fingerprint,
            "certificate_serial": certificate_serial,
            "certificate_issuer": certificate_issuer,
            "certificate_issued_at": certificate_issued_at,
            "certificate_expires_at": certificate_expires_at,
            "certificate_status": "valid",
            "disabled_at": existing.get("disabled_at"),
            "disabled_reason": existing.get("disabled_reason"),
        }
        agent["status"] = self._status(agent, now)
        data["agents"][agent_id] = agent
        self._save(data)
        return self.with_status(agent)

    def update_certificate(
        self,
        agent_id: str,
        *,
        fingerprint: str,
        serial: str,
        issuer: str,
        issued_at: float,
        expires_at: float,
    ) -> dict[str, Any]:
        data = self._load()
        if agent_id not in data["agents"]:
            raise KeyError("unknown agent")
        agent = data["agents"][agent_id]
        agent.update(
            {
                "certificate_fingerprint": fingerprint,
                "certificate_serial": serial,
                "certificate_issuer": issuer,
                "certificate_issued_at": issued_at,
                "certificate_expires_at": expires_at,
                "certificate_status": "valid",
            }
        )
        data["agents"][agent_id] = agent
        self._save(data)
        return self.with_status(agent)

    def set_disabled(self, agent_id: str, disabled: bool, reason: str | None = None) -> dict[str, Any]:
        data = self._load()
        if agent_id not in data["agents"]:
            raise KeyError("unknown agent")
        agent = data["agents"][agent_id]
        if disabled:
            agent["disabled_at"] = time.time()
            agent["disabled_reason"] = reason or "operator disabled"
            agent["certificate_status"] = "disabled"
        else:
            agent["disabled_at"] = None
            agent["disabled_reason"] = None
            agent["certificate_status"] = self._certificate_status(agent)
        agent["status"] = self._status(agent)
        data["agents"][agent_id] = agent
        self._save(data)
        return self.with_status(agent)

    def heartbeat(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._load()
        if agent_id not in data["agents"]:
            raise KeyError("unknown agent")
        agent = data["agents"][agent_id]
        if agent.get("disabled_at"):
            raise PermissionError("agent is disabled")
        for key in ("host_name", "agent_version", "capabilities"):
            if key in payload:
                agent[key] = payload[key]
        agent["last_seen_at"] = time.time()
        agent["status"] = self._status(agent)
        data["agents"][agent_id] = agent
        self._save(data)
        return self.with_status(agent)

    def with_status(self, agent: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(agent)
        enriched["status"] = self._status(agent)
        enriched["certificate_status"] = self._certificate_status(agent)
        enriched["telemetry_recent"] = "unknown"
        return enriched

    def _certificate_status(self, agent: dict[str, Any]) -> str:
        if agent.get("disabled_at"):
            return "disabled"
        expires_at = agent.get("certificate_expires_at")
        if not expires_at:
            return agent.get("certificate_status", "unknown")
        now = time.time()
        expires = float(expires_at)
        if expires <= now:
            return "expired"
        if expires - now <= 20 * 24 * 60 * 60:
            return "expiring_soon"
        return "valid"

    def list_agents(self, filters: dict[str, str]) -> list[dict[str, Any]]:
        data = self._load()
        self._refresh_statuses(data)
        agents = [self.with_status(agent) for agent in data["agents"].values()]
        for key, value in filters.items():
            if value:
                agents = [agent for agent in agents if str(agent.get(key)) == value]
        return sorted(agents, key=lambda agent: agent["agent_id"])

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        data = self._load()
        self._refresh_statuses(data)
        return data["agents"].get(agent_id)


class PrometheusClient:
    def __init__(self, base_url: str | None) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None

    def query(self, expression: str) -> list[dict[str, Any]]:
        if not self.base_url:
            return []
        url = f"{self.base_url}/api/v1/query?{urlencode({'query': expression})}"
        with urlopen(url, timeout=10) as response:
            payload = json.loads(response.read())
        if payload.get("status") != "success":
            raise RuntimeError(payload.get("error", "prometheus query failed"))
        return payload.get("data", {}).get("result", [])


def vector_by_host(results: list[dict[str, Any]]) -> dict[str, float]:
    values: dict[str, float] = {}
    for result in results:
        host_name = result.get("metric", {}).get("host_name")
        if not host_name:
            continue
        try:
            values[host_name] = float(result["value"][1])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return values


class InfrastructureService:
    CPU_QUERY = '(1 - avg by (host_name) (rate(system_cpu_time_seconds_total{state="idle",host_name!=""}[5m]))) * 100'
    MEMORY_QUERY = (
        'sum by (host_name) (system_memory_usage_bytes{state="used",host_name!=""}) '
        '/ sum by (host_name) (system_memory_usage_bytes{host_name!=""}) * 100'
    )
    FILESYSTEM_QUERY = (
        'sum by (host_name) (system_filesystem_usage_bytes{state="used",host_name!=""}) '
        '/ (sum by (host_name) (system_filesystem_usage_bytes{state="used",host_name!=""}) '
        '+ sum by (host_name) (system_filesystem_usage_bytes{state="free",host_name!=""})) * 100'
    )
    NETWORK_QUERY = 'sum by (host_name) (rate(system_network_io_bytes_total{host_name!=""}[5m]))'

    def __init__(self, prometheus: PrometheusClient) -> None:
        self.prometheus = prometheus

    def host_metrics(self) -> tuple[dict[str, dict[str, float | None]], dict[str, Any]]:
        queries = {
            "cpu_percent": self.CPU_QUERY,
            "memory_percent": self.MEMORY_QUERY,
            "filesystem_percent": self.FILESYSTEM_QUERY,
            "network_bytes_per_second": self.NETWORK_QUERY,
        }
        metrics: dict[str, dict[str, float | None]] = {}
        errors: dict[str, str] = {}
        for key, expression in queries.items():
            try:
                values = vector_by_host(self.prometheus.query(expression))
            except Exception as exc:  # noqa: BLE001
                errors[key] = str(exc)
                values = {}
            for host_name, value in values.items():
                metrics.setdefault(host_name, {})[key] = value
        return metrics, {"available": bool(metrics), "errors": errors}

    def hosts(self, agents: list[dict[str, Any]], filters: dict[str, str]) -> dict[str, Any]:
        metrics, source = self.host_metrics()
        host_names = set(metrics)
        host_names.update(agent["host_name"] for agent in agents if agent.get("host_name"))
        hosts: list[dict[str, Any]] = []
        for host_name in sorted(host_names):
            agent = next((candidate for candidate in agents if candidate.get("host_name") == host_name), None)
            hosts.append(
                {
                    "host_name": host_name,
                    "agent_id": agent.get("agent_id") if agent else None,
                    "agent_status": agent.get("status") if agent else "unknown",
                    "environment": agent.get("environment") if agent else filters.get("environment") or None,
                    "site_id": agent.get("site_id") if agent else filters.get("site_id") or None,
                    "cpu_percent": metrics.get(host_name, {}).get("cpu_percent"),
                    "memory_percent": metrics.get(host_name, {}).get("memory_percent"),
                    "filesystem_percent": metrics.get(host_name, {}).get("filesystem_percent"),
                    "network_bytes_per_second": metrics.get(host_name, {}).get("network_bytes_per_second"),
                }
            )
        return {"hosts": hosts, "source": source}


def summarize_agents(agents: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(agents),
        "healthy": sum(1 for agent in agents if agent.get("status") == "healthy"),
        "stale": sum(1 for agent in agents if agent.get("status") == "stale"),
        "offline": sum(1 for agent in agents if agent.get("status") == "offline"),
    }


def summarize_infrastructure(hosts: list[dict[str, Any]]) -> dict[str, Any]:
    def average(key: str) -> float | None:
        values = [float(host[key]) for host in hosts if host.get(key) is not None]
        return sum(values) / len(values) if values else None

    return {
        "host_count": len(hosts),
        "cpu_percent": average("cpu_percent"),
        "memory_percent": average("memory_percent"),
        "filesystem_percent": average("filesystem_percent"),
        "network_bytes_per_second": average("network_bytes_per_second"),
    }


def count_by(agents: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for agent in agents:
        value = agent.get(key) or "unknown"
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def capability_counts(agents: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for agent in agents:
        for capability in agent.get("capabilities", []):
            counts[str(capability)] = counts.get(str(capability), 0) + 1
    return dict(sorted(counts.items()))


def recent_agent_activity(agents: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    ordered = sorted(agents, key=lambda agent: agent.get("last_seen_at") or 0, reverse=True)
    return [
        {
            "agent_id": agent["agent_id"],
            "host_name": agent.get("host_name"),
            "status": agent.get("status"),
            "last_seen_at": agent.get("last_seen_at"),
        }
        for agent in ordered[:limit]
    ]


def site_summaries(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sites: dict[tuple[str, str], dict[str, Any]] = {}
    for agent in agents:
        key = (agent.get("site_id") or "unknown", agent.get("environment") or "unknown")
        site = sites.setdefault(
            key,
            {
                "site_id": key[0],
                "environment": key[1],
                "agent_count": 0,
                "healthy": 0,
                "stale": 0,
                "offline": 0,
            },
        )
        site["agent_count"] += 1
        if agent.get("status") in ("healthy", "stale", "offline"):
            site[agent["status"]] += 1
    return sorted(sites.values(), key=lambda site: (site["environment"], site["site_id"]))


class GrafanaLinks:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def url(self, path: str = "/") -> str:
        return f"{self.base_url}{path}"

    def explore(self, datasource_uid: str, query: str = "") -> str:
        left = {
            "datasource": datasource_uid,
            "queries": [{"refId": "A", "datasource": {"uid": datasource_uid}, "expr": query}],
            "range": {"from": "now-1h", "to": "now"},
        }
        return self.url(f"/explore?{urlencode({'left': json.dumps(left)})}")

    def for_agent(self, agent: dict[str, Any]) -> dict[str, str]:
        host_name = agent.get("host_name") or ""
        host_filter = f'{{host_name="{host_name}"}}' if host_name else ""
        metric_query = f'system_cpu_time_seconds_total{{host_name="{host_name}"}}' if host_name else ""
        return {
            "logs": self.explore("loki", host_filter),
            "metrics": self.explore("prometheus", metric_query),
            "traces": self.explore("tempo"),
            "grafana": self.url("/"),
        }


class EnrollmentHandler(BaseHTTPRequestHandler):
    server_version = "node-agent-enrollment-mvp/1"

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/v1/node-agents/enroll":
            self.handle_enroll()
            return
        if parsed.path == "/v1/enrollment/credentials":
            self.handle_create_enrollment_credential(parsed)
            return
        if parsed.path.startswith("/v1/node-agents/") and parsed.path.endswith("/renew"):
            self.handle_renew(parsed.path)
            return
        if parsed.path.startswith("/v1/node-agents/") and parsed.path.endswith("/disable"):
            self.handle_disable(parsed.path, disabled=True)
            return
        if parsed.path.startswith("/v1/node-agents/") and parsed.path.endswith("/enable"):
            self.handle_disable(parsed.path, disabled=False)
            return
        if parsed.path.startswith("/v1/node-agents/") and parsed.path.endswith("/heartbeat"):
            self.handle_heartbeat(parsed.path)
            return
        self.send_error(404)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_json(204, {})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self.send_json(200, {"status": "ok"})
            return
        if parsed.path == "/v1/overview":
            self.handle_overview(parsed)
            return
        if parsed.path == "/v1/infrastructure/hosts":
            self.handle_list_hosts(parsed)
            return
        if parsed.path.startswith("/v1/infrastructure/hosts/"):
            self.handle_get_host(parsed)
            return
        if parsed.path == "/v1/sites":
            self.handle_sites(parsed)
            return
        if parsed.path == "/v1/environments":
            self.handle_environments(parsed)
            return
        if parsed.path == "/v1/capabilities":
            self.handle_capabilities(parsed)
            return
        if parsed.path == "/v1/integrations":
            self.handle_integrations(parsed)
            return
        if parsed.path == "/v1/node-agents":
            self.handle_list_agents(parsed)
            return
        if parsed.path.startswith("/v1/node-agents/"):
            self.handle_get_agent(parsed.path)
            return
        if parsed.path == "/agents":
            self.handle_agents_page(parsed)
            return
        self.send_error(404)

    def read_json_body(self) -> tuple[dict[str, Any], bool, bytes]:
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        private_key_present = b"PRIVATE KEY" in body
        return json.loads(body), private_key_present, body

    def send_json(self, status: int, payload: Any) -> None:
        self.send_response(status)
        self.send_header("content-type", "application/json")
        cors_origin = control_plane_cors_origin(self.server.operator_token)  # type: ignore[attr-defined]
        if cors_origin:
            self.send_header("access-control-allow-origin", cors_origin)
        self.send_header("access-control-allow-headers", "authorization,content-type,x-tenant-id")
        self.send_header("access-control-allow-methods", "GET,POST,OPTIONS")
        self.end_headers()
        if status != 204:
            self.wfile.write(json.dumps(payload, sort_keys=True).encode())

    def require_operator(self) -> str:
        tenant = self.server.single_tenant_id  # type: ignore[attr-defined]
        token = self.server.operator_token  # type: ignore[attr-defined]
        if not token:
            return tenant
        auth = self.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            raise PermissionError("missing operator bearer token")
        supplied = auth.removeprefix("Bearer ").strip()
        if not secrets.compare_digest(supplied, token):
            raise PermissionError("invalid operator bearer token")
        return tenant

    def request_tenant(self, parsed: Any | None = None) -> str:
        query = parse_qs(parsed.query) if parsed else {}
        if self.server.operator_token:  # type: ignore[attr-defined]
            tenant = self.require_operator()
        else:
            tenant = self.headers.get("x-tenant-id") or (query.get("tenant_id", [None])[0])
            if not tenant:
                raise PermissionError("tenant_id is required")
        query_tenant = query.get("tenant_id", [tenant])[0]
        if query_tenant != tenant:
            raise PermissionError("tenant_id filter does not match tenant boundary")
        return tenant

    def handle_enroll(self) -> None:
        request: dict[str, Any] = {}
        private_key_present = False
        try:
            request, private_key_present, _body = self.read_json_body()
            auth = self.headers.get("authorization", "")
            if not auth.startswith("Bearer "):
                raise PermissionError("missing bearer enrollment credential")
            token = auth.removeprefix("Bearer ").strip()
            if private_key_present:
                raise ValueError("private key material is not accepted")
            csr_pem = request["csr_pem"]
            csr_sha256 = validate_csr(csr_pem)
            response = self.server.enroll(token, csr_pem, csr_sha256, sorted(request.keys()), private_key_present)  # type: ignore[attr-defined]
            self.send_json(200, response)
        except PermissionError as exc:
            self.server.audit("enrollment_rejected", {"reason": str(exc), "private_key_present": private_key_present})  # type: ignore[attr-defined]
            self.send_error(403, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.server.audit("enrollment_failed", {"reason": str(exc), "private_key_present": private_key_present})  # type: ignore[attr-defined]
            self.send_error(400, str(exc))

    def handle_heartbeat(self, path: str) -> None:
        try:
            agent_id = path.split("/")[3]
            payload, private_key_present, _body = self.read_json_body()
            if private_key_present:
                raise ValueError("private key material is not accepted")
            tenant = self.server.single_tenant_id if self.server.operator_token else self.headers.get("x-tenant-id") or payload.get("tenant_id")  # type: ignore[attr-defined]
            if not tenant:
                raise PermissionError("tenant_id is required")
            agent = self.server.registry.get_agent(agent_id)  # type: ignore[attr-defined]
            if not agent or agent["tenant_id"] != tenant:
                raise PermissionError("agent not found for tenant")
            updated = self.server.registry.heartbeat(agent_id, payload)  # type: ignore[attr-defined]
            self.server.audit("agent_heartbeat", {"agent_id": agent_id, "tenant_id": tenant})  # type: ignore[attr-defined]
            self.send_json(200, updated)
        except PermissionError as exc:
            self.send_error(403, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.send_error(400, str(exc))

    def handle_renew(self, path: str) -> None:
        private_key_present = False
        try:
            agent_id = path.split("/")[3]
            payload, private_key_present, _body = self.read_json_body()
            if private_key_present:
                raise ValueError("private key material is not accepted")
            auth = self.headers.get("authorization", "")
            if not auth.startswith("Bearer "):
                raise PermissionError("missing bearer renewal credential")
            token = auth.removeprefix("Bearer ").strip()
            csr_pem = payload["csr_pem"]
            csr_sha256 = validate_csr(csr_pem)
            response = self.server.renew(agent_id, token, csr_pem, csr_sha256, sorted(payload.keys()), private_key_present)  # type: ignore[attr-defined]
            self.send_json(200, response)
        except PermissionError as exc:
            self.server.audit("renewal_rejected", {"reason": str(exc), "private_key_present": private_key_present})  # type: ignore[attr-defined]
            self.send_error(403, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.server.audit("renewal_failed", {"reason": str(exc), "private_key_present": private_key_present})  # type: ignore[attr-defined]
            self.send_error(400, str(exc))

    def handle_disable(self, path: str, disabled: bool) -> None:
        try:
            tenant = self.request_tenant(urlparse(self.path))
            agent_id = path.split("/")[3]
            payload, private_key_present, _body = self.read_json_body()
            if private_key_present:
                raise ValueError("private key material is not accepted")
            agent = self.server.registry.get_agent(agent_id)  # type: ignore[attr-defined]
            if not agent or agent["tenant_id"] != tenant:
                self.send_error(404)
                return
            updated = self.server.registry.set_disabled(agent_id, disabled, payload.get("reason"))  # type: ignore[attr-defined]
            self.server.audit(  # type: ignore[attr-defined]
                "agent_disabled" if disabled else "agent_enabled",
                {"agent_id": agent_id, "tenant_id": tenant, "reason": payload.get("reason")},
            )
            self.send_json(200, updated)
        except PermissionError as exc:
            self.send_error(403, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.send_error(400, str(exc))

    def handle_list_agents(self, parsed: Any) -> None:
        try:
            tenant = self.request_tenant(parsed)
            query = parse_qs(parsed.query)
            filters = {
                "tenant_id": tenant,
                "site_id": query.get("site_id", [""])[0],
                "environment": query.get("environment", [""])[0],
                "status": query.get("status", [""])[0],
            }
            self.send_json(200, {"agents": self.server.registry.list_agents(filters)})  # type: ignore[attr-defined]
        except PermissionError as exc:
            self.send_error(403, str(exc))

    def handle_get_agent(self, path: str) -> None:
        try:
            tenant = self.request_tenant(urlparse(self.path))
            agent_id = path.split("/")[3]
            agent = self.server.registry.get_agent(agent_id)  # type: ignore[attr-defined]
            if not agent or agent["tenant_id"] != tenant:
                self.send_error(404)
                return
            response = self.server.registry.with_status(agent)  # type: ignore[attr-defined]
            response["grafana_links"] = self.server.grafana_links.for_agent(response)  # type: ignore[attr-defined]
            self.send_json(200, response)
        except PermissionError as exc:
            self.send_error(403, str(exc))

    def handle_create_enrollment_credential(self, parsed: Any) -> None:
        try:
            tenant = self.request_tenant(parsed)
            payload, private_key_present, _body = self.read_json_body()
            if private_key_present:
                raise ValueError("private key material is not accepted")
            credential = self.server.create_enrollment_credential(tenant, payload)  # type: ignore[attr-defined]
            self.send_json(201, credential)
        except PermissionError as exc:
            self.send_error(403, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.send_error(400, str(exc))

    def filters_from_query(self, parsed: Any) -> tuple[str, dict[str, str]]:
        tenant = self.request_tenant(parsed)
        query = parse_qs(parsed.query)
        return tenant, {
            "tenant_id": tenant,
            "site_id": query.get("site_id", [""])[0],
            "environment": query.get("environment", [""])[0],
            "status": query.get("status", [""])[0],
        }

    def handle_list_hosts(self, parsed: Any) -> None:
        try:
            _tenant, filters = self.filters_from_query(parsed)
            agents = self.server.registry.list_agents(filters)  # type: ignore[attr-defined]
            self.send_json(200, self.server.infrastructure.hosts(agents, filters))  # type: ignore[attr-defined]
        except PermissionError as exc:
            self.send_error(403, str(exc))

    def handle_get_host(self, parsed: Any) -> None:
        try:
            host_name = parsed.path.removeprefix("/v1/infrastructure/hosts/")
            _tenant, filters = self.filters_from_query(parsed)
            agents = self.server.registry.list_agents(filters)  # type: ignore[attr-defined]
            hosts = self.server.infrastructure.hosts(agents, filters)  # type: ignore[attr-defined]
            host = next((candidate for candidate in hosts["hosts"] if candidate["host_name"] == host_name), None)
            if not host:
                self.send_error(404)
                return
            self.send_json(200, {**host, "source": hosts["source"]})
        except PermissionError as exc:
            self.send_error(403, str(exc))

    def handle_overview(self, parsed: Any) -> None:
        try:
            _tenant, filters = self.filters_from_query(parsed)
            agents = self.server.registry.list_agents(filters)  # type: ignore[attr-defined]
            hosts_payload = self.server.infrastructure.hosts(agents, filters)  # type: ignore[attr-defined]
            self.send_json(
                200,
                {
                    "agents": summarize_agents(agents),
                    "agents_by_version": count_by(agents, "agent_version"),
                    "agents_by_environment": count_by(agents, "environment"),
                    "agents_by_site": count_by(agents, "site_id"),
                    "capabilities": capability_counts(agents),
                    "recent_agent_activity": recent_agent_activity(agents),
                    "platform_health": {
                        "agent_registry": "available",
                        "prometheus": "available" if hosts_payload["source"]["available"] else "unavailable",
                    },
                    "infrastructure": {
                        **summarize_infrastructure(hosts_payload["hosts"]),
                        "grafana_url": self.server.grafana_links.explore("prometheus"),  # type: ignore[attr-defined]
                    },
                },
            )
        except PermissionError as exc:
            self.send_error(403, str(exc))

    def handle_sites(self, parsed: Any) -> None:
        try:
            _tenant, filters = self.filters_from_query(parsed)
            agents = self.server.registry.list_agents(filters)  # type: ignore[attr-defined]
            self.send_json(200, {"sites": site_summaries(agents)})
        except PermissionError as exc:
            self.send_error(403, str(exc))

    def handle_environments(self, parsed: Any) -> None:
        try:
            _tenant, filters = self.filters_from_query(parsed)
            agents = self.server.registry.list_agents(filters)  # type: ignore[attr-defined]
            seen = count_by(agents, "environment")
            defaults = ["production", "staging", "development", "validation"]
            environments = [{"environment": name, "agent_count": seen.get(name, 0)} for name in defaults]
            for name, count in seen.items():
                if name not in defaults:
                    environments.append({"environment": name, "agent_count": count})
            self.send_json(200, {"environments": environments})
        except PermissionError as exc:
            self.send_error(403, str(exc))

    def handle_capabilities(self, parsed: Any) -> None:
        try:
            _tenant, filters = self.filters_from_query(parsed)
            agents = self.server.registry.list_agents(filters)  # type: ignore[attr-defined]
            counts = capability_counts(agents)
            supported = ["otlp", "docker", "filelog", "hostmetrics", "prometheus"]
            capabilities = [{"capability": name, "agents": counts.get(name, 0)} for name in supported]
            for name, count in counts.items():
                if name not in supported:
                    capabilities.append({"capability": name, "agents": count})
            self.send_json(200, {"capabilities": capabilities})
        except PermissionError as exc:
            self.send_error(403, str(exc))

    def handle_integrations(self, parsed: Any) -> None:
        try:
            self.request_tenant(parsed)
            self.send_json(
                200,
                {
                    "integrations": [
                        {
                            "name": "Grafana",
                            "role": "Telemetry exploration, dashboards, and visualization",
                            "status": "configured",
                            "url": self.server.grafana_links.url("/"),  # type: ignore[attr-defined]
                            "actions": [{"label": "Open Grafana", "url": self.server.grafana_links.url("/")}],  # type: ignore[attr-defined]
                        },
                        {"name": "Loki", "role": "Logs backend", "status": "configured", "reference": "datasource uid: loki"},
                        {"name": "Tempo", "role": "Traces backend", "status": "configured", "reference": "datasource uid: tempo"},
                        {
                            "name": "Prometheus",
                            "role": "Metrics backend",
                            "status": "configured",
                            "reference": "datasource uid: prometheus",
                        },
                        {"name": "Gateway", "role": "OTLP ingestion and routing", "status": "configured"},
                    ]
                },
            )
        except PermissionError as exc:
            self.send_error(403, str(exc))

    def handle_agents_page(self, parsed: Any) -> None:
        try:
            tenant = self.request_tenant(parsed)
            agents = self.server.registry.list_agents({"tenant_id": tenant})  # type: ignore[attr-defined]
            rows = "\n".join(
                f"<tr><td><a href=\"/v1/node-agents/{agent['agent_id']}?tenant_id={tenant}\">{agent['agent_id']}</a></td>"
                f"<td>{agent['status']}</td><td>{agent.get('agent_version') or ''}</td>"
                f"<td>{agent['environment']}</td><td>{agent['site_id']}</td><td>{agent.get('last_seen_at') or ''}</td></tr>"
                for agent in agents
            )
            html = (
                "<!doctype html><title>Agents</title><h1>Agents</h1>"
                "<table><thead><tr><th>Agent</th><th>Status</th><th>Version</th>"
                "<th>Environment</th><th>Site</th><th>Last Seen</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>"
            )
            self.send_response(200)
            self.send_header("content-type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode())
        except PermissionError as exc:
            self.send_error(403, str(exc))

    def log_message(self, format: str, *args: Any) -> None:
        self.server.audit("http", {"message": format % args})  # type: ignore[attr-defined]


class EnrollmentServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        credentials_file: Path,
        issuer: CertificateIssuer,
        gateway_ca_bundle: Path,
        registry: AgentRegistry,
        infrastructure: InfrastructureService,
        grafana_links: GrafanaLinks,
        audit_log: Path | None,
        single_tenant_id: str,
        operator_token: str | None,
    ) -> None:
        super().__init__(address, EnrollmentHandler)
        self.credentials_file = credentials_file
        self.issuer = issuer
        self.gateway_ca_bundle = gateway_ca_bundle
        self.registry = registry
        self.infrastructure = infrastructure
        self.grafana_links = grafana_links
        self.audit_log = audit_log
        self.single_tenant_id = single_tenant_id
        self.operator_token = operator_token

    def audit(self, event: str, fields: dict[str, Any]) -> None:
        record = {"ts": time.time(), "event": event, **fields}
        line = json.dumps(record, sort_keys=True)
        print(line, flush=True)
        if self.audit_log:
            with self.audit_log.open("a") as handle:
                handle.write(line + "\n")

    def enroll(
        self,
        token: str,
        csr_pem: str,
        csr_sha256: str,
        request_keys: list[str],
        private_key_present: bool,
    ) -> dict[str, str]:
        data = load_json(self.credentials_file)
        entry = data.get("tokens", {}).get(token)
        if not entry:
            raise PermissionError("invalid enrollment credential")
        if entry.get("used"):
            raise PermissionError("enrollment credential already used")
        if entry.get("purpose", "enrollment") != "enrollment":
            raise PermissionError("credential is not valid for enrollment")

        agent_id = entry.get("agent_id") or f"agent-{uuid.uuid4().hex}"
        identity_domain = entry.get("identity_domain", "observability.local")
        agent_uri = (
            f"spiffe://{identity_domain}/tenant/{entry['tenant_id']}"
            f"/site/{entry['site_id']}/environment/{entry['environment']}/agent/{agent_id}"
        )
        context = {
            "operation": "enrollment",
            "agent_id": agent_id,
            "tenant_id": entry["tenant_id"],
            "site_id": entry["site_id"],
            "environment": entry["environment"],
            "csr_sha256": csr_sha256,
        }
        issue = self.issuer.issue(csr_pem, agent_uri, context)
        fingerprint = certificate_fingerprint(issue.certificate_pem)
        capabilities = entry.get("capabilities") or []
        registered = self.registry.upsert_from_enrollment(
            agent_id=agent_id,
            tenant_id=entry["tenant_id"],
            site_id=entry["site_id"],
            environment=entry["environment"],
            host_name=entry.get("host_name"),
            agent_version=entry.get("agent_version"),
            capabilities=capabilities,
            agent_uri=agent_uri,
            fingerprint=fingerprint,
            certificate_serial=issue.serial,
            certificate_issuer=issue.issuer,
            certificate_issued_at=issue.issued_at,
            certificate_expires_at=issue.expires_at,
        )
        entry.update({"used": True, "used_at": time.time(), "agent_id": agent_id, "agent_uri": agent_uri})
        save_json(self.credentials_file, data)
        self.audit(
            "enrollment_issued",
            {
                "agent_id": agent_id,
                "tenant_id": entry["tenant_id"],
                "site_id": entry["site_id"],
                "environment": entry["environment"],
                "agent_uri": agent_uri,
                "body_keys": request_keys,
                "csr_sha256": csr_sha256,
                "certificate_fingerprint": fingerprint,
                "certificate_serial": issue.serial,
                "certificate_issuer": issue.issuer,
                "certificate_issued_at": issue.issued_at,
                "certificate_expires_at": issue.expires_at,
                "result": "issued",
                "private_key_present": private_key_present,
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            },
        )
        return {
            "agent_id": agent_id,
            "agent_uri": agent_uri,
            "certificate_pem": issue.certificate_pem,
            "ca_bundle_pem": self.gateway_ca_bundle.read_text(),
            "certificate_fingerprint": fingerprint,
            "certificate_serial": issue.serial,
            "certificate_issued_at": issue.issued_at,
            "certificate_expires_at": issue.expires_at,
            "registry_status": registered["status"],
        }

    def renew(
        self,
        agent_id: str,
        token: str,
        csr_pem: str,
        csr_sha256: str,
        request_keys: list[str],
        private_key_present: bool,
    ) -> dict[str, Any]:
        data = load_json(self.credentials_file)
        entry = data.get("tokens", {}).get(token)
        if not entry:
            raise PermissionError("invalid renewal credential")
        if entry.get("used"):
            raise PermissionError("renewal credential already used")
        if entry.get("purpose") != "renewal":
            raise PermissionError("credential is not valid for renewal")
        if entry.get("agent_id") != agent_id:
            raise PermissionError("renewal credential does not match agent")
        agent = self.registry.get_agent(agent_id)
        if not agent or agent["tenant_id"] != entry["tenant_id"]:
            raise PermissionError("agent not found for tenant")
        if agent.get("disabled_at"):
            raise PermissionError("agent is disabled")

        agent_uri = agent["certificate_identity"]
        context = {
            "operation": "renewal",
            "agent_id": agent_id,
            "tenant_id": agent["tenant_id"],
            "site_id": agent["site_id"],
            "environment": agent["environment"],
            "csr_sha256": csr_sha256,
        }
        issue = self.issuer.issue(csr_pem, agent_uri, context)
        fingerprint = certificate_fingerprint(issue.certificate_pem)
        updated = self.registry.update_certificate(
            agent_id,
            fingerprint=fingerprint,
            serial=issue.serial,
            issuer=issue.issuer,
            issued_at=issue.issued_at,
            expires_at=issue.expires_at,
        )
        entry.update({"used": True, "used_at": time.time(), "agent_uri": agent_uri})
        save_json(self.credentials_file, data)
        self.audit(
            "certificate_renewal_issued",
            {
                "agent_id": agent_id,
                "tenant_id": agent["tenant_id"],
                "site_id": agent["site_id"],
                "environment": agent["environment"],
                "agent_uri": agent_uri,
                "body_keys": request_keys,
                "csr_sha256": csr_sha256,
                "certificate_fingerprint": fingerprint,
                "certificate_serial": issue.serial,
                "certificate_issuer": issue.issuer,
                "certificate_issued_at": issue.issued_at,
                "certificate_expires_at": issue.expires_at,
                "result": "issued",
                "private_key_present": private_key_present,
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            },
        )
        return {
            "agent_id": agent_id,
            "agent_uri": agent_uri,
            "certificate_pem": issue.certificate_pem,
            "ca_bundle_pem": self.gateway_ca_bundle.read_text(),
            "certificate_fingerprint": fingerprint,
            "certificate_serial": issue.serial,
            "certificate_issued_at": issue.issued_at,
            "certificate_expires_at": issue.expires_at,
            "registry_status": updated["status"],
        }

    def create_enrollment_credential(self, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        purpose = payload.get("purpose", "enrollment")
        if purpose not in ("enrollment", "renewal"):
            raise ValueError("purpose must be enrollment or renewal")
        if purpose == "renewal":
            agent_id = payload.get("agent_id")
            if not agent_id:
                raise ValueError("agent_id is required for renewal credentials")
            agent = self.registry.get_agent(agent_id)
            if not agent or agent["tenant_id"] != tenant_id:
                raise PermissionError("agent not found for tenant")
            if agent.get("disabled_at"):
                raise PermissionError("agent is disabled")
            token = secrets.token_urlsafe(32)
            data = load_json(self.credentials_file)
            data.setdefault("tokens", {})[token] = {
                "purpose": "renewal",
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "site_id": agent["site_id"],
                "environment": agent["environment"],
                "used": False,
                "created_at": time.time(),
            }
            save_json(self.credentials_file, data)
            self.audit(
                "renewal_credential_created",
                {
                    "agent_id": agent_id,
                    "tenant_id": tenant_id,
                    "site_id": agent["site_id"],
                    "environment": agent["environment"],
                    "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                },
            )
            endpoint = os.environ.get("PUBLIC_ENROLLMENT_ENDPOINT", "http://localhost:8080")
            return {
                "renewal_credential": token,
                "one_time": True,
                "agent_id": agent_id,
                "renewal_command": (
                    f"NODE_AGENT_ENROLLMENT_ENDPOINT={endpoint} "
                    f"NODE_AGENT_RENEWAL_CREDENTIAL={token} "
                    "bin/enroll-node-agent.sh renew"
                ),
            }

        site_id = payload.get("site_id")
        environment = payload.get("environment")
        capabilities = payload.get("capabilities", [])
        if not site_id:
            raise ValueError("site_id is required")
        if not environment:
            raise ValueError("environment is required")
        if not isinstance(capabilities, list):
            raise ValueError("capabilities must be a list")

        token = secrets.token_urlsafe(32)
        data = load_json(self.credentials_file)
        data.setdefault("tokens", {})[token] = {
            "purpose": "enrollment",
            "tenant_id": tenant_id,
            "site_id": site_id,
            "environment": environment,
            "identity_domain": payload.get("identity_domain", "observability.local"),
            "host_name": payload.get("host_name"),
            "agent_version": payload.get("agent_version"),
            "capabilities": capabilities,
            "used": False,
            "created_at": time.time(),
        }
        save_json(self.credentials_file, data)
        self.audit(
            "enrollment_credential_created",
            {
                "tenant_id": tenant_id,
                "site_id": site_id,
                "environment": environment,
                "capabilities": capabilities,
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            },
        )
        endpoint = os.environ.get("PUBLIC_ENROLLMENT_ENDPOINT", "http://localhost:8080")
        return {
            "enrollment_credential": token,
            "one_time": True,
            "site_id": site_id,
            "environment": environment,
            "capabilities": capabilities,
            "install_command": "tar -xzf otel-node-agent-<version>.tgz && cd otel-node-agent-<version>",
            "enrollment_command": (
                f"NODE_AGENT_ENROLLMENT_ENDPOINT={endpoint} "
                f"NODE_AGENT_ENROLLMENT_CREDENTIAL={token} "
                "bin/enroll-node-agent.sh enroll"
            ),
            "start_command": (
                "NODE_AGENT_TRANSPORT_SUFFIX=-mtls "
                "NODE_AGENT_CERTS_HOST_PATH=/etc/otel-node-agent/certs "
                "NODE_AGENT_SECRETS_HOST_PATH=/etc/otel-node-agent/secrets "
                "docker compose -f compose.yaml -f config/compose/otlp-hostmetrics.yaml -f config/compose/mtls.yaml up -d"
            ),
            "verification_steps": [
                "Run the enrollment command on the node.",
                "Start the Node Agent with the selected capability profile.",
                "Confirm the Agent appears on the Agents page.",
                "Confirm the Agent status becomes healthy after heartbeat.",
            ],
        }


def main() -> None:
    credentials_file = env_path("ENROLLMENT_CREDENTIALS_FILE")
    issuer = build_issuer()
    server = EnrollmentServer(
        (os.environ.get("ENROLLMENT_BIND", "0.0.0.0"), int(os.environ.get("ENROLLMENT_PORT", "8080"))),
        credentials_file=credentials_file,
        issuer=issuer,
        gateway_ca_bundle=env_path("ENROLLMENT_GATEWAY_CA_BUNDLE"),
        registry=AgentRegistry(
            env_path("ENROLLMENT_REGISTRY_FILE")
            if os.environ.get("ENROLLMENT_REGISTRY_FILE")
            else credentials_file.with_name("agent-registry.json"),
            stale_after_seconds=int(os.environ.get("AGENT_STALE_AFTER_SECONDS", "90")),
            offline_after_seconds=int(os.environ.get("AGENT_OFFLINE_AFTER_SECONDS", "300")),
        ),
        infrastructure=InfrastructureService(PrometheusClient(os.environ.get("PROMETHEUS_URL"))),
        grafana_links=GrafanaLinks(os.environ.get("GRAFANA_URL", "http://localhost:3000")),
        audit_log=Path(os.environ["ENROLLMENT_AUDIT_LOG"]) if os.environ.get("ENROLLMENT_AUDIT_LOG") else None,
        single_tenant_id=os.environ.get("CONTROL_PLANE_TENANT_ID", "tenant-a"),
        operator_token=validate_operator_token(os.environ.get("CONTROL_PLANE_OPERATOR_TOKEN")),
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
