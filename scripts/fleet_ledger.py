#!/usr/bin/env python3
"""Collect a redacted MCPGit Docker fleet version ledger."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA = "mcpgitrelease/fleet-ledger/v1"
MCPGIT_NAME_RE = re.compile(r"(mcpgit|yxsgit|hpgit|lrigit|rustc)", re.IGNORECASE)
MC_LABEL_PREFIX = "com.yxsicd.mcpgit."
SAFE_LABEL_SUFFIXES = {
    "source-sha",
    "program-source-sha",
    "binary-revision",
    "manifest-sha256",
    "release-id",
    "release-tag",
    "program-target",
    "data-volume",
    "assembly-sha256",
    "base-image-id",
    "base-manifest-id",
    "base-archive-sha256",
    "tools-archive-sha256",
    "program-archive-sha256",
    "exec.mcpgit-sha256",
    "exec.mcpgitgw-sha256",
    "exec.safe-recover-sha256",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_offline_pointer(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema") != "mcpgit.offline-pointer.v1":
        raise ValueError(f"unsupported offline pointer schema: {value.get('schema')}")
    architectures = value.get("architectures") or {}
    tags: dict[str, str] = {}
    if isinstance(architectures, dict):
        for platform, entry in architectures.items():
            if isinstance(entry, dict) and isinstance(entry.get("tag"), str):
                tags[str(platform)] = entry["tag"]
            elif isinstance(entry, str):
                tags[str(platform)] = entry
    return {
        "schema": value.get("schema"),
        "source_sha": value.get("source_sha"),
        "tags": tags,
    }


def docker_json(args: list[str]) -> Any:
    result = subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE)
    return json.loads(result.stdout) if result.stdout.strip() else None


def docker_container_ids(include_all: bool) -> list[str]:
    cmd = ["docker", "ps"]
    if include_all:
        cmd.append("-a")
    cmd += ["--format", "{{.ID}} {{.Image}} {{.Names}}"]
    result = subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE)
    ids: list[str] = []
    for line in result.stdout.splitlines():
        if MCPGIT_NAME_RE.search(line):
            ids.append(line.split()[0])
    return ids


def safe_labels(labels: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in sorted((labels or {}).items()):
        if not key.startswith(MC_LABEL_PREFIX):
            continue
        suffix = key[len(MC_LABEL_PREFIX) :]
        if suffix in SAFE_LABEL_SUFFIXES:
            result[suffix] = value
    return result


def container_kind(image: str) -> str:
    if image.startswith("mcpgit-offline-runtime:"):
        return "runtime"
    return "support"


def public_latest_match(image: str, labels: dict[str, str], pointer: dict[str, Any] | None) -> str:
    if container_kind(image) != "runtime":
        return "not_applicable"
    if not pointer:
        return "unknown"
    source = pointer.get("source_sha")
    tags = set((pointer.get("tags") or {}).values())
    candidates = {
        labels.get("source-sha"),
        labels.get("program-source-sha"),
        labels.get("binary-revision"),
    }
    if source and source in candidates:
        return "match"
    if image in tags or any(tag and tag in image for tag in tags):
        return "match"
    if source and source in image:
        return "match"
    return "drift"


def published_ports(container: dict[str, Any]) -> list[str]:
    ports = container.get("NetworkSettings", {}).get("Ports") or {}
    values: list[str] = []
    for container_port, bindings in sorted(ports.items()):
        if not bindings:
            continue
        for binding in bindings:
            host_ip = binding.get("HostIp", "")
            host_port = binding.get("HostPort", "")
            values.append(f"{host_ip}:{host_port}->{container_port}")
    return values


def mount_summary(container: dict[str, Any]) -> dict[str, Any]:
    data = None
    config = False
    netrc = False
    for mount in container.get("Mounts", []) or []:
        dest = mount.get("Destination")
        if dest == "/data":
            data = {
                "type": mount.get("Type"),
                "name": mount.get("Name") or None,
                "source_kind": "bind" if mount.get("Type") == "bind" else "volume",
            }
        elif dest == "/config/mcpgit.toml":
            config = True
        elif dest == "/root/.netrc":
            netrc = True
    return {"data": data, "config_mounted": config, "netrc_mounted": netrc}


def container_record(container: dict[str, Any], pointer: dict[str, Any] | None) -> dict[str, Any]:
    config = container.get("Config") or {}
    state = container.get("State") or {}
    name = str(container.get("Name") or "").lstrip("/")
    image = str(config.get("Image") or "")
    labels = safe_labels(config.get("Labels") or {})
    health = None
    if isinstance(state.get("Health"), dict):
        health = state["Health"].get("Status")
    kind = container_kind(image)
    return {
        "name": name,
        "id": str(container.get("Id") or "")[:12],
        "kind": kind,
        "image": image,
        "image_id": str(container.get("Image") or ""),
        "state": state.get("Status"),
        "health": health,
        "restart_count": container.get("RestartCount", 0),
        "ports": published_ports(container),
        "mounts": mount_summary(container),
        "labels": labels,
        "public_latest": public_latest_match(image, labels, pointer),
    }


def collect(pointer_path: str | None, include_all: bool) -> dict[str, Any]:
    pointer = parse_offline_pointer(pointer_path)
    ids = docker_container_ids(include_all)
    containers = docker_json(["docker", "inspect", *ids]) if ids else []
    records = [container_record(item, pointer) for item in containers]
    records.sort(key=lambda item: item["name"])
    return {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "host": socket.gethostname(),
        "include_all": include_all,
        "public_latest_pointer": pointer,
        "summary": {
            "containers": len(records),
            "running": sum(1 for item in records if item.get("state") == "running"),
            "healthy": sum(1 for item in records if item.get("health") == "healthy"),
            "runtime": sum(1 for item in records if item.get("kind") == "runtime"),
            "support": sum(1 for item in records if item.get("kind") == "support"),
            "runtime_drift": sum(1 for item in records if item.get("public_latest") == "drift"),
            "runtime_match": sum(1 for item in records if item.get("public_latest") == "match"),
        },
        "containers": records,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    root.add_argument("--offline-pointer", default="offline-latest.json")
    root.add_argument("--include-all", action="store_true", help="include stopped MCPGit-like containers")
    root.add_argument("--output", default="-", help="output JSON path, or - for stdout")
    return root


def main() -> int:
    args = parser().parse_args()
    value = collect(args.offline_pointer, args.include_all)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        sys.stdout.write(text)
    else:
        Path(args.output).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
