import json
import pathlib
import re
import stat
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ProductInstallerTests(unittest.TestCase):
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
        self.assertRegex(readme, re.compile(r"## Install MCPGit.*mcpgit-install\.sh", re.S))
        self.assertIn("mcpgitctl status", readme)
        self.assertIn("--download-only --bundle", readme)


if __name__ == "__main__":
    unittest.main()
