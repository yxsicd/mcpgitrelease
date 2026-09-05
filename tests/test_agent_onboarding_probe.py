import base64
import importlib.util
import json
import pathlib
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("agent_probe", ROOT / "scripts/agent_onboarding_probe.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)
INSTANCE = "11111111-1111-4111-8111-111111111111"
SECRET = "fixture-random-do-not-log"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(request)
        authenticated = self.headers.get("Authorization") == "Basic " + base64.b64encode(
            ("systemadmin:" + SECRET).encode()).decode()
        method = request["method"]
        result = {}
        if method == "initialize":
            result = {"protocolVersion": "2025-11-25"}
        elif method == "tools/list":
            names = sorted(probe.KERNEL)
            result = {"tools": [{"name": n} for n in names[:self.server.tool_count]]}
        elif method == "tools/call":
            name = request["params"]["name"]
            args = request["params"]["arguments"]
            if name == "service_metadata":
                value = {"instance_id": self.server.instance_id}
            elif name == "person_status":
                if not authenticated:
                    result = {"isError": True, "structuredContent": {"outcome": "error", "secret": SECRET}}
                    value = None
                else:
                    value = {"outcome": "authenticated_person", "selected_person": {
                        "handle": "systemadmin", "person_id": "22222222-2222-4222-8222-222222222222"}}
            elif name == "skill_get":
                op = args["operation"]
                value = {"skill": {"summary": {"skill_version": "2.2.0"}, "operations": [
                    {"name": op, "access_lane": "write" if op == "write_file" else "read"}]}}
            else:
                op = args["operation"]
                inner = args["arguments"]
                if op == "repo_status":
                    data = {"dirty": False, "head": "a" * 40}
                elif op == "wasmc_status":
                    data = {"outcome": "ready", "compiler_mode": "embedded_offline",
                            "offline_sdk_available": self.server.sdk_available, "release_tag": "v0.0.4"}
                elif op == "write_file":
                    self.server.files[inner["path"]] = inner["content"]
                    data = {"revision": "b" * 40}
                elif op == "read_file":
                    data = {"content": self.server.files.get(inner["path"]) if not self.server.corrupt else "bad"}
                else:
                    raise AssertionError("unexpected probe operation")
                value = {"outcome": "executed", "result": data}
            if value is not None:
                result = {"isError": False, "structuredContent": value}
        self.send_response(202 if method == "notifications/initialized" else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Mcp-Session-Id", "probe-session")
        self.end_headers()
        if method != "notifications/initialized":
            self.wfile.write(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}).encode())


class AgentProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.credential = pathlib.Path(self.tmp.name) / "instance.env"
        self.credential.write_text("MCPGIT_BASIC_USERNAME=systemadmin\nMCPGIT_BASIC_VERIFY=" + SECRET + "\n")
        self.credential.chmod(0o600)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.requests, self.server.files = [], {}
        self.server.instance_id, self.server.tool_count = INSTANCE, 8
        self.server.sdk_available, self.server.corrupt = True, False
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.tmp.cleanup()

    def test_default_is_real_http_authenticated_but_read_only(self):
        report = probe.probe(self.url, self.credential, INSTANCE)
        self.assertTrue(report["ok"])
        self.assertEqual(self.server.files, {})
        self.assertNotIn(SECRET, json.dumps(report))
        bodies = json.dumps(self.server.requests)
        self.assertNotIn(SECRET, bodies)
        self.assertNotIn("basic_verify", bodies)
        self.assertNotIn("repo_list", bodies)

    def test_explicit_write_commits_and_reads_unique_scoped_file(self):
        report = probe.probe(self.url, self.credential, INSTANCE, True)
        self.assertTrue(report["checks"]["committed_write_readback"])
        self.assertTrue(report["probe_path"].startswith("acceptance/agent-probe-"))
        self.assertEqual(len(self.server.files), 1)

    def test_identity_mismatch_stops_before_write(self):
        self.server.instance_id = "33333333-3333-4333-8333-333333333333"
        with self.assertRaisesRegex(probe.ProbeError, "identity mismatch"):
            probe.probe(self.url, self.credential, INSTANCE, True)
        self.assertEqual(self.server.files, {})

    def test_invalid_credential_is_not_guest_success_and_is_not_echoed(self):
        self.credential.write_text("MCPGIT_BASIC_USERNAME=systemadmin\nMCPGIT_BASIC_VERIFY=invalid\n")
        with self.assertRaises(probe.ProbeError) as caught:
            probe.probe(self.url, self.credential, INSTANCE)
        self.assertNotIn(SECRET, str(caught.exception))

    def test_private_regular_credential_is_required(self):
        self.credential.chmod(0o644)
        with self.assertRaises(probe.ProbeError):
            probe.credentials(self.credential)
        self.credential.chmod(0o600)
        link = self.credential.with_name("link.env")
        link.symlink_to(self.credential)
        with self.assertRaises(probe.ProbeError):
            probe.credentials(link)

    def test_wrong_kernel_and_missing_sdk_fail_closed(self):
        self.server.tool_count = 7
        with self.assertRaisesRegex(probe.ProbeError, "Kernel"):
            probe.probe(self.url, self.credential, INSTANCE)
        self.server.tool_count, self.server.sdk_available = 8, False
        with self.assertRaisesRegex(probe.ProbeError, "WAsmC"):
            probe.probe(self.url, self.credential, INSTANCE)

    def test_failed_readback_cannot_be_success(self):
        self.server.corrupt = True
        with self.assertRaisesRegex(probe.ProbeError, "readback"):
            probe.probe(self.url, self.credential, INSTANCE, True)

    def test_urls_and_event_stream_heartbeat_are_bounded(self):
        for url in ("http://remote.invalid", "https://user:password@example.invalid", "https://host.invalid/?secret=1"):
            with self.assertRaises(probe.ProbeError):
                probe.endpoint(url)
        self.assertEqual(probe.decode(': heartbeat\n\ndata: \ndata: {"ok":true}\n\n'), {"ok": True})


if __name__ == "__main__":
    unittest.main()
