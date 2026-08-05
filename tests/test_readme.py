import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")


class ReadmeContractTests(unittest.TestCase):
    def test_agent_quick_start_separates_deployment_and_integration(self) -> None:
        self.assertIn("## Agent quick start", README)
        self.assertIn("Mode 1: Client SDK integration", README)
        self.assertIn("Mode 2: deploy a new instance", README)
        self.assertIn(
            "### Mode 2 instance side: deploy or upgrade an MCPGit instance",
            README,
        )
        self.assertIn("### Mode 1 client side: integrate a Rust client", README)
        self.assertIn("docs/CLIENT_INTEGRATION.md", README)
        self.assertIn("Never change the deployment host", README)
        self.assertIn("Never delete the existing data volume", README)
        self.assertIn("mcpgit-fetch.sh", README)
        self.assertIn("mcpgit-deploy.sh", README)
        self.assertIn("configure-project.sh", README)
        self.assertIn("cargo check --offline", README)
        self.assertIn("/__mcpgit/service-ws", README)
        self.assertIn("Do not invent or", README)
        self.assertIn("mcpgit-preflight.sh", README)
        self.assertIn("AGENT_DEPLOYMENT_RUNBOOK.md", README)
        self.assertIn("x-mcpgit-person-id", README)

    def test_client_sdk_release_is_documented_as_offline_and_channel_independent(self) -> None:
        self.assertIn("## Rust Client SDK", README)
        self.assertIn("client-sdk.json", README)
        self.assertIn("machine-readable authority", README)
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
        self.assertIn("retains the newest five SDK Releases", README)


if __name__ == "__main__":
    unittest.main()
