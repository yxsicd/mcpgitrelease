import datetime as dt
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gc_releases", ROOT / "scripts/gc_releases.py")
gc = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gc)


def release(tag, published_at):
    return {"tag_name": tag, "published_at": published_at, "draft": False}


class GarbageCollectionTests(unittest.TestCase):
    def test_referenced_recent_and_pinned_releases_survive(self):
        now = dt.datetime(2026, 7, 18, tzinfo=dt.timezone.utc)
        releases = [
            release("mcpgit-current", "2026-01-01T00:00:00Z"),
            release("mcpgit-new", "2026-07-17T00:00:00Z"),
            release("mcpgit-pinned", "2026-01-01T00:00:00Z"),
            release("mcpgit-old", "2026-01-01T00:00:00Z"),
            release("devbase-old", "2026-01-01T00:00:00Z"),
        ]
        config = {
            "grace_days": 14,
            "keep_newest_binary": 1,
            "keep_newest_devbase": 0,
            "pinned_tags": ["mcpgit-pinned"],
        }
        result = gc.plan_gc(releases, {"mcpgit-current"}, config, now)
        self.assertEqual(result, ["devbase-old", "mcpgit-old"])

    def test_unknown_release_names_are_ignored(self):
        now = dt.datetime(2026, 7, 18, tzinfo=dt.timezone.utc)
        config = {
            "grace_days": 0,
            "keep_newest_binary": 0,
            "keep_newest_devbase": 0,
        }
        result = gc.plan_gc(
            [release("unmanaged-tag", "2020-01-01T00:00:00Z")],
            set(),
            config,
            now,
        )
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
