#!/usr/bin/env python3
"""Idempotently provision MCPGit's built-in systemadmin and Guest policy.

The script edits one SystemConfig Git repository using normal TableGit row
envelopes. It never reads or writes passwords, API keys, Root Seeds, or Agent
Keys. SafeGit creates the password verifier and default managed keys when the
new SystemConfig snapshot is activated on an unlocked instance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


ROW_SCHEMA = "mcpgit.table-row.v1"
TABLE_SCHEMA = "mcpgit.table.v1"


TABLE_DEFINITIONS = {
    "system_instances": {
        "key_field": "instance_id",
        "required_fields": ["instance_id", "zone", "status"],
        "indexes": [{"name": "zone", "field": "zone"}, {"name": "status", "field": "status"}],
    },
    "system_persons": {
        "key_field": "person_id",
        "required_fields": ["person_id", "handle", "display_name", "status"],
        "indexes": [{"name": "handle", "field": "handle"}, {"name": "status", "field": "status"}],
    },
    "system_memberships": {
        "key_field": "membership_id",
        "required_fields": ["membership_id", "person_id", "zone", "status"],
        "indexes": [{"name": "person_id", "field": "person_id"}, {"name": "zone", "field": "zone"}],
    },
    "system_roles": {
        "key_field": "role_id",
        "required_fields": ["role_id", "permissions", "status"],
        "indexes": [{"name": "status", "field": "status"}],
    },
    "system_grants": {
        "key_field": "grant_id",
        "required_fields": ["grant_id", "instance_id", "role_id", "status"],
        "indexes": [
            {"name": "person_id", "field": "person_id"},
            {"name": "role_id", "field": "role_id"},
            {"name": "repository_id", "field": "repository_id"},
        ],
    },
}


def run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def stable_person_id(instance_id: str, handle: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"mcpgit:{instance_id}:person:{handle}"))


def row_path(repo: Path, table: str, key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return repo / "data" / "tables" / table / "rows" / digest[:2] / f"{digest}.json"


def ensure_definition(repo: Path, table: str) -> bool:
    table_root = repo / "data" / "tables" / table
    definition_path = table_root / "_table.json"
    table_root.joinpath("rows").mkdir(parents=True, exist_ok=True)
    if definition_path.exists():
        return False
    definition = {
        "schema": TABLE_SCHEMA,
        **TABLE_DEFINITIONS[table],
        "description": f"MCPGit built-in authentication: {table}",
    }
    definition_path.write_text(json.dumps(definition, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def read_envelope(path: Path, key: str) -> dict | None:
    if not path.exists():
        return None
    envelope = json.loads(path.read_text(encoding="utf-8"))
    if envelope.get("schema") != ROW_SCHEMA or envelope.get("key") != key or envelope.get("deleted"):
        raise ValueError(f"conflicting or invalid TableGit row: {path}")
    if not isinstance(envelope.get("row"), dict):
        raise ValueError(f"TableGit row has no object payload: {path}")
    return envelope


def write_row(repo: Path, table: str, key: str, desired: dict, merge: bool = False) -> bool:
    path = row_path(repo, table, key)
    existing = read_envelope(path, key)
    current = dict(existing["row"]) if existing else {}
    target = {**current, **desired} if merge else desired
    if current == target and existing is not None:
        return False
    if existing is not None and not merge:
        for stable_field in ("person_id", "handle", "membership_id", "role_id", "grant_id"):
            if stable_field in current and current.get(stable_field) != target.get(stable_field):
                raise ValueError(f"refusing to overwrite conflicting {table}/{key} field {stable_field}")
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "schema": ROW_SCHEMA,
        "key": key,
        "row_version": int(existing.get("row_version", 0)) + 1 if existing else 1,
        "deleted": False,
        "recorded_at_unix_ms": int(time.time() * 1000),
        "transaction_id": str(uuid.uuid4()),
        "row": target,
    }
    path.write_text(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return True


def active_handles(repo: Path) -> dict[str, str]:
    handles: dict[str, str] = {}
    root = repo / "data" / "tables" / "system_persons" / "rows"
    if not root.exists():
        return handles
    for path in root.rglob("*.json"):
        envelope = json.loads(path.read_text(encoding="utf-8"))
        row = envelope.get("row") or {}
        if envelope.get("deleted") or row.get("status", "active") != "active":
            continue
        handle = row.get("handle")
        person_id = row.get("person_id")
        if handle and person_id:
            handles[handle] = person_id
    return handles


def bootstrap(repo: Path, instance_id: str, zone: str, guest_repository: str) -> list[str]:
    if not (repo / ".git").exists():
        raise ValueError(f"not a Git repository: {repo}")
    if run_git(repo, "status", "--porcelain").stdout.strip():
        raise ValueError("SystemConfig repository must be clean before built-in auth bootstrap")

    changed: list[str] = []
    for table in TABLE_DEFINITIONS:
        if ensure_definition(repo, table):
            changed.append(f"definition:{table}")

    systemadmin_id = stable_person_id(instance_id, "systemadmin")
    guest_id = stable_person_id(instance_id, "guest")
    builder_id = stable_person_id(instance_id, "builder")
    safe_system_id = stable_person_id(instance_id, "safe-system")
    handles = active_handles(repo)
    for handle, person_id in (
        ("systemadmin", systemadmin_id),
        ("guest", guest_id),
        ("builder", builder_id),
        ("safe-system", safe_system_id),
    ):
        owner = handles.get(handle)
        if owner is not None and owner != person_id:
            raise ValueError(f"active handle {handle} is already owned by {owner}")

    builder_repositories = [
        repository.strip()
        for repository in (os.environ.get("MCPGIT_BUILDER_REPOSITORIES", "works,tablegit,binarygit").split(","))
        if repository.strip()
    ]
    if not builder_repositories:
        raise ValueError("at least one builder repository is required")

    desired_rows: list[tuple[str, str, dict, bool]] = [
        (
            "system_instances",
            instance_id,
            {
                "instance_id": instance_id,
                "zone": zone,
                "status": "active",
                "mcp_person_verify_enabled": True,
            },
            True,
        ),
        (
            "system_persons",
            systemadmin_id,
            {
                "person_id": systemadmin_id,
                "handle": "systemadmin",
                "display_name": "System Administrator",
                "status": "active",
            },
            False,
        ),
        (
            "system_persons",
            guest_id,
            {"person_id": guest_id, "handle": "guest", "display_name": "Guest", "status": "active"},
            False,
        ),
        (
            "system_persons",
            builder_id,
            {
                "person_id": builder_id,
                "handle": "builder",
                "display_name": "Works Builder",
                "status": "active",
            },
            False,
        ),
        (
            "system_persons",
            safe_system_id,
            {
                "person_id": safe_system_id,
                "handle": "safe-system",
                "display_name": "SafeGit system",
                "status": "active",
            },
            False,
        ),
        (
            "system_memberships",
            "builtin-systemadmin-membership",
            {
                "membership_id": "builtin-systemadmin-membership",
                "person_id": systemadmin_id,
                "zone": zone,
                "status": "active",
            },
            False,
        ),
        (
            "system_memberships",
            "builtin-guest-membership",
            {
                "membership_id": "builtin-guest-membership",
                "person_id": guest_id,
                "zone": zone,
                "status": "active",
            },
            False,
        ),
        (
            "system_memberships",
            "builtin-builder-membership",
            {
                "membership_id": "builtin-builder-membership",
                "person_id": builder_id,
                "zone": zone,
                "status": "active",
            },
            False,
        ),
        (
            "system_roles",
            "builtin-connect",
            {"role_id": "builtin-connect", "permissions": ["mcp.connect"], "status": "active"},
            False,
        ),
        (
            "system_roles",
            "builtin-systemadmin-control",
            {
                "role_id": "builtin-systemadmin-control",
                "permissions": ["mcp.admin", "safe.read", "safe.write", "safe.admin"],
                "status": "active",
            },
            False,
        ),
        (
            "system_roles",
            "builtin-guest-reader",
            {
                "role_id": "builtin-guest-reader",
                "permissions": ["repo.read", "table.read", "binary.read"],
                "status": "active",
            },
            False,
        ),
        (
            "system_roles",
            "builtin-builder",
            {
                "role_id": "builtin-builder",
                "permissions": [
                    "repo.read",
                    "repo.write",
                    "table.read",
                    "table.write",
                    "binary.read",
                    "binary.write",
                ],
                "status": "active",
            },
            False,
        ),
        (
            "system_grants",
            "builtin-systemadmin-connect",
            {
                "grant_id": "builtin-systemadmin-connect",
                "person_id": systemadmin_id,
                "instance_id": instance_id,
                "role_id": "builtin-connect",
                "repository_id": None,
                "resource": None,
                "status": "active",
            },
            False,
        ),
        (
            "system_grants",
            "builtin-guest-connect",
            {
                "grant_id": "builtin-guest-connect",
                "person_id": guest_id,
                "instance_id": instance_id,
                "role_id": "builtin-connect",
                "repository_id": None,
                "resource": None,
                "status": "active",
            },
            False,
        ),
        (
            "system_grants",
            "builtin-systemadmin-control",
            {
                "grant_id": "builtin-systemadmin-control",
                "person_id": systemadmin_id,
                "instance_id": instance_id,
                "role_id": "builtin-systemadmin-control",
                "repository_id": None,
                "resource": None,
                "status": "active",
            },
            False,
        ),
        (
            "system_grants",
            "builtin-guest-reader",
            {
                "grant_id": "builtin-guest-reader",
                "person_id": guest_id,
                "instance_id": instance_id,
                "role_id": "builtin-guest-reader",
                "repository_id": guest_repository,
                "resource": None,
                "status": "active",
            },
            False,
        ),
        (
            "system_grants",
            "builtin-builder-connect",
            {
                "grant_id": "builtin-builder-connect",
                "person_id": builder_id,
                "instance_id": instance_id,
                "role_id": "builtin-connect",
                "repository_id": None,
                "resource": None,
                "status": "active",
            },
            False,
        ),
    ]
    for repository_id in builder_repositories:
        grant_id = f"builtin-builder-{repository_id}"
        desired_rows.append(
            (
                "system_grants",
                grant_id,
                {
                    "grant_id": grant_id,
                    "person_id": builder_id,
                    "instance_id": instance_id,
                    "role_id": "builtin-builder",
                    "repository_id": repository_id,
                    "resource": None,
                    "status": "active",
                },
                False,
            )
        )
    for table, key, row, merge in desired_rows:
        if write_row(repo, table, key, row, merge=merge):
            changed.append(f"row:{table}/{key}")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--zone", required=True)
    parser.add_argument("--guest-repository", default="works")
    parser.add_argument(
        "--builder-repositories",
        default=None,
        help="comma-separated business repositories granted to the built-in builder Person (default: works,tablegit,binarygit)",
    )
    parser.add_argument("--apply", action="store_true", help="write and commit instead of reporting the planned change")
    parser.add_argument("--no-commit", action="store_true", help="write rows but leave the Git commit to the caller")
    args = parser.parse_args()

    repo = args.repo.resolve()
    if args.builder_repositories is not None:
        os.environ["MCPGIT_BUILDER_REPOSITORIES"] = args.builder_repositories
    if not args.apply:
        print(json.dumps({"outcome": "dry_run", "repo": str(repo), "instance_id": args.instance_id, "zone": args.zone}))
        return 0
    changed = bootstrap(repo, args.instance_id, args.zone, args.guest_repository)
    if changed and not args.no_commit:
        run_git(repo, "add", "data/tables")
        run_git(
            repo,
            "-c",
            "user.name=MCPGit Bootstrap",
            "-c",
            "user.email=mcpgit-bootstrap@example.invalid",
            "commit",
            "-m",
            "config(auth): bootstrap systemadmin and guest",
        )
    result = {
        "outcome": "changed" if changed else "no_change",
        "repo": str(repo),
        "instance_id": args.instance_id,
        "zone": args.zone,
        "systemadmin_person_id": stable_person_id(args.instance_id, "systemadmin"),
        "guest_person_id": stable_person_id(args.instance_id, "guest"),
        "builder_person_id": stable_person_id(args.instance_id, "builder"),
        "safe_system_person_id": stable_person_id(args.instance_id, "safe-system"),
        "changed": changed,
        "committed": bool(changed and not args.no_commit),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"bootstrap-builtin-auth: {error}", file=sys.stderr)
        raise SystemExit(2)
