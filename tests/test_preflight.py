import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class PreflightTests(unittest.TestCase):
    def test_ready_new_install_is_json_and_never_mutates_docker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            bundle = root / "bundle"
            fake_bin = root / "bin"
            bundle.mkdir()
            fake_bin.mkdir()
            binary = bundle / "mcpgit-linux-arm64.tar.gz"
            devbase = bundle / "mcpgit-devbase-linux-arm64.docker.tar.zst"
            deployment = bundle / "mcpgit-deploy.tar.gz"
            binary.write_bytes(b"binary")
            devbase.write_bytes(b"devbase")
            deployment.write_bytes(b"deployment")

            def digest(path: pathlib.Path) -> str:
                return hashlib.sha256(path.read_bytes()).hexdigest()

            (bundle / "install-linux-arm64.env").write_text(
                "\n".join(
                    [
                        "MCPGIT_INSTALL_SCHEMA=mcpgitrelease/install/v1",
                        "MCPGIT_CHANNEL=dev",
                        "MCPGIT_ARCH=arm64",
                        "MCPGIT_BINARY_TAG=mcpgit-test",
                        "MCPGIT_BINARY_REVISION=" + "a" * 40,
                        "MCPGIT_BINARY_FILE=" + binary.name,
                        "MCPGIT_BINARY_URL=https://example.invalid/" + binary.name,
                        "MCPGIT_BINARY_SHA256=" + digest(binary),
                        "MCPGIT_DEVBASE_TAG=devbase-2026.08.1",
                        "MCPGIT_DEVBASE_IMAGE=mcpgit-devbase:devbase-2026.08.1",
                        "MCPGIT_DEVBASE_FILE=" + devbase.name,
                        "MCPGIT_DEVBASE_URL=https://example.invalid/" + devbase.name,
                        "MCPGIT_DEVBASE_SHA256=" + digest(devbase),
                        "MCPGIT_DEPLOY_TAG=deploy-aaaaaaaaaaaa",
                        "MCPGIT_DEPLOY_FILE=" + deployment.name,
                        "MCPGIT_DEPLOY_URL=https://example.invalid/" + deployment.name,
                        "MCPGIT_DEPLOY_SHA256=" + digest(deployment),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            config = root / "mcpgit.toml"
            config.write_text("[service]\n", encoding="utf-8")
            netrc = root / "netrc"
            netrc.write_text("", encoding="utf-8")
            runtime = root / "runtime.env"
            runtime.write_text("", encoding="utf-8")
            docker_log = root / "docker.log"
            docker = fake_bin / "docker"
            docker.write_text(
                """#!/bin/sh
printf '%s\n' "$*" >> "$DOCKER_LOG"
case "$1 $2" in
  "context show") echo default; exit 0 ;;
  "version --format") echo 27.0.0; exit 0 ;;
  "compose version") exit 0 ;;
  "volume inspect") [ "$3" = toolchain ] && exit 0; exit 1 ;;
  "container inspect") exit 1 ;;
  "image inspect") exit 1 ;;
  "network inspect") exit 1 ;;
esac
exit 1
""",
                encoding="utf-8",
            )
            docker.chmod(0o755)
            uname = fake_bin / "uname"
            uname.write_text("#!/bin/sh\necho arm64\n", encoding="utf-8")
            uname.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "PATH": str(fake_bin) + os.pathsep + env["PATH"],
                    "DOCKER_LOG": str(docker_log),
                    "HOME": str(root / "home"),
                }
            )
            result = subprocess.run(
                [
                    str(ROOT / "deploy" / "mcpgit-preflight.sh"),
                    "--bundle",
                    str(bundle),
                    "--instance",
                    "sample",
                    "--config",
                    str(config),
                    "--netrc",
                    str(netrc),
                    "--runtime-env",
                    str(runtime),
                    "--data-source",
                    "sample_data",
                    "--network",
                    "sample_network",
                    "--toolchain-volume",
                    "toolchain",
                    "--no-traefik",
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["schema"], "mcpgitrelease/preflight/v1")
            self.assertTrue(report["ready"])
            self.assertEqual(report["blockers"], [])
            commands = docker_log.read_text(encoding="utf-8")
            for forbidden in [" create", " stop", " start", " rename", " load", " run", " up", " down", " rm"]:
                self.assertNotIn(forbidden, commands)

    def test_existing_instance_without_data_inference_is_a_blocker(self) -> None:
        script = (ROOT / "deploy" / "mcpgit-preflight.sh").read_text(encoding="utf-8")
        self.assertIn("existing /data source cannot be inferred", script)
        self.assertIn("exit 2", script)
        self.assertNotIn("docker volume create", script)
        self.assertNotIn("docker network create", script)
        self.assertNotIn("docker load", script)
        self.assertNotIn("compose up", script)


if __name__ == "__main__":
    unittest.main()
