import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "client_sdk_tool", ROOT / "scripts" / "client_sdk_tool.py"
)
tool = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(tool)


class ClientSdkToolTests(unittest.TestCase):
    def test_checked_in_pointer_is_valid(self) -> None:
        tool.validate(json.loads((ROOT / "client-sdk.json").read_text(encoding="utf-8")))

    def test_pointer_rejects_a_tag_source_mismatch(self) -> None:
        pointer = json.loads((ROOT / "client-sdk.json").read_text(encoding="utf-8"))
        pointer["source_revision"] = "0" * 40
        with self.assertRaises(tool.PointerError):
            tool.validate(pointer)

    def test_compose_requires_uploaded_assets_with_exact_digests(self) -> None:
        pointer = json.loads((ROOT / "client-sdk.json").read_text(encoding="utf-8"))
        manifest = {
            "schema": "mcpgit.client-sdk-release.v1",
            "release_id": "git-" + pointer["source_revision"],
            "source_sha": pointer["source_revision"],
            "registry_name": pointer["registry_name"],
            "packages": pointer["packages"],
            "assets": [
                {
                    "role": item["role"],
                    "file": item["file"],
                    "bytes": item["size"],
                    "sha256": item["sha256"],
                }
                for item in pointer["assets"]
            ],
        }
        release = {
            "tagName": pointer["tag"],
            "isDraft": False,
            "isPrerelease": False,
            "publishedAt": pointer["updated_at"],
            "url": pointer["release_url"],
            "assets": [
                {
                    "name": item["file"],
                    "size": item["size"],
                    "digest": "sha256:" + item["sha256"],
                    "state": "uploaded",
                    "url": item["url"],
                }
                for item in pointer["assets"]
            ],
        }
        self.assertEqual(tool.compose(manifest, release), pointer)
        broken = copy.deepcopy(release)
        broken["assets"][0]["digest"] = "sha256:" + "0" * 64
        with self.assertRaises(tool.PointerError):
            tool.compose(manifest, broken)
