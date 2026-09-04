#!/usr/bin/env python3
"""Create, verify, inspect, and safely extract MCPGit offline release manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import tarfile
import tempfile

SCHEMA = "mcpgit.offline-release.v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")
IMAGE_TAG_RE = re.compile(
    r"^[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*:"
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
)


def fail(message: str) -> None:
    raise SystemExit(f"mcpgit-offline-release: {message}")


def digest(path: pathlib.Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def _tar_regular_bytes(bundle: tarfile.TarFile, name: str) -> bytes:
    matches = [member for member in bundle.getmembers() if member.name == name]
    if len(matches) != 1:
        fail(f"Docker image archive must contain exactly one {name}")
    member = matches[0]
    if not member.isfile() or member.issym() or member.islnk():
        fail(f"Docker image archive member must be one regular file: {name}")
    source = bundle.extractfile(member)
    if source is None:
        fail(f"cannot read Docker image archive member: {name}")
    return source.read()


def _tar_optional_regular_bytes(bundle: tarfile.TarFile, name: str) -> bytes | None:
    matches = [member for member in bundle.getmembers() if member.name == name]
    if not matches:
        return None
    if len(matches) != 1:
        fail(f"Docker image archive must not duplicate {name}")
    member = matches[0]
    if not member.isfile() or member.issym() or member.islnk():
        fail(f"Docker image archive member must be one regular file: {name}")
    source = bundle.extractfile(member)
    if source is None:
        fail(f"cannot read Docker image archive member: {name}")
    return source.read()


def _json_bytes(data: bytes, label: str) -> object:
    try:
        return json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"Docker image archive has invalid {label}: {error}")


def _descriptor_reaches_config(
    bundle: tarfile.TarFile,
    descriptor: object,
    config_id: str,
    ancestors: set[str],
) -> bool:
    if not isinstance(descriptor, dict):
        fail("Docker image archive OCI descriptor is invalid")
    media_type = str(descriptor.get("mediaType", ""))
    if media_type not in {
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
    }:
        return False
    digest_value = str(descriptor.get("digest", ""))
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest_value):
        fail("Docker image archive OCI descriptor digest is invalid")
    if digest_value in ancestors:
        fail("Docker image archive OCI descriptor graph contains a cycle")
    digest_hex = digest_value.split(":", 1)[1]
    blob = _tar_regular_bytes(bundle, f"blobs/sha256/{digest_hex}")
    if hashlib.sha256(blob).hexdigest() != digest_hex:
        fail("Docker image archive OCI descriptor blob digest mismatch")
    size = descriptor.get("size")
    if isinstance(size, int) and size != len(blob):
        fail("Docker image archive OCI descriptor blob size mismatch")
    value = _json_bytes(blob, "OCI descriptor blob")
    if not isinstance(value, dict):
        fail("Docker image archive OCI descriptor blob must be an object")
    if media_type == "application/vnd.oci.image.manifest.v1+json":
        config = value.get("config")
        return isinstance(config, dict) and config.get("digest") == config_id
    manifests = value.get("manifests")
    if not isinstance(manifests, list) or not manifests:
        fail("Docker image archive OCI index has no manifests")
    next_ancestors = set(ancestors)
    next_ancestors.add(digest_value)
    return any(
        _descriptor_reaches_config(bundle, child, config_id, next_ancestors)
        for child in manifests
    )


def docker_image_archive_identities(
    archive_path: pathlib.Path, expected_tag: str
) -> dict[str, str]:
    """Return portable config and optional OCI-manifest identities from docker save."""
    try:
        bundle = tarfile.open(archive_path, "r:gz")
    except (OSError, tarfile.TarError) as error:
        fail(f"cannot open Docker image archive: {error}")
    with bundle:
        docker_manifest = _json_bytes(
            _tar_regular_bytes(bundle, "manifest.json"), "manifest.json"
        )
        if not isinstance(docker_manifest, list) or len(docker_manifest) != 1:
            fail("Docker image archive manifest.json must contain exactly one image")
        entry = docker_manifest[0]
        if not isinstance(entry, dict):
            fail("Docker image archive manifest entry must be an object")
        tags = entry.get("RepoTags")
        if not isinstance(tags, list) or expected_tag not in tags:
            fail(f"Docker image archive does not contain expected tag: {expected_tag}")
        config_name = entry.get("Config")
        if not isinstance(config_name, str) or not config_name:
            fail("Docker image archive manifest has no Config")
        config_path = pathlib.PurePosixPath(config_name)
        if config_path.is_absolute() or ".." in config_path.parts:
            fail("Docker image archive Config path is unsafe")
        config_bytes = _tar_regular_bytes(bundle, config_name)
        config_digest = hashlib.sha256(config_bytes).hexdigest()
        config_id = f"sha256:{config_digest}"
        if config_path.parts[:2] == ("blobs", "sha256"):
            if len(config_path.parts) != 3 or config_path.parts[2] != config_digest:
                fail("Docker image archive Config blob name/digest mismatch")
        elif config_path.name.endswith(".json"):
            stem = config_path.name[:-5]
            if SHA256_RE.fullmatch(stem) and stem != config_digest:
                fail("Docker image archive Config file name/digest mismatch")

        manifest_id = ""
        index_bytes = _tar_optional_regular_bytes(bundle, "index.json")
        if index_bytes is not None:
            index = _json_bytes(index_bytes, "index.json")
            if not isinstance(index, dict) or index.get("schemaVersion") != 2:
                fail("Docker image archive index.json is invalid")
            manifests = index.get("manifests")
            if not isinstance(manifests, list) or not manifests:
                fail("Docker image archive index.json has no manifests")
            matches = [
                str(descriptor.get("digest", ""))
                for descriptor in manifests
                if isinstance(descriptor, dict)
                and _descriptor_reaches_config(bundle, descriptor, config_id, set())
            ]
            if len(matches) != 1:
                fail(
                    "Docker image archive index.json must have exactly one top-level "
                    "descriptor that resolves to the selected Config"
                )
            manifest_id = matches[0]
        return {"config_id": config_id, "manifest_id": manifest_id}


def artifact(kind: str, version: str, path: pathlib.Path, **extra: object) -> dict[str, object]:
    sha256, size = digest(path)
    return {
        "kind": kind,
        "version": version,
        "file": path.name,
        "sha256": sha256,
        "bytes": size,
        **extra,
    }


def load_manifest(path: pathlib.Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read manifest: {error}")
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        fail(f"manifest schema must be {SCHEMA}")
    if not SHA_RE.fullmatch(str(value.get("source_sha", ""))):
        fail("manifest source_sha must be a full lowercase Git SHA")
    if not SAFE_NAME_RE.fullmatch(str(value.get("release_id", ""))):
        fail("manifest release_id is invalid")
    if not isinstance(value.get("created_unix"), int) or int(value["created_unix"]) <= 0:
        fail("manifest created_unix must be a positive integer")
    layers = value.get("layers")
    if not isinstance(layers, list) or len(layers) not in (3, 4):
        fail("manifest must contain three or four layers")
    expected = ["base_image", "tools_volume", "program"]
    kinds = [layer.get("kind") for layer in layers if isinstance(layer, dict)]
    if len(kinds) != len(layers) or kinds[:3] != expected:
        fail("manifest layers must start with base_image, tools_volume, program")
    if len(layers) == 4 and kinds[3] != "instance_templates":
        fail("optional fourth manifest layer must be instance_templates")
    names: set[str] = set()
    for layer in layers:
        if not isinstance(layer, dict):
            fail("manifest layer must be an object")
        name = str(layer.get("file", ""))
        if not SAFE_NAME_RE.fullmatch(name) or pathlib.PurePosixPath(name).name != name:
            fail("manifest layer file must be one safe basename")
        if name in names:
            fail("manifest layer files must be unique")
        names.add(name)
        if not SHA256_RE.fullmatch(str(layer.get("sha256", ""))):
            fail(f"manifest layer {name} has an invalid SHA-256")
        if not isinstance(layer.get("bytes"), int) or int(layer["bytes"]) <= 0:
            fail(f"manifest layer {name} has an invalid byte count")
        if not SAFE_NAME_RE.fullmatch(str(layer.get("version", ""))):
            fail(f"manifest layer {name} has an invalid version")
    base = layers[0]
    if not IMAGE_TAG_RE.fullmatch(str(base.get("image_tag", ""))):
        fail("base image_tag is invalid")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(base.get("image_id", ""))):
        fail("base image_id is invalid")
    if not SAFE_NAME_RE.fullmatch(str(layers[2].get("target", ""))):
        fail("program target is invalid")
    return value


def command_create(args: argparse.Namespace) -> None:
    source_sha = args.source_sha
    if not SHA_RE.fullmatch(source_sha):
        fail("--source-sha must be a full lowercase Git SHA")
    paths = [pathlib.Path(value).resolve() for value in [args.base, args.tools, args.program]]
    if any(not path.is_file() for path in paths):
        fail("all three layer archives must be regular files")
    layers = [
        artifact(
            "base_image",
            args.base_version,
            paths[0],
            image_tag=args.base_image_tag,
            image_id=args.base_image_id,
        ),
        artifact("tools_volume", args.tools_version, paths[1]),
        artifact("program", args.program_version, paths[2], target=args.target),
    ]
    if getattr(args, "templates", None):
        templates_path = pathlib.Path(args.templates).resolve()
        if not templates_path.is_file():
            fail("--templates must be a regular archive")
        layers.append(
            artifact("instance_templates", args.templates_version, templates_path)
        )
    manifest = {
        "schema": SCHEMA,
        "release_id": args.release_id,
        "source_sha": source_sha,
        "created_unix": args.created_unix,
        "layers": layers,
    }
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as temporary:
        temporary.write(data)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = pathlib.Path(temporary.name)
    os.replace(temporary_path, output)
    load_manifest(output)


def command_verify(args: argparse.Namespace) -> None:
    manifest_path = pathlib.Path(args.manifest).resolve()
    manifest = load_manifest(manifest_path)
    asset_dir = pathlib.Path(args.asset_dir).resolve()
    for layer in manifest["layers"]:
        path = asset_dir / layer["file"]
        if not path.is_file():
            fail(f"missing release asset: {layer['file']}")
        sha256, size = digest(path)
        if sha256 != layer["sha256"] or size != layer["bytes"]:
            fail(f"release asset digest or size mismatch: {layer['file']}")
    base = layer_by_kind(manifest, "base_image")
    identities = docker_image_archive_identities(
        asset_dir / str(base["file"]), str(base["image_tag"])
    )
    if identities["config_id"] != base["image_id"]:
        fail(
            "base image config identity does not match release manifest: "
            f"expected={base['image_id']} archive={identities['config_id']}"
        )
    print(json.dumps({"ok": True, "release_id": manifest["release_id"]}, sort_keys=True))


def layer_by_kind(manifest: dict[str, object], kind: str) -> dict[str, object]:
    for layer in manifest["layers"]:
        if layer["kind"] == kind:
            return layer
    fail(f"manifest has no layer kind: {kind}")


def command_verify_layer(args: argparse.Namespace) -> None:
    manifest = load_manifest(pathlib.Path(args.manifest).resolve())
    layer = layer_by_kind(manifest, args.kind)
    asset = pathlib.Path(args.asset).resolve()
    if asset.name != layer["file"] or not asset.is_file():
        fail(f"release asset does not match layer {args.kind}: {asset.name}")
    sha256, size = digest(asset)
    if sha256 != layer["sha256"] or size != layer["bytes"]:
        fail(f"release asset digest or size mismatch: {layer['file']}")
    if args.kind == "base_image":
        identities = docker_image_archive_identities(asset, str(layer["image_tag"]))
        if identities["config_id"] != layer["image_id"]:
            fail(
                "base image config identity does not match release manifest: "
                f"expected={layer['image_id']} archive={identities['config_id']}"
            )
    print(
        json.dumps(
            {"kind": args.kind, "ok": True, "release_id": manifest["release_id"]},
            sort_keys=True,
        )
    )


def command_find_installed_layer(args: argparse.Namespace) -> None:
    release_root = pathlib.Path(args.release_root).resolve()
    if not release_root.exists():
        return
    if not release_root.is_dir() or release_root.is_symlink():
        fail("installed release root must be a real directory")
    expected_directory = {"tools_volume": "tools", "program": "program"}[args.kind]
    for release_dir in sorted(release_root.iterdir()):
        if not release_dir.is_dir() or release_dir.is_symlink():
            continue
        manifest_path = release_dir / "manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            continue
        manifest = load_manifest(manifest_path)
        if release_dir.name != manifest["release_id"]:
            fail(f"installed release directory does not match its manifest: {release_dir.name}")
        layer = layer_by_kind(manifest, args.kind)
        if layer["version"] != args.version or layer["sha256"] != args.sha256:
            continue
        layer_directory = release_dir / expected_directory
        if not layer_directory.is_dir() or layer_directory.is_symlink():
            fail(f"installed {args.kind} layer is not a real directory: {release_dir.name}")
        print(layer_directory)
        return


def command_assets(args: argparse.Namespace) -> None:
    manifest = load_manifest(pathlib.Path(args.manifest))
    for layer in manifest["layers"]:
        print(layer["file"])


def command_field(args: argparse.Namespace) -> None:
    value: object = load_manifest(pathlib.Path(args.manifest))
    for component in args.path.split("."):
        if isinstance(value, list):
            try:
                value = value[int(component)]
            except (ValueError, IndexError):
                fail(f"field path is invalid: {args.path}")
        elif isinstance(value, dict) and component in value:
            value = value[component]
        else:
            fail(f"field path is invalid: {args.path}")
    if isinstance(value, (dict, list)):
        print(json.dumps(value, sort_keys=True))
    else:
        print(value)


def command_image_identity(args: argparse.Namespace) -> None:
    identities = docker_image_archive_identities(
        pathlib.Path(args.archive).resolve(), args.image_tag
    )
    print(identities[args.field])


def command_extract(args: argparse.Namespace) -> None:
    archive = pathlib.Path(args.archive).resolve()
    destination = pathlib.Path(args.destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        names: set[str] = set()
        for member in members:
            path = pathlib.PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                fail(f"unsafe archive path: {member.name}")
            if path.parts[0] != args.root:
                fail(f"archive member is outside expected root {args.root}: {member.name}")
            normalized = path.as_posix().rstrip("/")
            if normalized in names:
                fail(f"duplicate archive member: {member.name}")
            names.add(normalized)
            if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                fail(f"unsupported archive member: {member.name}")
        bundle.extractall(destination, members=members)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    for name in [
        "release_id",
        "source_sha",
        "base",
        "base_version",
        "base_image_tag",
        "base_image_id",
        "tools",
        "tools_version",
        "program",
        "program_version",
        "target",
        "output",
    ]:
        create.add_argument("--" + name.replace("_", "-"), required=True)
    create.add_argument("--templates", required=False)
    create.add_argument("--templates-version", required=False)
    create.add_argument("--created-unix", type=int, required=True)
    create.set_defaults(handler=command_create)
    verify = commands.add_parser("verify")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--asset-dir", required=True)
    verify.set_defaults(handler=command_verify)
    verify_layer = commands.add_parser("verify-layer")
    verify_layer.add_argument("--manifest", required=True)
    verify_layer.add_argument(
        "--kind", required=True, choices=["base_image", "tools_volume", "program"]
    )
    verify_layer.add_argument("--asset", required=True)
    verify_layer.set_defaults(handler=command_verify_layer)
    find_installed_layer = commands.add_parser("find-installed-layer")
    find_installed_layer.add_argument("--release-root", required=True)
    find_installed_layer.add_argument(
        "--kind", required=True, choices=["tools_volume", "program"]
    )
    find_installed_layer.add_argument("--version", required=True)
    find_installed_layer.add_argument("--sha256", required=True)
    find_installed_layer.set_defaults(handler=command_find_installed_layer)
    assets = commands.add_parser("assets")
    assets.add_argument("--manifest", required=True)
    assets.set_defaults(handler=command_assets)
    field = commands.add_parser("field")
    field.add_argument("--manifest", required=True)
    field.add_argument("--path", required=True)
    field.set_defaults(handler=command_field)
    image_identity = commands.add_parser("image-identity")
    image_identity.add_argument("--archive", required=True)
    image_identity.add_argument("--image-tag", required=True)
    image_identity.add_argument(
        "--field", required=True, choices=["config_id", "manifest_id"]
    )
    image_identity.set_defaults(handler=command_image_identity)
    extract = commands.add_parser("extract")
    extract.add_argument("--archive", required=True)
    extract.add_argument("--destination", required=True)
    extract.add_argument("--root", required=True, choices=["tools", "program"])
    extract.set_defaults(handler=command_extract)
    return root


def main() -> None:
    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
