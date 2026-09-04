import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fleet_ledger", ROOT / "scripts/fleet_ledger.py")
fleet_ledger = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(fleet_ledger)


class FleetLedgerTests(unittest.TestCase):
    def test_container_record_redacts_env_and_reports_drift(self):
        pointer = {
            "schema": "mcpgit.offline-pointer.v1",
            "source_sha": "a" * 40,
            "tags": {"linux-arm64": "mcpgit-git-" + "a" * 40 + "-linux-arm64"},
        }
        container = {
            "Id": "1234567890abcdef",
            "Name": "/prodmcpgit",
            "Image": "sha256:" + "b" * 64,
            "RestartCount": 2,
            "Config": {
                "Image": "mcpgit-offline-runtime:git-" + "b" * 40,
                "Env": ["SECRET=must-not-leak"],
                "Labels": {
                    "com.yxsicd.mcpgit.binary-revision": "b" * 40,
                    "com.yxsicd.mcpgit.manifest-sha256": "c" * 64,
                    "private.secret": "must-not-leak",
                },
            },
            "State": {"Status": "running", "Health": {"Status": "healthy"}},
            "NetworkSettings": {"Ports": {"8001/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8001"}]}},
            "Mounts": [
                {"Destination": "/data", "Type": "volume", "Name": "prodmcpgit_data", "Source": "/secret/path"},
                {"Destination": "/root/.netrc", "Type": "bind", "Source": "/Users/me/.netrc"},
            ],
        }
        record = fleet_ledger.container_record(container, pointer)
        self.assertEqual(record["id"], "1234567890ab")
        self.assertEqual(record["kind"], "runtime")
        self.assertEqual(record["public_latest"], "drift")
        self.assertEqual(record["mounts"]["data"]["name"], "prodmcpgit_data")
        self.assertTrue(record["mounts"]["netrc_mounted"])
        self.assertNotIn("Env", record)
        self.assertNotIn("private.secret", record["labels"])

    def test_public_latest_match_accepts_label_source(self):
        pointer = {"source_sha": "a" * 40, "tags": {}}
        labels = {"binary-revision": "a" * 40}
        self.assertEqual(
            fleet_ledger.public_latest_match("mcpgit-offline-runtime:git-" + "a" * 40, labels, pointer),
            "match",
        )

    def test_support_containers_are_not_public_latest_drift(self):
        self.assertEqual(
            fleet_ledger.public_latest_match("prom/prometheus:v3.13.1", {}, {"source_sha": "a" * 40}),
            "not_applicable",
        )


if __name__ == "__main__":
    unittest.main()
