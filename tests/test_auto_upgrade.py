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


if __name__ == "__main__":
    unittest.main()
