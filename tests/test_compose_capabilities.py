from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector" / "agent" / "tools"))

import compose_capabilities  # noqa: E402


class ComposeCapabilitiesTests(unittest.TestCase):
    def test_generated_profiles_match_manifests(self) -> None:
        manifests = sorted(compose_capabilities.PROFILES.glob("*.json"))
        self.assertGreater(len(manifests), 0)

        for manifest in manifests:
            name = manifest.stem
            with self.subTest(profile=name):
                self.assertEqual(
                    compose_capabilities.generate(name),
                    (compose_capabilities.OUTPUT / f"{name}.yaml").read_text(),
                )
                self.assertEqual(
                    compose_capabilities.generate(name, exporter="gateway-mtls"),
                    (compose_capabilities.OUTPUT / f"{name}-mtls.yaml").read_text(),
                )

    def test_docker_file_hostmetrics_profile_includes_expected_receivers(self) -> None:
        generated = compose_capabilities.generate("docker-file-hostmetrics")

        self.assertIn("docker_observer", generated)
        self.assertIn("receiver_creator/docker", generated)
        self.assertIn("file_log/application", generated)
        self.assertIn("host_metrics", generated)
        self.assertIn("receivers: [host_metrics, otlp]", generated)

    def test_mtls_exporter_variant_uses_mtls_exporter(self) -> None:
        generated = compose_capabilities.generate("otlp", exporter="gateway-mtls")

        self.assertIn("common/exporters/gateway-mtls.yaml", generated)
        self.assertNotIn("docker_observer", generated)
        self.assertNotIn("host_metrics", generated)

    def test_invalid_manifest_rejects_unknown_duplicate_or_missing_otlp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles = Path(tmp)

            (profiles / "unknown.json").write_text(json.dumps({"capabilities": ["otlp", "unknown"]}))
            (profiles / "duplicate.json").write_text(json.dumps({"capabilities": ["otlp", "otlp"]}))
            (profiles / "missing-otlp.json").write_text(json.dumps({"capabilities": ["docker"]}))

            with patch.object(compose_capabilities, "PROFILES", profiles):
                with self.assertRaisesRegex(ValueError, "invalid capabilities"):
                    compose_capabilities.generate("unknown")
                with self.assertRaisesRegex(ValueError, "invalid capabilities"):
                    compose_capabilities.generate("duplicate")
                with self.assertRaisesRegex(ValueError, "must include otlp"):
                    compose_capabilities.generate("missing-otlp")


if __name__ == "__main__":
    unittest.main()
