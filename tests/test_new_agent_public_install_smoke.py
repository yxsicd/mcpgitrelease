import pathlib
import os
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class NewAgentPublicInstallSmokeTests(unittest.TestCase):
    def test_existing_paths_and_docker_names_are_rejected_without_cleanup(self):
        for collision in ["bundle", "credentials", "installer", "config", "container", "volume"]:
            with self.subTest(collision=collision), tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory)
                commands = root / "commands"
                commands.mkdir()
                log = root / "commands.log"
                docker = commands / "docker"
                docker.write_text('''#!/bin/bash
echo "$*" >> "$COMMAND_LOG"
[[ "$1 $2" == "$COLLISION inspect" ]]
''')
                docker.chmod(0o755)
                curl = commands / "curl"
                curl.write_text('#!/bin/bash\necho curl >> "$COMMAND_LOG"\nexit 99\n')
                curl.chmod(0o755)
                paths = {
                    "bundle": root / "test-bundle",
                    "credentials": root / "test-creds",
                    "installer": root / "test-install.sh",
                    "config": root / ".mcpgit/instances/test.toml",
                }
                sentinel = paths.get(collision)
                if sentinel is not None:
                    sentinel.parent.mkdir(parents=True, exist_ok=True)
                    sentinel.write_text("preexisting")
                env = dict(os.environ, HOME=str(root), TMPDIR=str(root),
                           PATH=str(commands) + ":" + os.environ["PATH"],
                           COMMAND_LOG=str(log), COLLISION=collision)
                result = subprocess.run(
                    ["bash", str(ROOT / "scripts/new_agent_public_install_smoke.sh"), "--instance", "test"],
                    env=env, capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("existing", result.stderr)
                if sentinel is not None:
                    self.assertEqual(sentinel.read_text(), "preexisting")
                calls = log.read_text() if log.exists() else ""
                self.assertNotIn("rm", calls)
                self.assertNotIn("curl", calls)

    def test_cleanup_requires_matching_container_and_volume_identity(self):
        script = (ROOT / "scripts/new_agent_public_install_smoke.sh").read_text()
        function = script[script.index("cleanup_created() {"):script.index("\ncleanup_sensitive() {")]
        for container, volume, accepted in [
            ("owned-id", "owned-time", True),
            ("replacement-id", "owned-time", False),
            ("owned-id", "replacement-time", False),
        ]:
            with self.subTest(container=container, volume=volume), tempfile.TemporaryDirectory() as directory:
                log = pathlib.Path(directory) / "calls"
                body = '''set -eu
instance=test
created_container_id=owned-id
created_volume_timestamp=owned-time
bundle=bundle credentials=credentials installer=installer instance_config=config
docker() {
  if [[ "$1 $2" == "container inspect" ]]; then echo "$CURRENT_CONTAINER";
  elif [[ "$1 $2" == "volume inspect" ]]; then echo "$CURRENT_VOLUME";
  else echo "docker $*" >> "$COMMAND_LOG"; fi
}
rm() { echo "local rm $*" >> "$COMMAND_LOG"; }
'''
                result = subprocess.run(
                    ["bash", "-c", body + function + "\ncleanup_created\n"],
                    env=dict(os.environ, CURRENT_CONTAINER=container, CURRENT_VOLUME=volume, COMMAND_LOG=str(log)),
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode == 0, accepted)
                calls = log.read_text() if log.exists() else ""
                if accepted:
                    self.assertIn("docker rm -f owned-id", calls)
                    self.assertIn("docker volume rm test_data", calls)
                else:
                    self.assertEqual(calls, "")

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
        self.assertIn("verify_repository_layout.py", script)
        self.assertIn('f"{instance}_data:/data:ro"', script)
        self.assertIn('**layout["checks"]', script)
        self.assertNotIn("cat $credentials", script)
        validate = (ROOT / "scripts" / "validate.sh").read_text(encoding="utf-8")
        self.assertIn("bash -n scripts/new_agent_public_install_smoke.sh", validate)

    def test_release_workflow_installs_before_service_interface_smoke(self):
        workflow = (ROOT / ".github/workflows/release-deployment-smoke.yml").read_text()
        self.assertIn("paths: [offline-latest.json]", workflow)
        self.assertIn("scripts/new_agent_public_install_smoke.sh", workflow)
        self.assertIn("--keep", workflow)
        self.assertIn("scripts/service_interface_smoke.py", workflow)
        self.assertLess(workflow.index("scripts/new_agent_public_install_smoke.sh"), workflow.index("scripts/service_interface_smoke.py"))
        self.assertNotIn("cargo build", workflow)
        self.assertIn("if: always()", workflow)
        probe = (ROOT / "scripts/service_interface_smoke.py").read_text()
        self.assertIn('"SKILL.md"', probe)
        self.assertIn('"service_metadata"', probe)
        self.assertIn('"businessMutationsInvoked": False', probe)
        self.assertIn("sdk/rust/CLIENT_SDK_RELEASE.md", probe)


if __name__ == "__main__":
    unittest.main()
