#!/usr/bin/env python3
"""Plan or execute conservative garbage collection of unreferenced releases."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
from typing import Any


def read_json(path: str) -> Any:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def referenced_tags(manifests: list[str]) -> set[str]:
    tags: set[str] = set()
    for path in manifests:
        manifest = read_json(path)
        if manifest.get("schema") == "mcpgitrelease/channel/v1":
            tags.add(manifest["release"]["tag"])
        else:
            tags.add(manifest["binary"]["tag"])
            tags.add(manifest["devbase"]["tag"])
            tags.add(manifest["deployment"]["tag"])
    return tags


def release_kind(tag: str) -> str | None:
    if tag.startswith("mcpgit-"):
        return "binary"
    if tag.startswith("devbase-"):
        return "devbase"
    if tag.startswith("deploy-"):
        return "deployment"
    return None


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def plan_gc(
    releases: list[dict[str, Any]],
    protected: set[str],
    config: dict[str, Any],
    now: dt.datetime,
) -> list[str]:
    grace = dt.timedelta(days=int(config["grace_days"]))
    keep_counts = {
        "binary": int(config["keep_newest_binary"]),
        "devbase": int(config["keep_newest_devbase"]),
        "deployment": int(config.get("keep_newest_deployment", 0)),
    }
    pinned = set(config.get("pinned_tags", []))
    by_kind: dict[str, list[dict[str, Any]]] = {"binary": [], "devbase": [], "deployment": []}
    for release in releases:
        kind = release_kind(release["tag_name"])
        if kind is not None and not release.get("draft", False):
            by_kind[kind].append(release)
    candidates: list[str] = []
    for kind, values in by_kind.items():
        values.sort(key=lambda item: parse_time(item["published_at"]), reverse=True)
        newest = {item["tag_name"] for item in values[: keep_counts[kind]]}
        for release in values:
            tag = release["tag_name"]
            age = now - parse_time(release["published_at"])
            if tag in protected or tag in pinned or tag in newest or age < grace:
                continue
            candidates.append(tag)
    return sorted(candidates)


def gh_releases(repository: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            "gh",
            "api",
            "--paginate",
            f"repos/{repository}/releases?per_page=100",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    decoder = json.JSONDecoder()
    text = result.stdout.lstrip()
    values: list[dict[str, Any]] = []
    while text:
        page, offset = decoder.raw_decode(text)
        values.extend(page)
        text = text[offset:].lstrip()
    return values


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    root.add_argument("--repository", default="yxsicd/mcpgitrelease")
    root.add_argument("--config", default="retention.json")
    root.add_argument("--manifest", action="append", required=True)
    root.add_argument("--releases-file")
    root.add_argument("--execute", action="store_true")
    root.add_argument("--now", help="ISO-8601 clock override for tests")
    return root


def main() -> int:
    args = parser().parse_args()
    config = read_json(args.config)
    if config.get("schema") != "mcpgitrelease/retention/v1":
        print("gc-releases: unsupported retention schema", file=sys.stderr)
        return 1
    protected = referenced_tags(args.manifest)
    releases = read_json(args.releases_file) if args.releases_file else gh_releases(args.repository)
    now = parse_time(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
    candidates = plan_gc(releases, protected, config, now)
    print(json.dumps({"protected": sorted(protected), "delete": candidates}, indent=2))
    if args.execute:
        for tag in candidates:
            subprocess.run(
                [
                    "gh",
                    "release",
                    "delete",
                    tag,
                    "--repo",
                    args.repository,
                    "--cleanup-tag",
                    "--yes",
                ],
                check=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
