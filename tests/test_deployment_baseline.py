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

    def test_hot_binary_update_reuses_unchanged_cold_artifacts(self) -> None:
        fetch = (ROOT / "deploy" / "mcpgit-fetch.sh").read_text(encoding="utf-8")
        deploy = (ROOT / "deploy" / "mcpgit-deploy.sh").read_text(encoding="utf-8")

        self.assertIn("reusing verified cached asset", fetch)
        self.assertIn('[[ -r "$target/$file"', fetch)
        self.assertIn("reusing verified cold base", deploy)
        self.assertIn("$MCPGIT_DEVBASE_TAG.image-id", deploy)
        self.assertIn('actual_image_id" == "$expected_image_id', deploy)
        self.assertIn(
            "verified devbase identity is unavailable and the cold archive is missing",
            deploy,
        )


if __name__ == "__main__":
    unittest.main()
