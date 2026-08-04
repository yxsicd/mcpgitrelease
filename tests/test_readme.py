import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")


class ReadmeContractTests(unittest.TestCase):
    def test_client_sdk_release_is_documented_as_offline_and_channel_independent(self) -> None:
        self.assertIn("## Rust Client SDK", README)
        self.assertIn(
            "mcpgit-client-sdk-git-8730092557649f2b4c6661d73424add50407cf38",
            README,
        )
        self.assertIn("mcpgit-client-sdk-release-v1.json", README)
        self.assertIn("mcpgit-service-sdk-2.0.0.crate", README)
        self.assertIn("mcpgit-service-client-2.0.0.crate", README)
        self.assertIn('registry = "mcpgit-sdk"', README)
        self.assertIn("cargo build --offline", README)
        self.assertIn("GitHub is only the immutable download location", README)
        self.assertIn("independent immutable Release family", README)
        self.assertIn("selected by `dev`, `main`, or `prod`", README)
        self.assertIn("never deleted automatically", README)


if __name__ == "__main__":
    unittest.main()
