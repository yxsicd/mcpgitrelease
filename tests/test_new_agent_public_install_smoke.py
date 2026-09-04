import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class NewAgentPublicInstallSmokeTests(unittest.TestCase):
    def test_public_install_smoke_checks_new_agent_initialization_without_secret_leaks(self):
        script = (ROOT / "scripts" / "new_agent_public_install_smoke.sh").read_text(encoding="utf-8")
        self.assertIn("raw.githubusercontent.com/yxsicd/mcpgitrelease/main/install.sh", script)
        self.assertIn("mcp_probe", script)
        self.assertIn("tools/list", script)
        self.assertIn("credentials_mode_0600", script)
        self.assertIn("release_identity_match", script)
        self.assertIn("credentials_dir", script)
        self.assertIn('glob(os.path.join(credentials_dir, "*"))', script)
        self.assertIn("cleanup_sensitive", script)
        self.assertIn("cleanup_failed_sensitive", script)
        self.assertIn(".mcpgit/instances", script)
        self.assertIn('rm -f -- "$instance_config"', script)
        self.assertIn("source_label == expected", script)
        self.assertIn("release_id == f\"git-{expected}\"", script)
        self.assertIn("program_version == f\"git-{expected}\"", script)
        self.assertIn("expected in image", script)
        self.assertIn("redact_log", script)
        self.assertNotIn("cat $credentials", script)
        validate = (ROOT / "scripts" / "validate.sh").read_text(encoding="utf-8")
        self.assertIn("bash -n scripts/new_agent_public_install_smoke.sh", validate)


if __name__ == "__main__":
    unittest.main()
