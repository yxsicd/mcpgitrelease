import argparse
import importlib.util
import io
import pathlib
import tarfile
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("offline_extract", ROOT / "scripts/mcpgit-offline-release.py")
offline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offline)


class OfflineExtractLinksTest(unittest.TestCase):
    def extract(self, entries, root="tools", preexisting=False):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = pathlib.Path(self.temp.name)
        archive, destination = base / "bundle.tar.gz", base / "out"
        if preexisting:
            (destination / "tools/bin").mkdir(parents=True)
            (destination / "tools/bin/bunx").write_bytes(b"existing")
        with tarfile.open(archive, "w:gz") as bundle:
            for name, kind, target in entries:
                member = tarfile.TarInfo(name)
                member.mode = 0o755
                if kind == "file":
                    payload = b"bounded executable fixture"
                    member.size = len(payload)
                    bundle.addfile(member, io.BytesIO(payload))
                else:
                    member.type = {"symlink": tarfile.SYMTYPE, "hardlink": tarfile.LNKTYPE, "directory": tarfile.DIRTYPE}[kind]
                    member.linkname = target
                    bundle.addfile(member)
        offline.command_extract(argparse.Namespace(archive=str(archive), destination=str(destination), root=root))
        return destination

    def test_exact_relative_bunx_alias_to_regular_bun_is_admitted(self):
        destination = self.extract([("tools/bin/bun", "file", ""), ("tools/bin/bunx", "symlink", "bun")])
        bunx = destination / "tools/bin/bunx"
        self.assertTrue(bunx.is_symlink())
        self.assertEqual(bunx.readlink(), pathlib.Path("bun"))
        self.assertEqual(bunx.read_bytes(), b"bounded executable fixture")

    def test_other_link_names_and_targets_are_rejected(self):
        for name, target in [("tools/bin/node", "bun"), ("tools/bin/bun", "/outside"), ("tools/bin/bunx", "/bun"), ("tools/bin/bunx", "../bun")]:
            with self.subTest(name=name, target=target), self.assertRaises(SystemExit):
                self.extract([(name, "symlink", target)])

    def test_missing_bun_is_rejected(self):
        with self.assertRaises(SystemExit):
            self.extract([("tools/bin/bunx", "symlink", "bun")])

    def test_non_regular_bun_is_rejected(self):
        with self.assertRaises(SystemExit):
            self.extract([("tools/bin/bun", "directory", ""), ("tools/bin/bunx", "symlink", "bun")])

    def test_hardlink_is_rejected(self):
        with self.assertRaises(SystemExit):
            self.extract([("tools/bin/bun", "file", ""), ("tools/bin/bunx", "hardlink", "tools/bin/bun")])

    def test_duplicate_alias_is_rejected(self):
        with self.assertRaises(SystemExit):
            self.extract([("tools/bin/bun", "file", ""), ("tools/bin/bunx", "symlink", "bun"), ("tools/bin/bunx", "symlink", "bun")])

    def test_program_root_does_not_admit_aliases(self):
        with self.assertRaises(SystemExit):
            self.extract([("program/bin/bun", "file", ""), ("program/bin/bunx", "symlink", "bun")], root="program")

    def test_existing_alias_destination_is_rejected(self):
        with self.assertRaises(SystemExit):
            self.extract([("tools/bin/bun", "file", ""), ("tools/bin/bunx", "symlink", "bun")], preexisting=True)


if __name__ == "__main__":
    unittest.main()
