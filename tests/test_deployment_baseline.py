import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class DeploymentBaselineTests(unittest.TestCase):
    def test_full_feature_bundle_uses_current_repository_set(self) -> None:
        config = (ROOT / "deploy" / "mcpgit.toml").read_text(encoding="utf-8")
        runtime = (ROOT / "deploy" / "mcpgit-runtime.env.example").read_text(
            encoding="utf-8"
        )

        self.assertIn('id = "safegit"', config)
        self.assertNotIn('id = "linkgit"', config)
        self.assertNotIn('link_repository = "linkgit"', config)
        self.assertIn(
            "MCPGIT_BOOTSTRAP_REMOTE_REPOS="
            "works,tablegit,binarygit,rootskills,mcpgitsystem,safegit",
            runtime,
        )
        self.assertNotIn("linkgit", runtime)


if __name__ == "__main__":
    unittest.main()
