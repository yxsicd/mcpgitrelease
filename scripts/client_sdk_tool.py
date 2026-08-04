#!/usr/bin/env python3
"""Compose and validate the recommended MCPGit Client SDK pointer."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from typing import Any


SCHEMA = "mcpgitrelease/client-sdk/v1"
MANIFEST_SCHEMA = "mcpgit.client-sdk-release.v1"
ROLES = ["sdk_crate", "client_crate", "offline_registry_bundle"]
TAG_RE = re.compile(r"^mcpgit-client-sdk-git-([0-9a-f]{40})$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class PointerError(ValueError):
    pass


def read_json(path: str | pathlib.Path) -> Any:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def require_keys(value: dict[str, Any], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        raise PointerError(
            f"{context} fields differ: missing={sorted(expected - actual)} "
            f"extra={sorted(actual - expected)}"
        )


def validate(pointer: dict[str, Any]) -> None:
    require_keys(
        pointer,
        {
            "schema",
            "updated_at",
            "tag",
            "release_url",
            "source_repository",
            "source_revision",
            "registry_name",
            "packages",
            "assets",
        },
        "pointer",
    )
    if pointer["schema"] != SCHEMA:
        raise PointerError("unsupported Client SDK pointer schema")
    try:
        dt.datetime.fromisoformat(pointer["updated_at"].replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise PointerError("updated_at must be ISO-8601") from error
    match = TAG_RE.fullmatch(pointer["tag"])
    if not match or match.group(1) != pointer["source_revision"]:
        raise PointerError("tag must bind the exact source revision")
    if pointer["source_repository"] != "yxsicd/MCPGit":
        raise PointerError("unexpected Client SDK source repository")
    if pointer["registry_name"] != "mcpgit-sdk":
        raise PointerError("unexpected Cargo registry name")
    expected_release_url = (
        "https://github.com/yxsicd/mcpgitrelease/releases/tag/" + pointer["tag"]
    )
    if pointer["release_url"] != expected_release_url:
        raise PointerError("release_url does not match the immutable tag")
    packages = pointer["packages"]
    require_keys(packages, {"mcpgit-service-client", "mcpgit-service-sdk"}, "packages")
    if not all(isinstance(value, str) and VERSION_RE.fullmatch(value) for value in packages.values()):
        raise PointerError("package versions must be exact SemVer triples")
    assets = pointer["assets"]
    if not isinstance(assets, list) or [item.get("role") for item in assets] != ROLES:
        raise PointerError("assets must use the exact ordered Client SDK roles")
    for item in assets:
        require_keys(item, {"role", "file", "url", "sha256", "size"}, f"asset {item.get('role')}")
        if not isinstance(item["size"], int) or item["size"] <= 0:
            raise PointerError("asset size must be positive")
        if not isinstance(item["sha256"], str) or not SHA_RE.fullmatch(item["sha256"]):
            raise PointerError("asset SHA-256 must be lowercase hexadecimal")
        expected_url = (
            "https://github.com/yxsicd/mcpgitrelease/releases/download/"
            f"{pointer['tag']}/{item['file']}"
        )
        if item["url"] != expected_url:
            raise PointerError(f"asset URL mismatch for {item['file']}")


def compose(manifest: dict[str, Any], release: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise PointerError("unsupported Client SDK release manifest schema")
    source_revision = manifest.get("source_sha")
    release_id = manifest.get("release_id")
    if release_id != f"git-{source_revision}":
        raise PointerError("release manifest is not source-bound")
    tag = f"mcpgit-client-sdk-{release_id}"
    if release.get("tagName") != tag:
        raise PointerError("GitHub Release tag does not match the manifest")
    if release.get("isDraft") or release.get("isPrerelease"):
        raise PointerError("recommended Client SDK must be a published stable Release")
    release_assets = {item["name"]: item for item in release.get("assets", [])}
    assets: list[dict[str, Any]] = []
    manifest_assets = manifest.get("assets", [])
    if [item.get("role") for item in manifest_assets] != ROLES:
        raise PointerError("release manifest asset roles are not exact")
    for item in manifest_assets:
        remote = release_assets.get(item["file"])
        if remote is None or remote.get("state") != "uploaded":
            raise PointerError(f"GitHub asset is not uploaded: {item['file']}")
        digest = remote.get("digest", "")
        if remote.get("size") != item["bytes"] or digest != f"sha256:{item['sha256']}":
            raise PointerError(f"GitHub asset identity mismatch: {item['file']}")
        assets.append(
            {
                "role": item["role"],
                "file": item["file"],
                "url": remote["url"],
                "sha256": item["sha256"],
                "size": item["bytes"],
            }
        )
    pointer = {
        "schema": SCHEMA,
        "updated_at": release["publishedAt"],
        "tag": tag,
        "release_url": release["url"],
        "source_repository": "yxsicd/MCPGit",
        "source_revision": source_revision,
        "registry_name": manifest["registry_name"],
        "packages": manifest["packages"],
        "assets": assets,
    }
    validate(pointer)
    return pointer


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    validate_cmd = commands.add_parser("validate")
    validate_cmd.add_argument("pointer")
    compose_cmd = commands.add_parser("compose")
    compose_cmd.add_argument("--manifest", required=True)
    compose_cmd.add_argument("--release", required=True)
    compose_cmd.add_argument("--output", required=True)
    return root


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.command == "validate":
            validate(read_json(arguments.pointer))
        else:
            pointer = compose(read_json(arguments.manifest), read_json(arguments.release))
            pathlib.Path(arguments.output).write_text(
                json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    except (KeyError, TypeError, PointerError, json.JSONDecodeError) as error:
        print(f"client-sdk-tool: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
