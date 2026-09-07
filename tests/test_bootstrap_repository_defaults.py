import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bootstrap", ROOT / "scripts/bootstrap-builtin-auth.py")
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class BootstrapRepositoryDefaultsTests(unittest.TestCase):
    def test_default_binary_and_explicit_legacy_repository_grants(self):
        for configured, expected in [
            (None, {"works", "tablegit", "binary"}),
            ("works,tablegit,binarygit", {"works", "tablegit", "binarygit"}),
        ]:
            with self.subTest(configured=configured), tempfile.TemporaryDirectory() as directory:
                repo = Path(directory)
                subprocess.run(["git", "init", "-q", str(repo)], check=True)
                with patch.dict(os.environ, {}, clear=True):
                    if configured is not None:
                        os.environ["MCPGIT_BUILDER_REPOSITORIES"] = configured
                    bootstrap.bootstrap(repo, "26090600-0000-4000-8000-000000000014", "test", "works")
                grants = [json.loads(path.read_text())["row"]
                          for path in (repo / "data/tables/system_grants/rows").rglob("*.json")]
                actual = {row["repository_id"] for row in grants if row["role_id"] == "builtin-builder"}
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
