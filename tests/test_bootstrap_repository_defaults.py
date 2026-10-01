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
    instance = "26090600-0000-4000-8000-000000000014"

    def commit(self, repo):
        bootstrap.run_git(repo, "add", "data")
        bootstrap.run_git(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Fixture checkpoint")

    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        repo = Path(temp.name)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        with patch.dict(os.environ, {"MCPGIT_BUILDER_REPOSITORIES": "works,tablegit,binarygit,safegit"}, clear=True):
            bootstrap.bootstrap(repo, self.instance, "test", "works")
        self.commit(repo)
        return repo

    def test_shared_person_grants_are_scoped_and_have_no_verification_material(self):
        repo = self.fixture()
        person_id = bootstrap.stable_person_id(self.instance, "mcpadmin")
        person = bootstrap.read_envelope(bootstrap.row_path(repo, "system_persons", person_id), person_id)["row"]
        self.assertEqual(person, {"person_id": person_id, "handle": "mcpadmin", "display_name": "mcpadmin", "status": "active"})
        grants = [json.loads(p.read_text())["row"] for p in (repo / "data/tables/system_grants/rows").rglob("*.json")]
        shared = [r for r in grants if r.get("person_id") == person_id]
        self.assertEqual({r["repository_id"] for r in shared if r["repository_id"]}, {"works", "tablegit", "binarygit"})
        self.assertEqual({r["role_id"] for r in shared if not r["repository_id"]}, {"builtin-connect", "builtin-mcpadmin-control"})
        self.assertTrue(all(r["instance_id"] == self.instance for r in shared))

    def test_shared_person_replay_is_zero_write(self):
        repo = self.fixture()
        with patch.dict(os.environ, {"MCPGIT_BUILDER_REPOSITORIES": "works,tablegit,binarygit,safegit"}, clear=True):
            self.assertEqual(bootstrap.bootstrap(repo, self.instance, "test", "works"), [])
        self.assertEqual(bootstrap.run_git(repo, "status", "--porcelain").stdout, "")

    def test_existing_explicit_shared_uuid_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            explicit_id = "00000000-0000-4000-8000-000000000099"
            bootstrap.ensure_definition(repo, "system_persons")
            bootstrap.write_row(repo, "system_persons", explicit_id, {"person_id": explicit_id, "handle": "mcpadmin", "display_name": "Explicit Shared", "status": "active"})
            self.commit(repo)
            bootstrap.bootstrap(repo, self.instance, "test", "works")
            membership = bootstrap.read_envelope(bootstrap.row_path(repo, "system_memberships", "builtin-mcpadmin-membership"), "builtin-mcpadmin-membership")
            self.assertEqual(membership["row"]["person_id"], explicit_id)

    def test_disabled_shared_person_is_not_reactivated(self):
        repo = self.fixture()
        person_id = bootstrap.stable_person_id(self.instance, "mcpadmin")
        path = bootstrap.row_path(repo, "system_persons", person_id)
        row = json.loads(path.read_text());row["row"]["status"] = "disabled"
        path.write_text(json.dumps(row));self.commit(repo)
        with self.assertRaisesRegex(ValueError, "disabled or ambiguous"):
            bootstrap.bootstrap(repo, self.instance, "test", "works")
        self.assertEqual(json.loads(path.read_text())["row"]["status"], "disabled")

    def test_revoked_shared_grant_is_not_restored(self):
        repo = self.fixture()
        path = bootstrap.row_path(repo, "system_grants", "builtin-mcpadmin-business-tablegit")
        row = json.loads(path.read_text());row["row"]["status"] = "disabled"
        path.write_text(json.dumps(row));self.commit(repo)
        with self.assertRaisesRegex(ValueError, "explicit repair required"):
            bootstrap.bootstrap(repo, self.instance, "test", "works")
        self.assertEqual(json.loads(path.read_text())["row"]["status"], "disabled")

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
