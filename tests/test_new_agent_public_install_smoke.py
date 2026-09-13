import pathlib
import os
import subprocess
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class NewAgentPublicInstallSmokeTests(unittest.TestCase):
    def test_candidate_identity_is_validated_before_any_external_action(self):
        source = "a" * 40
        good_tag = f"mcpgit-git-{source}-linux-amd64"
        for arguments in [
            ["--release-tag", good_tag],
            ["--manifest-sha256", "b" * 64],
            ["--expected-source-sha", source, "--release-tag", good_tag, "--manifest-sha256", "bad"],
            ["--expected-source-sha", "c" * 40, "--release-tag", good_tag, "--manifest-sha256", "b" * 64],
            ["--install-revision", "main"],
        ]:
            with self.subTest(arguments=arguments):
                result = subprocess.run(["bash", str(ROOT / "scripts/new_agent_public_install_smoke.sh"), *arguments],
                                        capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("new-agent-smoke:", result.stderr)
                self.assertNotIn("fetched public installer", result.stdout)

    def test_candidate_workflow_pins_both_native_architectures_without_promotion(self):
        workflow = (ROOT / ".github/workflows/release-deployment-smoke.yml").read_text()
        for text in ["ubuntu-24.04-arm", "amd64_manifest_sha256", "arm64_manifest_sha256",
                     "--release-tag", "--manifest-sha256", '--install-revision "$GITHUB_SHA"',
                     ".architectures[$platform].manifest_sha256", "docker restart", "contents: read"]:
            self.assertIn(text, workflow)
        self.assertIn("scripts/agent_onboarding_probe.py", workflow)
        self.assertIn("restart-authenticated-agent.json", workflow)
        install_step = workflow[workflow.index("      - name: Install exact immutable package"):workflow.index("      - name: Discover and smoke")]
        self.assertIn("TMPDIR: ${{ runner.temp }}", install_step)
        self.assertIn('$RUNNER_TEMP/${INSTANCE}-creds/${INSTANCE}-systemadmin.env', workflow)
        self.assertNotIn("--write-probe", workflow)
        self.assertNotIn("git push", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("yxsicd/MCPGit", workflow)
        self.assertNotIn("MCPGIT_DEPLOY_KEY", workflow)
        script = (ROOT / "scripts/new_agent_public_install_smoke.sh").read_text()
        self.assertIn('MCPGIT_RELEASE_TAG="$release_tag"', script)
        self.assertIn('MCPGIT_EXPECTED_MANIFEST_SHA256="$manifest_sha256"', script)
        self.assertIn('MCPGIT_INSTALL_REVISION="$install_revision"', script)

    def test_wasmc_offline_workflow_checks_exact_image_without_data_or_network(self):
        workflow = (ROOT / ".github/workflows/release-deployment-smoke.yml").read_text()
        step = workflow[workflow.index("      - name: Verify complete bundled WAsmC"):workflow.index("      - name: Discover and smoke")]
        self.assertLess(workflow.index("--keep"), workflow.index("      - name: Verify complete bundled WAsmC"))
        for expected in [
            "docker inspect", "{{.Image}}", "{{.Architecture}}", "org.opencontainers.image.revision",
            "docker run --rm --network none --read-only", "--tmpfs /tmp:rw,noexec,nosuid,size=32m",
            '--entrypoint /opt/mcpgit/tools/bin/node "$image_id"',
            "/opt/mcpgit/tools/verify-wasmc-offline.mjs /opt/mcpgit/tools/wasmc",
            "wasmc-offline-integrity.json", "mcpgit.wasmc-source-free-offline-integrity.v1",
            ".ok == true", ".compiler_wasm_valid == true", ".file_count_and_modes_verified == true",
            ".network_requests == false", ".application_queries_or_imports == false",
        ]:
            self.assertIn(expected, step)
        for forbidden in ["--volume", "--mount", "--env", "-v ", ":/data", "credential-file",
                          "cargo", "rustc", "validate-integrity.mjs", "git clone", "curl", "wget"]:
            self.assertNotIn(forbidden, step)
        self.assertNotIn("yxsicd/MCPGit", workflow)
        self.assertNotIn("MCPGIT_DEPLOY_KEY", workflow)
        producer = (ROOT / "Dockerfile.offline-runtime").read_text()
        self.assertIn('org.opencontainers.image.revision="${MCPGIT_SOURCE_SHA}"', producer)
        self.assertNotIn('"com.yxsicd.mcpgit.source-sha"', step)

    def test_offline_step_executes_with_oci_revision_and_fails_closed(self):
        workflow = (ROOT / ".github/workflows/release-deployment-smoke.yml").read_text()
        step = workflow[workflow.index("      - name: Verify complete bundled WAsmC"):workflow.index("      - name: Discover and smoke")]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])
        mock = r'''
docker() {
  case "$1 $2" in
    "inspect test") printf 'sha256:%064d\n' 1 ;;
    "image inspect")
      case "$5" in
        '{{.Architecture}}') printf '%s\n' "$ARCH" ;;
        '{{index .Config.Labels "org.opencontainers.image.revision"}}') printf '%s\n' "$MOCK_REVISION" ;;
        *) return 90 ;;
      esac ;;
    "run --rm")
      printf 'invoked\n' >> "$RUNNER_TEMP/invocations"
      [[ "$MOCK_CASE" != utility-error ]] || return 91
      printf '{"schema":"mcpgit.wasmc-source-free-offline-integrity.v1","ok":%s,"compiler_wasm_valid":true,"file_count_and_modes_verified":true,"network_requests":false,"application_queries_or_imports":false}\n' "$MOCK_OK" ;;
    *) return 92 ;;
  esac
}
'''
        for arch in ["amd64", "arm64"]:
            for case in ["valid", "wrong-source", "utility-error", "invalid-report"]:
                with self.subTest(arch=arch, case=case), tempfile.TemporaryDirectory() as directory:
                    root = pathlib.Path(directory)
                    (root / "mcpgit-release-smoke").mkdir()
                    env = dict(os.environ, RUNNER_TEMP=directory, INSTANCE="test", ARCH=arch,
                               SOURCE_SHA="a" * 40, MOCK_CASE=case,
                               MOCK_REVISION=("b" if case == "wrong-source" else "a") * 40,
                               MOCK_OK="false" if case == "invalid-report" else "true")
                    result = subprocess.run(["bash", "-c", mock + script], env=env,
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode == 0, case == "valid", result.stderr)
                    self.assertEqual((root / "invocations").exists(), case != "wrong-source")

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
