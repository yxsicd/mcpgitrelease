#!/usr/bin/env python3
"""Read-only fresh-install registry and physical Git repository verification."""
import json
from pathlib import Path
import subprocess
import sys

STANDARD_REPOSITORIES = {
    "works", "tablegit", "binary", "rootskills", "mcpgitsystem", "safegit", "systemconfig"
}
RUNTIME_DIRECTORIES = {".mcpgit-runtime"}


def is_git_repository(path):
    if path.is_symlink():
        return False
    if (path / ".git").is_dir():
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
        )
        return result.returncode == 0 and Path(result.stdout.strip()).resolve() == path.resolve()
    # TableGit may use a bare backing. HEAD alone is not proof of a repository:
    # require Git's explicit bare identity and validate its refs/object graph.
    if not (path / "objects").is_dir() or not (path / "refs").is_dir():
        return False
    command = ["git", "--git-dir=" + str(path)]
    result = subprocess.run(
        command + ["rev-parse", "--is-bare-repository"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        return False
    return subprocess.run(
        command + ["fsck", "--connectivity-only", "--no-reflogs", "--no-dangling"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0


def inspect_layout(root):
    root = Path(root)
    registry = {}
    duplicates = []
    for path in sorted((root / "systemconfig/data/tables/system_repositories/rows").rglob("*.json")):
        envelope = json.loads(path.read_text())
        row = envelope.get("row") or {}
        if envelope.get("deleted") or row.get("status", "active") != "active":
            continue
        name = row.get("repository_id")
        if not isinstance(name, str) or name in registry:
            duplicates.append(name)
        registry[name] = row.get("path")
    directories = {path.name for path in root.iterdir() if path.is_dir()}
    physical = directories - RUNTIME_DIRECTORIES
    git_repositories = set()
    for name in physical:
        path = root / name
        if is_git_repository(path):
            git_repositories.add(name)
    checks = {
        "standard_repos_initialized": git_repositories == STANDARD_REPOSITORIES,
        "registry_matches_physical_repos": (
            not duplicates and set(registry) == physical == STANDARD_REPOSITORIES
            and all(registry[name] == str(root / name) for name in STANDARD_REPOSITORIES)
        ),
    }
    return {
        "registered_repositories": registry,
        "physical_repositories": sorted(physical),
        "git_repositories": sorted(git_repositories),
        "runtime_directories": sorted(directories & RUNTIME_DIRECTORIES),
        "checks": checks,
    }


if __name__ == "__main__":
    print(json.dumps(inspect_layout(sys.argv[1]), sort_keys=True))
