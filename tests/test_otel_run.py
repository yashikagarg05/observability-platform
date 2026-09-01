from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
OTEL_RUN_PATH = ROOT / "collector" / "agent" / "bin" / "otel-run"


def load_otel_run():
    loader = importlib.machinery.SourceFileLoader("otel_run", str(OTEL_RUN_PATH))
    spec = importlib.util.spec_from_loader("otel_run", loader)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {OTEL_RUN_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


otel_run = load_otel_run()


class CaptureServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address, CaptureHandler)
        self.payloads: list[tuple[str, dict[str, Any]]] = []
        self.status_code = 200


class CaptureHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        self.server.payloads.append((self.path, body))  # type: ignore[attr-defined]
        status = getattr(self.server, "status_code", 200)
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()


class OtelRunArgumentTests(unittest.TestCase):
    def test_parse_command_without_options(self) -> None:
        options = otel_run.parse_argv(["npm", "run", "dev"])
        self.assertIsNone(options.service)
        self.assertIsNone(options.endpoint)
        self.assertEqual(options.command, ["npm", "run", "dev"])

    def test_parse_service_and_endpoint(self) -> None:
        options = otel_run.parse_argv(
            ["--service", "orders-api", "--endpoint", "http://127.0.0.1:4318", "npm", "run", "dev"]
        )
        self.assertEqual(options.service, "orders-api")
        self.assertEqual(options.endpoint, "http://127.0.0.1:4318")
        self.assertEqual(options.command, ["npm", "run", "dev"])

    def test_parse_service_and_endpoint_equals_form(self) -> None:
        options = otel_run.parse_argv(
            ["--service=orders-api", "--endpoint=http://127.0.0.1:4318", "npm", "run", "dev"]
        )
        self.assertEqual(options.service, "orders-api")
        self.assertEqual(options.endpoint, "http://127.0.0.1:4318")
        self.assertEqual(options.command, ["npm", "run", "dev"])

    def test_exit_status_maps_signal_to_shell_code(self) -> None:
        self.assertEqual(otel_run._exit_status(0), 0)
        self.assertEqual(otel_run._exit_status(1), 1)
        self.assertEqual(otel_run._exit_status(-signal.SIGTERM), 128 + signal.SIGTERM)
        self.assertEqual(otel_run._exit_status(-signal.SIGINT), 128 + signal.SIGINT)

    def test_parse_separator_keeps_command_flags(self) -> None:
        options = otel_run.parse_argv(["--service", "orders-api", "--", "npm", "run", "dev", "--port", "3000"])
        self.assertEqual(options.service, "orders-api")
        self.assertEqual(options.command, ["npm", "run", "dev", "--port", "3000"])

    def test_parse_does_not_invoke_a_shell(self) -> None:
        options = otel_run.parse_argv(["python", "app.py"])
        self.assertEqual(options.command, ["python", "app.py"])
        self.assertNotEqual(options.command[0], "sh")

    def test_default_service_name_is_command_basename(self) -> None:
        self.assertEqual(otel_run.default_service_name(["/usr/bin/python3", "app.py"], None, {}), "python3")
        self.assertEqual(otel_run.default_service_name(["npm", "run", "dev"], None, {}), "npm")

    def test_service_name_precedence(self) -> None:
        env = {"OTEL_SERVICE_NAME": "from-env"}
        self.assertEqual(otel_run.default_service_name(["npm"], "from-flag", env), "from-flag")
        self.assertEqual(otel_run.default_service_name(["npm"], None, env), "from-env")
        self.assertEqual(otel_run.default_service_name(["npm"], None, {}), "npm")

    def test_endpoint_flag_overrides_env_and_default(self) -> None:
        env = {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://env-endpoint:4318"}
        self.assertEqual(
            otel_run.logs_url("http://flag-endpoint:4318", env),
            "http://flag-endpoint:4318/v1/logs",
        )
        self.assertEqual(otel_run.logs_url(None, env), "http://env-endpoint:4318/v1/logs")
        self.assertEqual(otel_run.logs_url(None, {}), "http://127.0.0.1:4318/v1/logs")

    def test_help_and_missing_command(self) -> None:
        with self.assertRaises(otel_run.HelpRequested):
            otel_run.parse_argv(["--help"])
        with self.assertRaises(otel_run.ParseError):
            otel_run.parse_argv(["--service", "orders-api"])
        with patch("sys.stdout", new=io.StringIO()), patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(otel_run.main(["--help"]), 0)
            self.assertEqual(otel_run.main(["--service", "x"]), 2)


class OtelRunProcessTests(unittest.TestCase):
    def start_server(self, status_code: int = 200) -> tuple[CaptureServer, str, threading.Thread]:
        server = CaptureServer(("127.0.0.1", 0))
        server.status_code = status_code
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        return server, f"http://{host}:{port}", thread

    def stop_server(self, server: CaptureServer) -> None:
        server.shutdown()
        server.server_close()

    def run_otel(self, *args: str, extra_env: dict[str, str] | None = None, timeout: float = 8.0) -> subprocess.CompletedProcess[bytes]:
        env = os.environ.copy()
        env.pop("OTEL_SERVICE_NAME", None)
        env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(OTEL_RUN_PATH), *args],
            capture_output=True,
            env=env,
            timeout=timeout,
        )

    def wait_records(self, server: CaptureServer, minimum: int = 1, timeout: float = 4.0) -> list[dict[str, Any]]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            records = self.records(server)
            if len(records) >= minimum:
                return records
            time.sleep(0.05)
        return self.records(server)

    def records(self, server: CaptureServer) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for _path, body in server.payloads:
            for resource_logs in body.get("resourceLogs", []):
                for scope_logs in resource_logs.get("scopeLogs", []):
                    found.extend(scope_logs.get("logRecords", []))
        return found

    def resource_attrs(self, server: CaptureServer) -> dict[str, str]:
        attrs: dict[str, str] = {}
        for _path, body in server.payloads:
            for resource_logs in body.get("resourceLogs", []):
                for item in resource_logs.get("resource", {}).get("attributes", []):
                    attrs[item["key"]] = item["value"]["stringValue"]
        return attrs

    def attr_map(self, record: dict[str, Any]) -> dict[str, str]:
        return {item["key"]: item["value"]["stringValue"] for item in record.get("attributes", [])}

    def test_stdout_otlp_payload_and_terminal_output(self) -> None:
        server, endpoint, _thread = self.start_server()
        try:
            result = self.run_otel(
                "--service",
                "orders-api",
                "--endpoint",
                endpoint,
                "--",
                sys.executable,
                "-c",
                "print('hello-stdout')",
                extra_env={
                    "OTEL_SERVICE_NAMESPACE": "my-team",
                    "OTEL_DEPLOYMENT_ENVIRONMENT": "local",
                },
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn(b"hello-stdout", result.stdout)
            self.assertEqual(server.payloads[0][0], "/v1/logs")
            records = self.wait_records(server, 1)
            self.assertTrue(records)
            matching = [record for record in records if record["body"]["stringValue"] == "hello-stdout"]
            self.assertEqual(len(matching), 1)
            record = matching[0]
            self.assertEqual(record["severityText"], "INFO")
            self.assertEqual(record["severityNumber"], 9)
            self.assertIsInstance(record["timeUnixNano"], str)
            self.assertTrue(record["timeUnixNano"].isdigit())
            self.assertGreater(int(record["timeUnixNano"]), 0)
            self.assertEqual(self.attr_map(record)["log.source.type"], "process")
            self.assertEqual(self.attr_map(record)["log.iostream"], "stdout")
            self.assertEqual(
                self.resource_attrs(server),
                {
                    "service.name": "orders-api",
                    "service.namespace": "my-team",
                    "deployment.environment": "local",
                },
            )
        finally:
            self.stop_server(server)


    def test_final_line_without_newline_is_flushed_on_shutdown(self) -> None:
        server, endpoint, _thread = self.start_server()
        try:
            result = self.run_otel(
                "--endpoint",
                endpoint,
                "--",
                sys.executable,
                "-c",
                "import sys; sys.stdout.write('one\\ntwo\\nthree-no-nl'); sys.stdout.flush()",
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"one\ntwo\nthree-no-nl")
            records = self.wait_records(server, 3)
            bodies = [record["body"]["stringValue"] for record in records]
            self.assertEqual(bodies, ["one", "two", "three-no-nl"])
        finally:
            self.stop_server(server)

    def test_queue_full_drops_and_warns_once(self) -> None:
        exporter = otel_run.LogExporter("http://127.0.0.1:1/v1/logs", "svc", {})
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            for index in range(otel_run.QUEUE_MAXSIZE):
                exporter.enqueue("stdout", f"line-{index}")
            exporter.enqueue("stdout", "overflow-1")
            exporter.enqueue("stdout", "overflow-2")
        self.assertEqual(exporter.queue.qsize(), otel_run.QUEUE_MAXSIZE)
        self.assertEqual(stderr.getvalue().count("otel-run: warning: OTLP log queue full; dropping logs"), 1)

    def test_http_503_fails_open(self) -> None:
        server, endpoint, _thread = self.start_server(status_code=503)
        try:
            result = self.run_otel(
                "--endpoint",
                endpoint,
                "--",
                sys.executable,
                "-c",
                "print('still-running'); raise SystemExit(0)",
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn(b"still-running", result.stdout)
            self.assertEqual(result.stderr.count(b"otel-run: warning: OTLP log export failed"), 1)
        finally:
            self.stop_server(server)

    def test_missing_command_exits_127(self) -> None:
        result = self.run_otel("--endpoint", "http://127.0.0.1:1", "--", "otel-run-command-that-does-not-exist")
        self.assertEqual(result.returncode, 127)
        self.assertIn(b"command not found", result.stderr)

    def test_non_executable_command_exits_126(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_otel("--endpoint", "http://127.0.0.1:1", "--", tmp)
        self.assertEqual(result.returncode, 126)
        self.assertIn(b"failed to start", result.stderr)

    def test_child_terminated_by_signal_uses_shell_exit_status(self) -> None:
        server, endpoint, _thread = self.start_server()
        child_script = "import os, time\nprint('pid', os.getpid(), flush=True)\ntime.sleep(60)\n"
        env = os.environ.copy()
        proc = subprocess.Popen(
            [
                sys.executable,
                str(OTEL_RUN_PATH),
                "--endpoint",
                endpoint,
                "--",
                sys.executable,
                "-c",
                child_script,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        child_pid = None
        try:
            assert proc.stdout is not None
            line = proc.stdout.readline().decode("utf-8", errors="replace")
            self.assertTrue(line.startswith("pid "), line)
            child_pid = int(line.split()[1])
            proc.send_signal(signal.SIGTERM)
            self.assertEqual(proc.wait(timeout=5), 128 + signal.SIGTERM)
            with self.assertRaises(ProcessLookupError):
                os.kill(child_pid, 0)
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGKILL)
                proc.wait(timeout=3)
            if proc.stdout is not None:
                proc.stdout.close()
            if proc.stderr is not None:
                proc.stderr.close()
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.stop_server(server)

    def test_stderr_otlp_payload(self) -> None:
        server, endpoint, _thread = self.start_server()
        try:
            result = self.run_otel(
                "--endpoint",
                endpoint,
                "--",
                sys.executable,
                "-c",
                "import sys; print('hello-stderr', file=sys.stderr)",
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn(b"hello-stderr", result.stderr)
            records = self.wait_records(server, 1)
            matching = [record for record in records if record["body"]["stringValue"] == "hello-stderr"]
            self.assertEqual(len(matching), 1)
            record = matching[0]
            self.assertEqual(record["severityText"], "ERROR")
            self.assertEqual(record["severityNumber"], 17)
            self.assertEqual(self.attr_map(record)["log.source.type"], "process")
            self.assertEqual(self.attr_map(record)["log.iostream"], "stderr")
        finally:
            self.stop_server(server)

    def test_child_exit_code_zero_and_one(self) -> None:
        server, endpoint, _thread = self.start_server()
        try:
            zero = self.run_otel("--endpoint", endpoint, "--", sys.executable, "-c", "raise SystemExit(0)")
            one = self.run_otel("--endpoint", endpoint, "--", sys.executable, "-c", "raise SystemExit(1)")
            self.assertEqual(zero.returncode, 0)
            self.assertEqual(one.returncode, 1)
        finally:
            self.stop_server(server)

    def test_otlp_failure_does_not_change_child_exit_code(self) -> None:
        server, endpoint, _thread = self.start_server(status_code=503)
        try:
            result = self.run_otel(
                "--endpoint",
                endpoint,
                "--",
                sys.executable,
                "-c",
                "print('still-running'); raise SystemExit(1)",
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"still-running", result.stdout)
            self.assertIn(b"otel-run: warning: OTLP log export failed", result.stderr)
        finally:
            self.stop_server(server)

        refused = self.run_otel(
            "--endpoint",
            "http://127.0.0.1:1",
            "--",
            sys.executable,
            "-c",
            "print('still-running'); raise SystemExit(0)",
        )
        self.assertEqual(refused.returncode, 0)
        self.assertIn(b"still-running", refused.stdout)
        self.assertIn(b"otel-run: warning: OTLP log export failed", refused.stderr)

    def test_default_service_name_in_payload(self) -> None:
        server, endpoint, _thread = self.start_server()
        try:
            result = self.run_otel("--endpoint", endpoint, "--", sys.executable, "-c", "print('named')")
            self.assertEqual(result.returncode, 0)
            self.wait_records(server, 1)
            self.assertEqual(self.resource_attrs(server)["service.name"], Path(sys.executable).name)
        finally:
            self.stop_server(server)

    def test_signal_forwarding_uses_process_group(self) -> None:
        proc = MagicMock()
        proc.poll.return_value = None
        proc.pid = 4242
        holder = {"proc": proc}
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with patch.object(otel_run.os, "killpg") as killpg:
                otel_run._forward_signal(signum, holder)
                killpg.assert_called_once_with(4242, signum)

    def test_signal_forwarding_and_process_cleanup(self) -> None:
        server, endpoint, _thread = self.start_server()
        child_script = (
            "import os, signal, sys, time\n"
            "signal.signal(signal.SIGINT, lambda *_: sys.exit(0))\n"
            "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))\n"
            "signal.signal(signal.SIGHUP, lambda *_: sys.exit(0))\n"
            "print('pid', os.getpid(), flush=True)\n"
            "time.sleep(60)\n"
        )
        env = os.environ.copy()
        proc = subprocess.Popen(
            [
                sys.executable,
                str(OTEL_RUN_PATH),
                "--endpoint",
                endpoint,
                "--",
                sys.executable,
                "-c",
                child_script,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        child_pid = None
        try:
            assert proc.stdout is not None
            line = proc.stdout.readline().decode("utf-8", errors="replace")
            self.assertTrue(line.startswith("pid "), line)
            child_pid = int(line.split()[1])
            proc.send_signal(signal.SIGINT)
            self.assertEqual(proc.wait(timeout=5), 0)
            with self.assertRaises(ProcessLookupError):
                os.kill(child_pid, 0)
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGKILL)
                proc.wait(timeout=3)
            if proc.stdout is not None:
                proc.stdout.close()
            if proc.stderr is not None:
                proc.stderr.close()
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.stop_server(server)


if __name__ == "__main__":
    unittest.main()
