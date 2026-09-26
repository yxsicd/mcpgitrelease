#!/usr/bin/env python3
"""Host-side, fail-closed MCPGit online Program updater.

The updater follows the public offline-latest pointer, defers while the host or
instance is busy, and delegates verification, transactional replacement and
rollback to the existing product installer.  It never mounts the Docker socket
inside MCPGit and never mutates the data volume directly.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import platform
import plistlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

POINTER_URL = "https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/offline-latest.json"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(command: list[str], *, timeout: int = 900, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout, check=check)


def state_root() -> Path:
    return Path(os.environ.get("MCPGIT_STATE_DIR", Path.home() / ".mcpgit")) / "auto-upgrade"


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def architecture() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "linux-amd64"
    if machine in {"aarch64", "arm64"}:
        return "linux-arm64"
    fail(f"unsupported architecture: {machine}")


def pointer(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "mcpgit-auto-upgrade/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(1024 * 1024)
    value = json.loads(raw)
    if value.get("schema") != "mcpgit.offline-pointer.v1":
        fail("release pointer schema is not supported")
    source = value.get("source_sha")
    selected = (value.get("architectures") or {}).get(architecture()) or {}
    if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source):
        fail("release pointer source SHA is invalid")
    if selected.get("source_sha") != source or not re.fullmatch(
        r"[0-9a-f]{64}", str(selected.get("manifest_sha256", ""))
    ):
        fail("release pointer architecture selection is invalid")
    return {"source_sha": source, "manifest_sha256": selected["manifest_sha256"],
            "tag": selected.get("tag"), "url": url}


def label(instance: str, key: str) -> str:
    result = run(["docker", "inspect", "--format", f'{{{{index .Config.Labels "{key}"}}}}', instance],
                 timeout=15, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def container_cpu(instance: str) -> float:
    result = run(["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}", instance],
                 timeout=20, check=False)
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)%\s*", result.stdout)
    return float(match.group(1)) if result.returncode == 0 and match else 0.0


def load_per_core() -> float:
    try:
        return os.getloadavg()[0] / max(1, os.cpu_count() or 1)
    except OSError:
        return 0.0


def read_json(path: Path, default: dict) -> dict:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else default
    except (FileNotFoundError, ValueError, OSError):
        return default


def ctl_path() -> str:
    adjacent = Path(__file__).resolve().with_name("mcpgitctl")
    if adjacent.exists():
        return str(adjacent)
    return os.environ.get("MCPGITCTL", "mcpgitctl")


def one_run(args: argparse.Namespace) -> int:
    root = state_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = root / f"{args.instance}.lock"
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"ok": True, "outcome": "already_running", "instance": args.instance}))
            return 0
        policy_path = root / f"{args.instance}.policy.json"
        policy = read_json(policy_path, {})
        if policy.get("enabled") is False:
            print(json.dumps({"ok": True, "outcome": "disabled", "instance": args.instance}))
            return 0
        release = pointer(str(policy.get("pointer_url") or POINTER_URL))
        current = label(args.instance, "org.opencontainers.image.revision")
        receipt_path = root / f"{args.instance}.receipt.json"
        receipt = read_json(receipt_path, {})
        now = int(time.time())
        if current == release["source_sha"]:
            atomic_json(receipt_path, {"schema": "mcpgit.auto-upgrade-receipt.v1",
                        "instance": args.instance, "outcome": "current", "checked_at": now,
                        "source_sha": current, "manifest_sha256": release["manifest_sha256"]})
            print(json.dumps({"ok": True, "outcome": "current", "instance": args.instance,
                              "source_sha": current}))
            return 0
        first_seen = now
        if receipt.get("candidate_source_sha") == release["source_sha"]:
            first_seen = int(receipt.get("candidate_first_seen_at") or now)
        host_load = load_per_core()
        cpu = container_cpu(args.instance)
        max_defer = int(policy.get("max_defer_seconds", 21600))
        busy = host_load > float(policy.get("max_load_per_core", 1.5)) or cpu > float(policy.get("max_container_cpu", 75.0))
        if busy and now - first_seen < max_defer:
            value = {"schema": "mcpgit.auto-upgrade-receipt.v1", "instance": args.instance,
                     "outcome": "deferred_busy", "checked_at": now,
                     "current_source_sha": current, "candidate_source_sha": release["source_sha"],
                     "candidate_first_seen_at": first_seen, "host_load_per_core": host_load,
                     "container_cpu_percent": cpu}
            atomic_json(receipt_path, value)
            print(json.dumps({"ok": True, **value}))
            return 0
        ctl = ctl_path()
        preflight = run([ctl, "--instance", args.instance, "upgrade", "--check"], check=False)
        if preflight.returncode != 0:
            fail("upgrade preflight failed: " + preflight.stdout[-2000:])
        activated = run([ctl, "--instance", args.instance, "upgrade"], timeout=1800, check=False)
        if activated.returncode != 0:
            fail("transactional upgrade failed: " + activated.stdout[-2000:])
        after = label(args.instance, "org.opencontainers.image.revision")
        if after != release["source_sha"]:
            fail(f"upgrade returned success but source is {after or 'missing'}")
        value = {"schema": "mcpgit.auto-upgrade-receipt.v1", "instance": args.instance,
                 "outcome": "upgraded", "checked_at": now, "completed_at": int(time.time()),
                 "previous_source_sha": current, "source_sha": after,
                 "manifest_sha256": release["manifest_sha256"], "forced_after_defer": busy}
        atomic_json(receipt_path, value)
        print(json.dumps({"ok": True, **value}))
        return 0


def install_scheduler(args: argparse.Namespace) -> int:
    root = state_root()
    policy = {"schema": "mcpgit.auto-upgrade-policy.v1", "instance": args.instance,
              "enabled": True, "interval_seconds": args.interval,
              "max_defer_seconds": args.max_defer, "max_load_per_core": args.max_load_per_core,
              "max_container_cpu": args.max_container_cpu, "pointer_url": args.pointer_url}
    atomic_json(root / f"{args.instance}.policy.json", policy)
    executable = str(Path(__file__).resolve())
    if sys.platform == "darwin":
        destination = Path.home() / "Library" / "LaunchAgents" / f"com.yxsicd.mcpgit-auto-upgrade.{args.instance}.plist"
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {"Label": f"com.yxsicd.mcpgit-auto-upgrade.{args.instance}",
                   "ProgramArguments": [sys.executable, executable, "run", "--instance", args.instance],
                   "StartInterval": args.interval, "RunAtLoad": True,
                   "StandardOutPath": str(root / f"{args.instance}.log"),
                   "StandardErrorPath": str(root / f"{args.instance}.log")}
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(plistlib.dumps(payload))
        os.replace(temporary, destination)
        run(["launchctl", "bootout", f"gui/{os.getuid()}", str(destination)], check=False)
        run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(destination)])
        scheduler = str(destination)
    else:
        system_scope = os.geteuid() == 0
        unit_dir = Path("/etc/systemd/system") if system_scope else Path.home() / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        stem = f"mcpgit-auto-upgrade-{args.instance}"
        service = unit_dir / f"{stem}.service"
        timer = unit_dir / f"{stem}.timer"
        service.write_text("[Unit]\nDescription=MCPGit verified online upgrade\n[Service]\nType=oneshot\n" +
                           f"ExecStart={sys.executable} {executable} run --instance {args.instance}\n")
        timer.write_text("[Unit]\nDescription=Check MCPGit release channel\n[Timer]\nOnBootSec=2m\n" +
                         f"OnUnitActiveSec={args.interval}s\nRandomizedDelaySec=90s\nPersistent=true\n" +
                         f"Unit={stem}.service\n[Install]\nWantedBy=timers.target\n")
        systemctl = ["systemctl"] if system_scope else ["systemctl", "--user"]
        run(systemctl + ["daemon-reload"])
        run(systemctl + ["enable", "--now", timer.name])
        scheduler = str(timer)
    print(json.dumps({"ok": True, "outcome": "enabled", "instance": args.instance,
                      "scheduler": scheduler, "policy": policy}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--instance", required=True)
    enable = commands.add_parser("enable")
    enable.add_argument("--instance", required=True)
    enable.add_argument("--interval", type=int, default=900)
    enable.add_argument("--max-defer", type=int, default=21600)
    enable.add_argument("--max-load-per-core", type=float, default=1.5)
    enable.add_argument("--max-container-cpu", type=float, default=75.0)
    enable.add_argument("--pointer-url", default=POINTER_URL)
    args = parser.parse_args()
    if not NAME.fullmatch(args.instance):
        parser.error("invalid instance name")
    try:
        return one_run(args) if args.command == "run" else install_scheduler(args)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "instance": args.instance, "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
