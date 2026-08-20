from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "enrollment"))

import enrollment_api  # noqa: E402


class AgentRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = enrollment_api.AgentRegistry(Path(self.tmp.name) / "agent-registry.json", stale_after_seconds=60, offline_after_seconds=300)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def add_agent(self, agent_id: str = "agent-1", *, expires_at: float | None = None) -> dict[str, object]:
        return self.registry.upsert_from_enrollment(
            agent_id=agent_id,
            tenant_id="tenant-a",
            site_id="site-1",
            environment="validation",
            host_name=f"{agent_id}.example",
            agent_version="1.1.0",
            capabilities=["otlp", "hostmetrics"],
            agent_uri=f"spiffe://observability.local/tenant/tenant-a/site/site-1/environment/validation/agent/{agent_id}",
            fingerprint=f"fingerprint-{agent_id}",
            certificate_serial=f"serial-{agent_id}",
            certificate_issuer="test-issuer",
            certificate_issued_at=time.time() - 60,
            certificate_expires_at=expires_at or time.time() + 60 * 24 * 60 * 60,
        )

    def test_enrolled_agent_is_offline_until_heartbeat_then_can_be_disabled(self) -> None:
        enrolled = self.add_agent()
        self.assertEqual(enrolled["status"], "offline")
        self.assertEqual(enrolled["certificate_status"], "valid")

        heartbeat = self.registry.heartbeat("agent-1", {"host_name": "node-1", "agent_version": "1.1.1"})
        self.assertEqual(heartbeat["status"], "healthy")
        self.assertEqual(heartbeat["host_name"], "node-1")
        self.assertEqual(heartbeat["agent_version"], "1.1.1")

        disabled = self.registry.set_disabled("agent-1", True, "maintenance")
        self.assertEqual(disabled["status"], "disabled")
        self.assertEqual(disabled["certificate_status"], "disabled")

        with self.assertRaises(PermissionError):
            self.registry.heartbeat("agent-1", {})

    def test_list_agents_filters_by_tenant_site_environment_and_status(self) -> None:
        self.add_agent("agent-1")
        self.add_agent("agent-2")
        self.registry.heartbeat("agent-2", {})

        healthy = self.registry.list_agents({"tenant_id": "tenant-a", "site_id": "", "environment": "", "status": "healthy"})
        offline = self.registry.list_agents({"tenant_id": "tenant-a", "site_id": "", "environment": "", "status": "offline"})

        self.assertEqual([agent["agent_id"] for agent in healthy], ["agent-2"])
        self.assertEqual([agent["agent_id"] for agent in offline], ["agent-1"])

    def test_certificate_status_reports_expiring_and_expired(self) -> None:
        expiring = self.add_agent("expiring", expires_at=time.time() + 5 * 24 * 60 * 60)
        expired = self.add_agent("expired", expires_at=time.time() - 60)

        self.assertEqual(expiring["certificate_status"], "expiring_soon")
        self.assertEqual(expired["certificate_status"], "expired")


class EnrollmentHelperTests(unittest.TestCase):
    def test_parse_agent_uri_extracts_identity_fields(self) -> None:
        parsed = enrollment_api.parse_agent_uri(
            "spiffe://observability.local/tenant/tenant-a/site/site-1/environment/production/agent/agent-1"
        )

        self.assertEqual(
            parsed,
            {
                "tenant_id": "tenant-a",
                "site_id": "site-1",
                "environment": "production",
                "agent_id": "agent-1",
            },
        )

    def test_validate_csr_rejects_private_key_material_before_openssl(self) -> None:
        private_key_marker = "PRIVATE" + " KEY"
        with self.assertRaisesRegex(ValueError, "private key"):
            enrollment_api.validate_csr(f"not-a-csr containing {private_key_marker} material")

    def test_external_issuer_mode_fails_closed_without_command(self) -> None:
        with patch.dict(os.environ, {"ENROLLMENT_ISSUER_MODE": "external", "ENROLLMENT_PRODUCTION_ISSUER_COMMAND": ""}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "ENROLLMENT_PRODUCTION_ISSUER_COMMAND is required"):
                enrollment_api.build_issuer()

    def test_development_issuer_requires_explicit_allow_flag(self) -> None:
        with patch.dict(os.environ, {"ENROLLMENT_ISSUER_MODE": "development"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "ENROLLMENT_ALLOW_DEVELOPMENT_ISSUER=true"):
                enrollment_api.build_issuer()

    def test_operator_token_rejects_placeholders_and_short_values(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "replaced"):
            enrollment_api.validate_operator_token("changeme-long-random-operator-token")
        with self.assertRaisesRegex(RuntimeError, "at least 32"):
            enrollment_api.validate_operator_token("short-token")
        self.assertEqual(enrollment_api.validate_operator_token("a" * 32), "a" * 32)

    def test_cors_origin_fails_closed_when_operator_auth_is_enabled(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(enrollment_api.control_plane_cors_origin(None), "*")
            self.assertIsNone(enrollment_api.control_plane_cors_origin("a" * 32))
        with patch.dict(os.environ, {"FRONTEND_CORS_ORIGIN": "http://localhost:4173"}, clear=True):
            self.assertEqual(enrollment_api.control_plane_cors_origin("a" * 32), "http://localhost:4173")


if __name__ == "__main__":
    unittest.main()
