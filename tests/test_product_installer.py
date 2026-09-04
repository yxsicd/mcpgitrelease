import json
import hashlib
import io
import os
import pathlib
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ProductInstallerTests(unittest.TestCase):
    def test_docker_save_identity_accepts_config_and_oci_manifest_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            archive = root / "base.tar.gz"
            tag = "mcpgit-offline-base:bookworm-v1-amd64"
            config = b'{"architecture":"amd64","os":"linux"}'
            config_sha = hashlib.sha256(config).hexdigest()
            oci_manifest = json.dumps(
                {
                    "schemaVersion": 2,
                    "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "config": {
                        "mediaType": "application/vnd.oci.image.config.v1+json",
                        "digest": f"sha256:{config_sha}",
                        "size": len(config),
                    },
                    "layers": [],
                },
                separators=(",", ":"),
            ).encode()
            manifest_sha = hashlib.sha256(oci_manifest).hexdigest()
            docker_manifest = json.dumps(
                [
                    {
                        "Config": f"blobs/sha256/{config_sha}",
                        "RepoTags": [tag],
                        "Layers": [],
                    }
                ],
                separators=(",", ":"),
            ).encode()
            index = json.dumps(
                {
                    "schemaVersion": 2,
                    "mediaType": "application/vnd.oci.image.index.v1+json",
                    "manifests": [
                        {
                            "mediaType": "application/vnd.oci.image.manifest.v1+json",
                            "digest": f"sha256:{manifest_sha}",
                            "size": len(oci_manifest),
                        }
                    ],
                },
                separators=(",", ":"),
            ).encode()

            with tarfile.open(archive, "w:gz") as bundle:
                for name, data in [
                    ("manifest.json", docker_manifest),
                    ("index.json", index),
                    (f"blobs/sha256/{config_sha}", config),
                    (f"blobs/sha256/{manifest_sha}", oci_manifest),
                ]:
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    bundle.addfile(info, io.BytesIO(data))

            parser = ROOT / "scripts/mcpgit-offline-release.py"
            for field, expected in [
                ("config_id", f"sha256:{config_sha}"),
                ("manifest_id", f"sha256:{manifest_sha}"),
            ]:
                result = subprocess.run(
                    [
                        "python3",
                        str(parser),
                        "image-identity",
                        "--archive",
                        str(archive),
                        "--image-tag",
                        tag,
                        "--field",
                        field,
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

    def test_binary_workflow_provisions_native_musl_compilers(self) -> None:
        workflow = (ROOT / ".github/workflows/publish-binary.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("musl-tools", workflow)
        self.assertIn("x86_64-linux-musl-gcc", workflow)
        self.assertIn("aarch64-linux-musl-gcc", workflow)
        self.assertIn("command -v musl-gcc", workflow)
        self.assertIn("scripts/build-linux-program-native.sh", workflow)

    def test_offline_release_workflow_is_tag_and_source_bound(self) -> None:
        workflow = (ROOT / ".github/workflows/publish-offline-v1.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("mcpgit-git-([0-9a-f]{40})-linux-(amd64|arm64)", workflow)
        self.assertIn("ref: ${{ needs.prepare.outputs.source_sha }}", workflow)
        self.assertIn("runs-on: ${{ needs.prepare.outputs.runner }}", workflow)
        self.assertIn("scripts/build-offline-release.sh", workflow)
        self.assertIn("--verify-tag", workflow)
        self.assertIn("--latest=false", workflow)

    def test_offline_pointer_is_architecture_qualified_and_digest_bound(self) -> None:
        pointer = json.loads((ROOT / "offline-latest.json").read_text(encoding="utf-8"))
        self.assertEqual(pointer["schema"], "mcpgit.offline-pointer.v1")
        architectures = pointer["architectures"]
        self.assertEqual(set(architectures), {"linux-amd64", "linux-arm64"})
        self.assertEqual(pointer["source_sha"], next(iter(architectures.values()))["source_sha"])
        expected_targets = {
            "linux-arm64": "aarch64-unknown-linux-musl",
            "linux-amd64": "x86_64-unknown-linux-musl",
        }
        for platform, entry in architectures.items():
            self.assertIn(platform, expected_targets)
            self.assertEqual(entry["target"], expected_targets[platform])
            self.assertRegex(entry["source_sha"], r"^[0-9a-f]{40}$")
            self.assertEqual(entry["source_sha"], pointer["source_sha"])
            self.assertRegex(entry["manifest_sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(entry["tag"].startswith("mcpgit-git-"))

    def test_product_entrypoints_are_executable_and_keep_the_fail_closed_contract(self) -> None:
        for relative in [
            "install.sh",
            "deploy/mcpgit-install.sh",
            "deploy/mcpgitctl",
            "deploy/novice-install.sh",
            "deploy/novice-fetch.sh",
        ]:
            mode = (ROOT / relative).stat().st_mode
            self.assertTrue(mode & stat.S_IXUSR, relative)

        installer = (ROOT / "deploy/mcpgit-install.sh").read_text(encoding="utf-8")
        novice = (ROOT / "deploy/novice-install.sh").read_text(encoding="utf-8")
        ctl = (ROOT / "deploy/mcpgitctl").read_text(encoding="utf-8")
        self.assertIn("mcpgitrelease/main/deploy", installer)
        self.assertIn("offline channel has no release for {platform}", novice)
        self.assertIn("offline bundle target $program_target is not compatible", novice)
        self.assertIn("aarch64-unknown-linux-gnu", novice)
        self.assertIn("aarch64-unknown-linux-musl", novice)
        self.assertIn("x86_64-unknown-linux-gnu", novice)
        self.assertIn("x86_64-unknown-linux-musl", novice)
        self.assertIn("/data/.mcpgit-org-id", ctl)
        self.assertIn("Container identity does not match the persistent data volume", ctl)

    def test_root_installer_is_versionless_and_delegates(self) -> None:
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn("api.github.com/repos/$REPOSITORY/commits/main", installer)
        self.assertIn("MCPGIT_INSTALL_REVISION", installer)
        self.assertIn('CONTENT_BASE="https://raw.githubusercontent.com/$REPOSITORY/$REVISION"', installer)
        self.assertIn('MCPGIT_CHANNEL_URL="$CONTENT_BASE/offline-latest.json"', installer)
        self.assertIn("mcpgit-install.sh", installer)
        self.assertNotRegex(installer, r"mcpgit-git-[0-9a-f]{40}")
        self.assertNotIn('exec "$TMP_DIR/mcpgit-install.sh"', installer)

    def test_online_bundle_helpers_follow_the_pinned_install_snapshot(self) -> None:
        novice = (ROOT / "deploy/novice-install.sh").read_text(encoding="utf-8")
        self.assertIn("MCPGIT_INSTALL_CONTENT_BASE", novice)
        self.assertIn('$MCPGIT_INSTALL_CONTENT_BASE/$helper', novice)
        self.assertIn('$MCPGIT_INSTALL_CONTENT_BASE/Dockerfile.offline-runtime', novice)
        self.assertIn('$MCPGIT_INSTALL_CONTENT_BASE/deploy/$product_file', novice)
        self.assertIn("fetch_snapshot_file", novice)
        self.assertIn("fetch_snapshot_file() (", novice)
        self.assertNotIn('if [ ! -f "$target/$helper" ]', novice)
        self.assertNotIn('if [ ! -f "$target/Dockerfile.offline-runtime" ]', novice)

    def test_installer_accepts_standard_linux_sha256sum(self) -> None:
        novice = (ROOT / "deploy/novice-install.sh").read_text(encoding="utf-8")
        self.assertIn("command -v sha256sum", novice)
        self.assertIn("command -v shasum", novice)

    def test_runtime_dockerfile_records_safe_recover_digest(self) -> None:
        dockerfile = (ROOT / "Dockerfile.offline-runtime").read_text(encoding="utf-8")
        self.assertIn("MCPGIT_EXEC_SAFE_RECOVER_SHA256", dockerfile)
        self.assertIn("com.yxsicd.mcpgit.exec.safe-recover-sha256", dockerfile)

    def test_runtime_assembly_template_is_digest_bound_and_health_checked(self) -> None:
        dockerfile = (ROOT / "Dockerfile.offline-runtime").read_text(encoding="utf-8")
        novice = (ROOT / "deploy/novice-install.sh").read_text(encoding="utf-8")
        self.assertIn("MCPGIT_ASSEMBLY_SHA256", dockerfile)
        self.assertIn("com.yxsicd.mcpgit.assembly-sha256", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn("http://127.0.0.1:8001/healthz", dockerfile)
        self.assertIn('assembly_sha=$(sha256_file "$dockerfile")', novice)
        self.assertIn('com.yxsicd.mcpgit.assembly-sha256', novice)
        self.assertIn('--build-arg "MCPGIT_ASSEMBLY_SHA256=$assembly_sha"', novice)

    def test_runtime_cache_is_source_bound_and_content_verified(self) -> None:
        novice = (ROOT / "deploy/novice-install.sh").read_text(encoding="utf-8")
        self.assertIn('runtime_image="mcpgit-offline-runtime:$release_id"', novice)
        self.assertIn('actual_base_image_id', novice)
        self.assertIn('base_manifest_id=$(python3 "$parser" image-identity', novice)
        self.assertIn('base_image_identity_matches()', novice)
        self.assertIn('if ! base_image_identity_matches "$actual_base_image_id"; then', novice)
        self.assertIn('runtime_image_exact()', novice)
        self.assertIn('com.yxsicd.mcpgit.manifest-sha256', novice)
        self.assertIn('assembled runtime image failed exact release verification', novice)

    def test_existing_instance_cannot_silently_switch_data_volume_or_conflict_port(self) -> None:
        novice = (ROOT / "deploy/novice-install.sh").read_text(encoding="utf-8")
        self.assertIn('refusing to change data volume for existing instance', novice)
        self.assertIn('refusing MCPGit install because host port $port is already in use', novice)
        self.assertIn('refusing to replace existing instance config with a different organization identity', novice)

    def test_instance_replacement_keeps_one_automatic_rollback(self) -> None:
        novice = (ROOT / "deploy/novice-install.sh").read_text(encoding="utf-8")
        self.assertIn('rollback_container="${instance}-rollback"', novice)
        self.assertIn('restore_previous_instance()', novice)
        self.assertIn('docker rename "$instance" "$rollback_container"', novice)
        self.assertIn('candidate container failed to start; restoring previous instance', novice)
        self.assertIn('candidate instance did not become healthy; restoring previous instance', novice)
        self.assertIn('restored previous instance $instance after candidate failure', novice)
        self.assertIn('--restart no', novice)
        self.assertIn('docker update --restart unless-stopped "$instance"', novice)
        self.assertNotIn('docker rm -f "$instance" >/dev/null 2>&1 || true\ndocker run -d', novice)

    def test_exact_current_instance_is_a_no_restart_install(self) -> None:
        novice = (ROOT / "deploy/novice-install.sh").read_text(encoding="utf-8")
        self.assertIn('current_image_id=$(docker inspect "$instance" --format \'{{.Image}}\')', novice)
        self.assertIn('current_config_source', novice)
        self.assertIn('current_netrc_source', novice)
        self.assertIn('desired_runtime_id=$(docker image inspect "$runtime_image" --format \'{{.Id}}\')', novice)
        self.assertIn('already matches the selected release; no restart required', novice)
        self.assertIn('base_image_identity_matches', novice)
        self.assertIn('--field manifest_id', novice)

    def test_fresh_install_uses_random_ephemeral_admin_bootstrap(self) -> None:
        novice = (ROOT / "deploy/novice-install.sh").read_text(encoding="utf-8")
        self.assertIn("MCPGIT_CREDENTIAL_DIR", novice)
        self.assertIn('secrets.token_urlsafe(24)', novice)
        self.assertIn('MCPGIT_BASIC_USERNAME=systemadmin', novice)
        self.assertIn('MCPGIT_BASIC_VERIFY=%s', novice)
        self.assertIn('chmod 0600 "$credential_tmp"', novice)
        self.assertIn('auth_bootstrap_container="${instance}-auth-bootstrap"', novice)
        self.assertIn('--env-file "$bootstrap_password_env"', novice)
        self.assertIn('docker restart "$auth_bootstrap_container"', novice)
        self.assertIn('/__mcpgit/system/safegit/', novice)
        self.assertIn('docker rm -f "$auth_bootstrap_container"', novice)
        self.assertIn('generated systemadmin credential failed authentication probe', novice)
        self.assertIn('systemadmin credential file (0600)', novice)
        self.assertIn('safegit-shamir-shares.v1.json', novice)
        self.assertIn('safegit-agent-key.v1.json', novice)
        self.assertNotIn('first login: systemadmin / change-me', novice)

    def test_local_product_wrapper_preserves_success_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            shutil.copy2(ROOT / "deploy/mcpgit-install.sh", root / "mcpgit-install.sh")
            (root / "novice-install.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            (root / "mcpgitctl").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            for name in ["mcpgit-install.sh", "novice-install.sh", "mcpgitctl"]:
                (root / name).chmod(0o755)
            result = subprocess.run(
                ["sh", str(root / "mcpgit-install.sh"), "--download-only"],
                cwd=root,
                env={**os.environ, "HOME": str(root / "home")},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_default_install_refreshes_latest_but_explicit_bundle_can_stay_offline(self) -> None:
        novice = (ROOT / "deploy/novice-install.sh").read_text(encoding="utf-8")
        self.assertIn("bundle_explicit=false", novice)
        self.assertIn("--bundle) bundle=$2; bundle_explicit=true", novice)
        self.assertIn('[ "$bundle_explicit" = false ]', novice)
        self.assertIn('[ "$download_only" = true ]', novice)
        self.assertIn('[ -n "$MCPGIT_RELEASE_TAG" ]', novice)
        self.assertIn('refresh_bundle=true', novice)
        self.assertIn('tag=$(resolve_tag)', novice)
        self.assertIn('fetch_bundle "$tag" "$bundle"', novice)

    def test_default_instance_enables_local_wasmc_build_without_forcing_router(self) -> None:
        novice = (ROOT / "deploy/novice-install.sh").read_text(encoding="utf-8")
        self.assertIn(
            'MCPGIT_EXECUTABLE_BUILD_REPOSITORY="${MCPGIT_EXECUTABLE_BUILD_REPOSITORY-tablegit}"',
            novice,
        )
        self.assertIn(
            '-e MCPGIT_EXECUTABLE_BUILD_REPOSITORY="$executable_build_repository"',
            novice,
        )
        self.assertIn(
            '[ "$current_executable_build_repository" = "$executable_build_repository" ]',
            novice,
        )
        self.assertNotIn('MCPGIT_EXECUTABLE_ROUTE_REPOSITORY="${', novice)

    def test_offline_latest_promotion_verifies_dual_arch_releases(self) -> None:
        workflow = (ROOT / ".github/workflows/promote-offline-latest.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("gh release view", workflow)
        self.assertIn("gh release download", workflow)
        self.assertIn("linux-amd64", workflow)
        self.assertIn("linux-arm64", workflow)
        self.assertIn("offline-latest.json", workflow)
        self.assertIn("verify-layer", workflow)
        self.assertIn("--kind base_image", workflow)

    def test_template_install_creates_repositories_missing_from_archive(self) -> None:
        novice = (ROOT / "deploy/novice-install.sh").read_text(encoding="utf-8")
        loop = "for r in works rootskills mcpgitsystem safegit systemconfig tablegit binarygit; do"
        loop_start = novice.index(loop)
        loop_end = novice.index("done", loop_start)
        template_init = novice[loop_start:loop_end]
        self.assertIn('mkdir -p "$dir"', template_init)
        self.assertIn('printf "# %s\\n" "$r" > "$dir/README.md"', template_init)
        self.assertLess(
            template_init.index('mkdir -p "$dir"'),
            template_init.index('git -C "$dir" init'),
        )

    def test_public_bootstrap_helpers_and_quick_start_are_present(self) -> None:
        for relative in [
            "Dockerfile.offline-runtime",
            "scripts/mcpgit-offline-release.py",
            "scripts/bootstrap-builtin-auth.py",
        ]:
            self.assertTrue((ROOT / relative).is_file(), relative)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertRegex(readme, re.compile(r"## Install the latest MCPGit.*install\.sh", re.S))
        self.assertIn("mcpgitctl status", readme)
        self.assertIn("--download-only --bundle", readme)


if __name__ == "__main__":
    unittest.main()
