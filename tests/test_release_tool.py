import copy
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_tool", ROOT / "scripts/release_tool.py")
release_tool = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(release_tool)


def artifact(kind, arch):
    suffix = "tar.gz" if kind == "binary" else "docker.tar.zst"
    return {
        "os": "linux",
        "arch": arch,
        "format": suffix,
        "url": f"https://github.com/yxsicd/mcpgitrelease/releases/download/tag/{kind}-{arch}.{suffix}",
        "sha256": "a" * 64,
        "size": 42,
    }


def metadata(kind):
    if kind == "deployment":
        return {
            "kind": kind,
            "tag": "deploy-" + "b" * 12,
            "source_repository": "yxsicd/mcpgitrelease",
            "source_revision": "b" * 40,
            "artifact": {
                "format": "tar.gz",
                "url": "https://github.com/yxsicd/mcpgitrelease/releases/download/deploy-tag/mcpgit-deploy.tar.gz",
                "sha256": "a" * 64,
                "size": 42,
            },
        }
    value = {
        "kind": kind,
        "tag": f"{kind}-tag",
        "source_repository": "yxsicd/MCPGit",
        "source_revision": "b" * 40,
        "artifacts": [artifact(kind, "amd64"), artifact(kind, "arm64")],
    }
    if kind == "devbase":
        value["image"] = "mcpgit-devbase:test"
    return value


class ReleaseToolTests(unittest.TestCase):
    def test_compose_and_validate(self):
        manifest = release_tool.compose(
            "dev", metadata("binary"), metadata("devbase"), metadata("deployment")
        )
        release_tool.validate_manifest(manifest, "dev")

    def test_promotions_preserve_release_objects(self):
        dev = release_tool.compose(
            "dev", metadata("binary"), metadata("devbase"), metadata("deployment")
        )
        main = release_tool.promote(dev, "main")
        self.assertEqual(main["binary"], dev["binary"])
        self.assertEqual(main["devbase"], dev["devbase"])
        self.assertEqual(main["deployment"], dev["deployment"])
        self.assertEqual(main["promoted_from"], "dev")

    def test_skipping_promotion_stage_is_rejected(self):
        dev = release_tool.compose(
            "dev", metadata("binary"), metadata("devbase"), metadata("deployment")
        )
        with self.assertRaises(release_tool.ManifestError):
            release_tool.promote(dev, "prod")

    def test_duplicate_architecture_is_rejected(self):
        manifest = release_tool.compose(
            "dev", metadata("binary"), metadata("devbase"), metadata("deployment")
        )
        broken = copy.deepcopy(manifest)
        broken["binary"]["artifacts"][1]["arch"] = "amd64"
        with self.assertRaises(release_tool.ManifestError):
            release_tool.validate_manifest(broken)

    def test_wrong_artifact_format_is_rejected(self):
        manifest = release_tool.compose(
            "dev", metadata("binary"), metadata("devbase"), metadata("deployment")
        )
        broken = copy.deepcopy(manifest)
        broken["devbase"]["artifacts"][0]["format"] = "tar.gz"
        with self.assertRaises(release_tool.ManifestError):
            release_tool.validate_manifest(broken)

    def test_installer_env_is_strict_and_arch_specific(self):
        manifest = release_tool.compose(
            "dev", metadata("binary"), metadata("devbase"), metadata("deployment")
        )
        value = release_tool.installer_env(manifest, "arm64")
        self.assertIn("MCPGIT_ARCH=arm64\n", value)
        self.assertIn("MCPGIT_DEVBASE_IMAGE=mcpgit-devbase:test\n", value)
        self.assertIn("MCPGIT_DEPLOY_FILE=mcpgit-deploy.tar.gz\n", value)
        self.assertIn("MCPGIT_BINARY_URL=https://github.com/", value)
        self.assertNotIn("amd64.tar.gz", value)


if __name__ == "__main__":
    unittest.main()
