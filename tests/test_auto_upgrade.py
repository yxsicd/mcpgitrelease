import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("auto_upgrade", ROOT / "scripts" / "auto_upgrade.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

SOURCE = "a" * 40
OLD = "b" * 40
RELEASE = {"source_sha": SOURCE, "manifest_sha256": "c" * 64, "tag": "release", "url": "test"}


class AutoUpgradeTest(unittest.TestCase):
    def args(self):
        return types.SimpleNamespace(instance="demo")

    def test_current_instance_is_a_noop(self):
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(MODULE, "state_root", return_value=Path(directory)), \
             mock.patch.object(MODULE, "pointer", return_value=RELEASE), \
             mock.patch.object(MODULE, "label", return_value=SOURCE), \
             mock.patch.object(MODULE, "run") as runner:
            self.assertEqual(MODULE.one_run(self.args()), 0)
            runner.assert_not_called()
            receipt = json.loads((Path(directory) / "demo.receipt.json").read_text())
            self.assertEqual(receipt["outcome"], "current")

    def test_busy_instance_defers_without_preflight(self):
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(MODULE, "state_root", return_value=Path(directory)), \
             mock.patch.object(MODULE, "pointer", return_value=RELEASE), \
             mock.patch.object(MODULE, "label", return_value=OLD), \
             mock.patch.object(MODULE, "load_per_core", return_value=2.0), \
             mock.patch.object(MODULE, "container_cpu", return_value=5.0), \
             mock.patch.object(MODULE, "run") as runner:
            self.assertEqual(MODULE.one_run(self.args()), 0)
            runner.assert_not_called()
            receipt = json.loads((Path(directory) / "demo.receipt.json").read_text())
            self.assertEqual(receipt["outcome"], "deferred_busy")

    def test_idle_instance_uses_preflight_then_transactional_upgrade(self):
        completed = types.SimpleNamespace(returncode=0, stdout="ok")
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(MODULE, "state_root", return_value=Path(directory)), \
             mock.patch.object(MODULE, "pointer", return_value=RELEASE), \
             mock.patch.object(MODULE, "label", side_effect=[OLD, SOURCE]), \
             mock.patch.object(MODULE, "load_per_core", return_value=0.1), \
             mock.patch.object(MODULE, "container_cpu", return_value=2.0), \
             mock.patch.object(MODULE, "ctl_path", return_value="/bin/mcpgitctl"), \
             mock.patch.object(MODULE, "run", return_value=completed) as runner:
            self.assertEqual(MODULE.one_run(self.args()), 0)
            self.assertEqual(runner.call_args_list[0].args[0][-2:], ["upgrade", "--check"])
            self.assertEqual(runner.call_args_list[1].args[0][-1], "upgrade")
            receipt = json.loads((Path(directory) / "demo.receipt.json").read_text())
            self.assertEqual(receipt["outcome"], "upgraded")
            self.assertEqual(receipt["source_sha"], SOURCE)

    def test_custom_adapter_is_copied_rendered_and_never_uses_a_shell(self):
        completed = types.SimpleNamespace(returncode=0, stdout="ok")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "fleet-upgrade"
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o700)
            adapter = {
                "schema": "mcpgit.auto-upgrade-adapter.v1",
                "preflight_argv": [str(executable), "check", "{instance}", "{tag}"],
                "activate_argv": [str(executable), "apply", "{source_sha}", "{manifest_sha256}"],
            }
            (root / "demo.policy.json").write_text(json.dumps({"adapter": adapter}))
            with mock.patch.object(MODULE, "state_root", return_value=root), \
                 mock.patch.object(MODULE, "pointer", return_value=RELEASE), \
                 mock.patch.object(MODULE, "label", side_effect=[OLD, SOURCE]), \
                 mock.patch.object(MODULE, "load_per_core", return_value=0.1), \
                 mock.patch.object(MODULE, "container_cpu", return_value=2.0), \
                 mock.patch.object(MODULE, "run", return_value=completed) as runner:
                self.assertEqual(MODULE.one_run(self.args()), 0)
            self.assertEqual(runner.call_args_list[0].args[0],
                             [str(executable), "check", "demo", "release"])
            self.assertEqual(runner.call_args_list[1].args[0],
                             [str(executable), "apply", SOURCE, "c" * 64])

    def test_adapter_file_must_be_protected_and_use_known_placeholders(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "adapter.json"
            path.write_text(json.dumps({
                "schema": "mcpgit.auto-upgrade-adapter.v1",
                "preflight_argv": ["/bin/true", "{unknown}"],
                "activate_argv": ["/bin/true"],
            }))
            path.chmod(0o600)
            with self.assertRaises(RuntimeError):
                MODULE.read_adapter(str(path))
            path.write_text(json.dumps({
                "schema": "mcpgit.auto-upgrade-adapter.v1",
                "preflight_argv": ["/bin/true"],
                "activate_argv": ["/bin/true"],
            }))
            path.chmod(0o622)
            with self.assertRaises(RuntimeError):
                MODULE.read_adapter(str(path))


if __name__ == "__main__":
    unittest.main()
