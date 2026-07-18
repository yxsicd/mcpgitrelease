#!/usr/bin/env python3
"""Compose, validate, and promote MCPGit release channel manifests."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import pathlib
import re
import sys
from typing import Any

CHANNELS = ("dev", "main", "prod")
ARCHES = ("amd64", "arm64")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
PROMOTIONS = {("dev", "main"), ("main", "prod")}


class ManifestError(ValueError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: str | pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ManifestError(f"{path} must contain a JSON object")
    return value


def write_json(path: str | pathlib.Path, value: dict[str, Any]) -> None:
    serialized = json.dumps(value, indent=2, sort_keys=False) + "\n"
    if str(path) == "-":
        sys.stdout.write(serialized)
    else:
        pathlib.Path(path).write_text(serialized, encoding="utf-8")


def _validate_artifacts(kind: str, artifacts: Any) -> None:
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise ManifestError(f"{kind}.artifacts must contain exactly amd64 and arm64")
    found: set[str] = set()
    expected_format = "tar.gz" if kind == "binary" else "docker.tar.zst"
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ManifestError(f"{kind} artifact must be an object")
        required = {"os", "arch", "format", "url", "sha256", "size"}
        if set(artifact) != required:
            raise ManifestError(f"{kind} artifact fields must equal {sorted(required)}")
        arch = artifact["arch"]
        if artifact["os"] != "linux" or arch not in ARCHES or arch in found:
            raise ManifestError(f"{kind} artifacts must uniquely cover linux/amd64 and linux/arm64")
        found.add(arch)
        if artifact["format"] != expected_format:
            raise ManifestError(f"{kind}/{arch} format must be {expected_format}")
        if not isinstance(artifact["url"], str) or not artifact["url"].startswith(
            "https://github.com/yxsicd/mcpgitrelease/releases/download/"
        ):
            raise ManifestError(f"{kind}/{arch} has an invalid release URL")
        if not isinstance(artifact["sha256"], str) or not SHA256_RE.fullmatch(artifact["sha256"]):
            raise ManifestError(f"{kind}/{arch} has an invalid SHA-256")
        if not isinstance(artifact["size"], int) or artifact["size"] < 1:
            raise ManifestError(f"{kind}/{arch} has an invalid size")
    if found != set(ARCHES):
        raise ManifestError(f"{kind}.artifacts must contain amd64 and arm64")


def _validate_release(kind: str, release: Any) -> None:
    if not isinstance(release, dict):
        raise ManifestError(f"{kind} must be an object")
    required = {"tag", "source_repository", "source_revision", "artifacts"}
    if kind == "devbase":
        required.add("image")
    if set(release) != required:
        raise ManifestError(f"{kind} fields must equal {sorted(required)}")
    if not isinstance(release["tag"], str) or not release["tag"]:
        raise ManifestError(f"{kind}.tag must be non-empty")
    if not isinstance(release["source_repository"], str) or not release["source_repository"]:
        raise ManifestError(f"{kind}.source_repository must be non-empty")
    if not isinstance(release["source_revision"], str) or not REVISION_RE.fullmatch(
        release["source_revision"]
    ):
        raise ManifestError(f"{kind}.source_revision must be a full lowercase Git SHA")
    if kind == "devbase" and (not isinstance(release["image"], str) or not release["image"]):
        raise ManifestError("devbase.image must be non-empty")
    _validate_artifacts(kind, release["artifacts"])


def _validate_deployment(release: Any) -> None:
    if not isinstance(release, dict):
        raise ManifestError("deployment must be an object")
    required = {"tag", "source_repository", "source_revision", "artifact"}
    if set(release) != required:
        raise ManifestError(f"deployment fields must equal {sorted(required)}")
    if not isinstance(release["tag"], str) or not release["tag"].startswith("deploy-"):
        raise ManifestError("deployment.tag must start with deploy-")
    if not isinstance(release["source_repository"], str) or not release["source_repository"]:
        raise ManifestError("deployment.source_repository must be non-empty")
    if not isinstance(release["source_revision"], str) or not REVISION_RE.fullmatch(
        release["source_revision"]
    ):
        raise ManifestError("deployment.source_revision must be a full lowercase Git SHA")
    artifact = release["artifact"]
    required_artifact = {"format", "url", "sha256", "size"}
    if not isinstance(artifact, dict) or set(artifact) != required_artifact:
        raise ManifestError(f"deployment artifact fields must equal {sorted(required_artifact)}")
    if artifact["format"] != "tar.gz":
        raise ManifestError("deployment artifact format must be tar.gz")
    if not isinstance(artifact["url"], str) or not artifact["url"].startswith(
        "https://github.com/yxsicd/mcpgitrelease/releases/download/"
    ) or not artifact["url"].endswith("/mcpgit-deploy.tar.gz"):
        raise ManifestError("deployment artifact has an invalid release URL")
    if not isinstance(artifact["sha256"], str) or not SHA256_RE.fullmatch(artifact["sha256"]):
        raise ManifestError("deployment artifact has an invalid SHA-256")
    if not isinstance(artifact["size"], int) or artifact["size"] < 1:
        raise ManifestError("deployment artifact has an invalid size")


def validate_manifest(manifest: dict[str, Any], expected_channel: str | None = None) -> None:
    required = {"schema", "channel", "updated_at", "binary", "devbase", "deployment"}
    optional = {"promoted_from"}
    if not required.issubset(manifest) or not set(manifest).issubset(required | optional):
        raise ManifestError("channel manifest has missing or unsupported fields")
    if manifest["schema"] != "mcpgitrelease/channel/v2":
        raise ManifestError("channel manifest schema must be mcpgitrelease/channel/v2")
    channel = manifest["channel"]
    if channel not in CHANNELS:
        raise ManifestError("channel must be dev, main, or prod")
    if expected_channel is not None and channel != expected_channel:
        raise ManifestError(f"manifest channel {channel!r} does not match {expected_channel!r}")
    try:
        dt.datetime.fromisoformat(str(manifest["updated_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ManifestError("updated_at must be an ISO-8601 timestamp") from exc
    if "promoted_from" in manifest:
        source = manifest["promoted_from"]
        if (source, channel) not in PROMOTIONS:
            raise ManifestError(f"invalid promotion {source!r} -> {channel!r}")
    _validate_release("binary", manifest["binary"])
    _validate_release("devbase", manifest["devbase"])
    _validate_deployment(manifest["deployment"])


def compose(
    channel: str,
    binary: dict[str, Any],
    devbase: dict[str, Any],
    deployment: dict[str, Any],
) -> dict[str, Any]:
    if channel not in CHANNELS:
        raise ManifestError("channel must be dev, main, or prod")
    binary = copy.deepcopy(binary)
    devbase = copy.deepcopy(devbase)
    deployment = copy.deepcopy(deployment)
    if binary.pop("kind", "binary") != "binary":
        raise ManifestError("binary metadata kind must be binary")
    if devbase.pop("kind", "devbase") != "devbase":
        raise ManifestError("devbase metadata kind must be devbase")
    if deployment.pop("kind", "deployment") != "deployment":
        raise ManifestError("deployment metadata kind must be deployment")
    manifest = {
        "schema": "mcpgitrelease/channel/v2",
        "channel": channel,
        "updated_at": utc_now(),
        "binary": binary,
        "devbase": devbase,
        "deployment": deployment,
    }
    validate_manifest(manifest, channel)
    return manifest


def promote(source: dict[str, Any], target: str) -> dict[str, Any]:
    validate_manifest(source)
    source_channel = source["channel"]
    if (source_channel, target) not in PROMOTIONS:
        raise ManifestError(f"invalid promotion {source_channel!r} -> {target!r}")
    result = copy.deepcopy(source)
    result["channel"] = target
    result["promoted_from"] = source_channel
    result["updated_at"] = utc_now()
    validate_manifest(result, target)
    return result


def installer_env(manifest: dict[str, Any], arch: str) -> str:
    validate_manifest(manifest)
    if arch not in ARCHES:
        raise ManifestError("installer architecture must be amd64 or arm64")
    binary = next(item for item in manifest["binary"]["artifacts"] if item["arch"] == arch)
    devbase = next(item for item in manifest["devbase"]["artifacts"] if item["arch"] == arch)
    deployment = manifest["deployment"]["artifact"]
    values = {
        "MCPGIT_INSTALL_SCHEMA": "mcpgitrelease/install/v1",
        "MCPGIT_CHANNEL": manifest["channel"],
        "MCPGIT_ARCH": arch,
        "MCPGIT_BINARY_TAG": manifest["binary"]["tag"],
        "MCPGIT_BINARY_REVISION": manifest["binary"]["source_revision"],
        "MCPGIT_BINARY_FILE": binary["url"].rsplit("/", 1)[-1],
        "MCPGIT_BINARY_SHA256": binary["sha256"],
        "MCPGIT_DEVBASE_TAG": manifest["devbase"]["tag"],
        "MCPGIT_DEVBASE_IMAGE": manifest["devbase"]["image"],
        "MCPGIT_DEVBASE_FILE": devbase["url"].rsplit("/", 1)[-1],
        "MCPGIT_DEVBASE_SHA256": devbase["sha256"],
        "MCPGIT_DEPLOY_TAG": manifest["deployment"]["tag"],
        "MCPGIT_DEPLOY_FILE": deployment["url"].rsplit("/", 1)[-1],
        "MCPGIT_DEPLOY_SHA256": deployment["sha256"],
    }
    for value in values.values():
        if "\n" in value or "\r" in value:
            raise ManifestError("installer values may not contain newlines")
    return "".join(f"{key}={value}\n" for key, value in values.items())


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("manifest")
    validate.add_argument("--channel", choices=CHANNELS)
    compose_cmd = commands.add_parser("compose")
    compose_cmd.add_argument("--channel", required=True, choices=CHANNELS)
    compose_cmd.add_argument("--binary", required=True)
    compose_cmd.add_argument("--devbase", required=True)
    compose_cmd.add_argument("--deployment", required=True)
    compose_cmd.add_argument("--output", required=True)
    promote_cmd = commands.add_parser("promote")
    promote_cmd.add_argument("--source", required=True)
    promote_cmd.add_argument("--target", required=True, choices=CHANNELS)
    promote_cmd.add_argument("--output", required=True)
    installer = commands.add_parser("installer-env")
    installer.add_argument("--manifest", required=True)
    installer.add_argument("--arch", required=True, choices=ARCHES)
    installer.add_argument("--output", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "validate":
            validate_manifest(read_json(args.manifest), args.channel)
        elif args.command == "compose":
            value = compose(
                args.channel,
                read_json(args.binary),
                read_json(args.devbase),
                read_json(args.deployment),
            )
            write_json(args.output, value)
        elif args.command == "promote":
            value = promote(read_json(args.source), args.target)
            write_json(args.output, value)
        else:
            value = installer_env(read_json(args.manifest), args.arch)
            if args.output == "-":
                sys.stdout.write(value)
            else:
                pathlib.Path(args.output).write_text(value, encoding="utf-8")
    except ManifestError as exc:
        print(f"release-tool: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
