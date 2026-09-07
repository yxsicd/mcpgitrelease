import importlib.util
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("layout", ROOT / "scripts/verify_repository_layout.py")
layout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(layout)


class RepositoryLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name) / "repos"
        self.root.mkdir()
        self.rows = self.root / "systemconfig/data/tables/system_repositories/rows"
        for name in layout.STANDARD_REPOSITORIES:
            subprocess.run(["git", "init", "-q", str(self.root / name)], check=True)
        self.rows.mkdir(parents=True)
        for name in layout.STANDARD_REPOSITORIES:
            self.register(name)

    def register(self, name, path=None):
        (self.rows / (name + ".json")).write_text(json.dumps({
            "deleted": False, "row": {"repository_id": name, "path": path or str(self.root / name)}
        }))

    def test_fresh_standard_registry_matches_git_directories_and_ignores_runtime(self):
        (self.root / ".mcpgit-runtime").mkdir()
        result = layout.inspect_layout(self.root)
        self.assertTrue(all(result["checks"].values()))
        self.assertNotIn(".mcpgit-runtime", result["physical_repositories"])
        self.assertEqual(result["runtime_directories"], [".mcpgit-runtime"])

    def test_old_registered_binarygit_plus_unused_binary_is_rejected(self):
        (self.rows / "binary.json").unlink()
        self.register("binarygit")
        subprocess.run(["git", "init", "-q", str(self.root / "binarygit")], check=True)
        result = layout.inspect_layout(self.root)
        self.assertFalse(result["checks"]["registry_matches_physical_repos"])
        self.assertFalse(result["checks"]["standard_repos_initialized"])

    def test_bare_tablegit_backing_is_valid_but_fake_or_broken_bare_is_not(self):
        tablegit = self.root / "tablegit"
        shutil.rmtree(tablegit)
        subprocess.run(["git", "init", "--bare", "-q", str(tablegit)], check=True)
        self.assertTrue(all(layout.inspect_layout(self.root)["checks"].values()))
        (tablegit / "refs/heads/main").write_text("1" * 40 + "\n")
        self.assertFalse(layout.inspect_layout(self.root)["checks"]["standard_repos_initialized"])
        shutil.rmtree(tablegit)
        tablegit.mkdir()
        (tablegit / "HEAD").write_text("ref: refs/heads/main\n")
        self.assertFalse(layout.inspect_layout(self.root)["checks"]["standard_repos_initialized"])

    def test_existing_directory_without_git_and_wrong_registered_path_are_rejected(self):
        self.register("binary", str(self.root / "different"))
        self.assertFalse(layout.inspect_layout(self.root)["checks"]["registry_matches_physical_repos"])
        shutil.rmtree(self.root / "binary/.git")
        self.assertFalse(layout.inspect_layout(self.root)["checks"]["standard_repos_initialized"])

    def test_deleted_row_does_not_count_as_registration(self):
        (self.rows / "binary.json").write_text(json.dumps({
            "deleted": True, "row": {"repository_id": "binary", "path": str(self.root / "binary")}
        }))
        self.assertFalse(layout.inspect_layout(self.root)["checks"]["registry_matches_physical_repos"])


if __name__ == "__main__":
    unittest.main()
