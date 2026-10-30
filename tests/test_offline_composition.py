import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("composition", ROOT / "scripts/verify-offline-composition.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CompositionTests(unittest.TestCase):
    def test_valid_and_changed_program_bytes(self):
        core = b"native core"
        bundle = b"\0asm\x01\0\0\0guidance"
        sha = hashlib.sha256(bundle).hexdigest()
        data = core + bundle + struct.pack("<QQ", len(core), len(bundle)) + hashlib.sha256(core).digest() + hashlib.sha256(bundle).digest() + b"MCPGITBUNDLE0001"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "program.tar.gz"
            def write(payload):
                with tarfile.open(path, "w:gz") as archive:
                    entry = tarfile.TarInfo("program/bin/mcpgit")
                    entry.size = len(payload)
                    archive.addfile(entry, io.BytesIO(payload))
            write(data)
            module.verify(path, sha)
            with self.assertRaises(ValueError):
                module.verify(path, "0" * 64)
            write(b"X" + data[1:])
            with self.assertRaises(ValueError):
                module.verify(path, sha)

    def test_workflow_requires_exact_shared_bundle(self):
        workflow = (ROOT / ".github/workflows/promote-offline-latest.yml").read_text()
        self.assertIn("bundle_sha256:", workflow)
        self.assertIn("architectures must use the same composition", workflow)
        self.assertIn("scripts/verify-offline-composition.py", workflow)
        block = workflow.split("python3 - candidate-pointer.json <<'PY'\n", 1)[1].split("          PY\n", 1)[0]
        source, bundle = "a" * 40, "b" * 64
        pointer = {"schema": "mcpgit.offline-pointer.v1", "source_sha": source, "architectures": {}}
        for platform, target in (("linux-amd64", "x86_64-unknown-linux-musl"), ("linux-arm64", "aarch64-unknown-linux-musl")):
            pointer["architectures"][platform] = {"source_sha": source, "target": target, "manifest_sha256": "c" * 64,
                                                    "tag": f"mcpgit-git-{source}-{platform}-bundle-{bundle}"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pointer.json"
            def check():
                path.write_text(json.dumps(pointer))
                return subprocess.run([sys.executable, "-c", textwrap.dedent(block), str(path)], capture_output=True)
            self.assertEqual(check().returncode, 0)
            pointer["architectures"]["linux-arm64"]["tag"] = f"mcpgit-git-{source}-linux-arm64-bundle-" + "d" * 64
            self.assertNotEqual(check().returncode, 0)
            pointer["architectures"]["linux-arm64"]["tag"] = f"mcpgit-git-{source}-linux-arm64"
            self.assertNotEqual(check().returncode, 0)


if __name__ == "__main__":
    unittest.main()
