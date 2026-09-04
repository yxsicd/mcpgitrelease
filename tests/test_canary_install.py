import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class CanaryInstallScriptTests(unittest.TestCase):
    def test_canary_has_post_install_wait_and_no_restart_gate(self):
        script = (ROOT / "scripts" / "canary_install.sh").read_text(encoding="utf-8")
        self.assertIn("wait_healthy", script)
        self.assertIn("mcpgitctl", script)
        self.assertIn("exact_current_no_restart", script)
        self.assertIn('[[ "$cid1" == "$cid2" ]]', script)
        self.assertIn('[[ "$created1" == "$created2" ]]', script)
        self.assertIn("Credentials are never", script)
        self.assertNotIn("cat $credential", script)
        validate = (ROOT / "scripts" / "validate.sh").read_text(encoding="utf-8")
        self.assertIn("bash -n scripts/canary_install.sh", validate)


if __name__ == "__main__":
    unittest.main()
