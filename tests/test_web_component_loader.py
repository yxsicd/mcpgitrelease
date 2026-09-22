from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LOADER = ROOT / "web-components" / "loader.js"


class WebComponentLoaderTests(unittest.TestCase):
    def test_mutable_control_plane_is_not_read_from_branch_cdn(self):
        source = LOADER.read_text(encoding="utf-8")
        self.assertIn(
            "https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/web-components/",
            source,
        )
        self.assertIn("mutableControlUrl(`channels/${channel}.json`)", source)
        self.assertIn("_mcpgit_control", source)
        self.assertNotIn(
            "new URL(`channels/${channel}.json`,CDN_ROOT)",
            source,
        )

    def test_immutable_artifact_still_uses_registry_entry_and_integrity(self):
        source = LOADER.read_text(encoding="utf-8")
        self.assertIn("importVerified(resolved.entry,resolved.integrity)", source)
        self.assertIn("crypto.subtle.digest('SHA-256',bytes)", source)


if __name__ == "__main__":
    unittest.main()
