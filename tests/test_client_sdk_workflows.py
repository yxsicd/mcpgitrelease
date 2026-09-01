import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ClientSdkWorkflowTests(unittest.TestCase):
    def test_publish_is_exact_source_tag_driven(self) -> None:
        workflow = (ROOT / ".github/workflows/publish-client-sdk.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('tags:\n      - "mcpgit-client-sdk-git-*"', workflow)
        self.assertIn("^mcpgit-client-sdk-git-([0-9a-f]{40})$", workflow)
        self.assertIn("repository: yxsicd/MCPGit", workflow)
        self.assertIn("ref: ${{ needs.prepare.outputs.source_sha }}", workflow)
        self.assertIn("cargo +1.96.0 fetch --locked", workflow)
        self.assertIn("scripts/publish-client-sdk-release.sh", workflow)
        self.assertIn("uses: ./.github/workflows/set-client-sdk.yml", workflow)

    def test_pointer_selector_remains_manually_callable_and_reusable(self) -> None:
        workflow = (ROOT / ".github/workflows/set-client-sdk.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("workflow_call:", workflow)
        self.assertIn("scripts/client_sdk_tool.py compose", workflow)
        self.assertIn("scripts/client_sdk_tool.py validate", workflow)


if __name__ == "__main__":
    unittest.main()
