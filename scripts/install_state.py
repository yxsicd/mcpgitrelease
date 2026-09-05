#!/usr/bin/env python3
"""Public installer selection and image-bound receipts; no Actions or grants.

Receipts are private operator state, not signatures. Program updates reuse one
fixed verified image, not the previous update, so image ancestry stays bounded.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tarfile
import tempfile

TARGETS = {"linux-amd64": "x86_64-unknown-linux-musl", "linux-arm64": "aarch64-unknown-linux-musl"}
PREFIX = "com.yxsicd.mcpgit."
PROGRAM = {"mcpgit": "mcpgit", "mcpgitgw": "mcpgitgw", "safe": "mcpgit-safe-recover"}
TOOLS = {"node": "node", "bun": "bun", "credential": "git-credential-netrc"}
SPEC = importlib.util.spec_from_file_location("offline", Path(__file__).with_name("mcpgit-offline-release.py"))
offline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(offline)


class InstallError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise InstallError(message)


def sha(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "expected a regular non-symlink file")
    return offline.digest(path)[0]


def run(args, timeout=30):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    require(result.returncode == 0, "command failed: " + " ".join(args[:3]))
    return result.stdout.strip()


def inspect(kind, name):
    value = json.loads(run(["docker", kind, "inspect", name]))
    require(isinstance(value, list) and len(value) == 1, "ambiguous Docker identity")
    return value[0]


def state_path(instance):
    require(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", instance), "invalid instance name")
    return Path(os.environ.get("MCPGIT_STATE_DIR", str(Path.home() / ".mcpgit/install-state"))) / (instance + ".json")


def private_json(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and stat.S_IMODE(path.stat().st_mode) == 0o600,
            "installation receipt must be a private regular file")
    require(path.stat().st_size < 262144, "installation receipt too large")
    return json.loads(path.read_text())


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(not path.is_symlink() and not path.parent.is_symlink(), "unsafe receipt location")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
        file.write((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())
        file.flush()
        os.fsync(file.fileno())
        name = Path(file.name)
    try:
        os.replace(name, path)
    finally:
        name.unlink(missing_ok=True)


def select(pointer, platform):
    require(pointer.get("schema") == "mcpgit.offline-pointer.v1", "unsupported release pointer")
    source = pointer.get("source_sha")
    require(isinstance(source, str) and re.fullmatch(r"[0-9a-f]{40}", source), "invalid pointer source")
    entries = pointer.get("architectures")
    require(isinstance(entries, dict) and set(entries) == set(TARGETS), "pointer needs both native architectures")
    for arch, target in TARGETS.items():
        entry = entries[arch]
        require(isinstance(entry, dict) and entry.get("source_sha") == source and entry.get("target") == target,
                "pointer architecture/source mismatch")
        require(entry.get("tag") == "mcpgit-git-" + source + "-" + arch, "pointer tag not source-bound")
        require(isinstance(entry.get("manifest_sha256"), str) and
                re.fullmatch(r"[0-9a-f]{64}", entry["manifest_sha256"]), "invalid manifest pin")
    return entries[platform]


def manifest(path, selected=None):
    if selected:
        require(sha(path) == selected["manifest_sha256"], "downloaded manifest differs from selected pointer")
    try:
        value = offline.load_manifest(Path(path))
    except SystemExit:
        raise InstallError("invalid release manifest") from None
    require(value["release_id"] == "git-" + value["source_sha"], "manifest release is not source-bound")
    require(value["layers"][2]["target"] in TARGETS.values(), "new installations require native musl Program")
    if selected:
        require(value["source_sha"] == selected["source_sha"] and value["layers"][2]["target"] == selected["target"],
                "manifest source or target differs from selected pointer")
    return value


def executable_hashes(archive, root, files):
    hashes = {}
    with tarfile.open(archive, "r:gz") as bundle:
        for key, name in files.items():
            items = [m for m in bundle.getmembers() if m.name.lstrip("./") == root + "/bin/" + name]
            if key == "safe" and not items:
                hashes[key] = ""
                continue
            require(len(items) == 1 and items[0].isfile() and items[0].mode & 0o111, "missing executable " + name)
            with bundle.extractfile(items[0]) as stream:
                digest = hashlib.sha256()
                for data in iter(lambda: stream.read(1048576), b""):
                    digest.update(data)
            hashes[key] = digest.hexdigest()
    return hashes


def probe(image, expected, container=False):
    require(set(expected) == set(PROGRAM) | set(TOOLS), "incomplete executable evidence")
    commands = []
    for root, names in (("program", PROGRAM), ("tools", TOOLS)):
        for key, name in names.items():
            path = "/opt/mcpgit/" + root + "/bin/" + name
            if expected[key] == "" and key == "safe":
                commands.append("test ! -e " + path)
            else:
                require(re.fullmatch(r"[0-9a-f]{64}", expected[key]), "invalid executable digest")
                commands.append("test \"$(sha256sum " + path + " | cut -d' ' -f1)\" = " + expected[key])
    args = ["docker", "exec", image] if container else ["docker", "run", "--rm", "--network", "none", "--read-only", "--entrypoint", "sh", image]
    run(args + (["sh"] if container else []) + ["-ec", "; ".join(commands)], timeout=60)


def compatible(saved, candidate, assembly):
    return (saved.get("assembly_sha256") == assembly and
            saved["manifest"]["layers"][:2] == candidate["layers"][:2] and
            saved["manifest"]["layers"][2]["target"] == candidate["layers"][2]["target"])


def supported_configuration(current, image):
    """The simple facade must refuse overrides it cannot faithfully replay."""
    config, original = current['Config'], image['Config']
    for field in ('Cmd', 'Entrypoint', 'User', 'WorkingDir'):
        require(config.get(field) == original.get(field), 'custom process configuration requires its deployment owner')
    original_env = dict(item.split('=', 1) for item in original.get('Env') or [])
    actual = dict(item.split('=', 1) for item in config.get('Env') or [])
    allowed = {'MCPGIT_BOOTSTRAP_REMOTE_REPOS', 'MCPGIT_BOOTSTRAP_REPO_SOURCES',
               'MCPGIT_ALLOWED_HOSTS', 'MCPGIT_PUBLIC_BASE_URL', 'MCPGIT_EXECUTABLE_BUILD_REPOSITORY'}
    require(all(k in allowed or actual.get(k) == original_env.get(k) for k in actual.keys() | original_env.keys()),
            'custom environment requires its deployment owner; no silent deletion')
    expected = {'MCPGIT_BOOTSTRAP_REMOTE_REPOS': '', 'MCPGIT_BOOTSTRAP_REPO_SOURCES': 'none',
                'MCPGIT_ALLOWED_HOSTS': 'localhost,127.0.0.1,::1'}
    require(all(actual.get(k) == v for k, v in expected.items()), 'custom bootstrap or host policy cannot be replayed')
    host = current['HostConfig']
    for key in ('Memory','MemorySwap','NanoCpus','CpuQuota','CpuPeriod','CpuShares','CpusetCpus','CpusetMems',
                'PidsLimit','Privileged','ReadonlyRootfs','CapAdd','CapDrop','Devices','DeviceRequests',
                'SecurityOpt','Ulimits','ExtraHosts','Dns','DnsSearch','VolumesFrom'):
        require(host.get(key) in (None, 0, False, '', []), 'custom resource/security configuration requires its deployment owner')


def preserve(instance):
    current = inspect('container', instance)
    supported_configuration(current, inspect('image', current['Image']))


def plan(path, instance, assembly, strict=False, full=False):
    value = manifest(path)
    answer = {"mode": "full", "foundation_image_id": "", "hashes": {}}
    receipt = state_path(instance)
    if receipt.exists() and not full:
        saved = private_json(receipt)
        require(saved.get("schema") == "mcpgit.install-state.v1" and saved.get("instance") == instance,
                "invalid installation receipt")
        require(saved.get("docker_id") == run(["docker", "info", "--format", "{{.ID}}"]), "receipt belongs to another Docker daemon")
        current = inspect("container", instance)
        require(current["Image"] == saved["image_id"], "current image differs from installed receipt; run explicit full verification")
        if compatible(saved, value, assembly):
            base = inspect("image", saved["foundation_image_id"])
            require(base["Id"] == saved["foundation_image_id"], "fixed foundation missing")
            probe(saved["foundation_image_id"], saved["foundation_hashes"])
            answer = {"mode": "exact" if sha(path) == saved["manifest_sha256"] else "program",
                      "foundation_image_id": saved["foundation_image_id"], "hashes": saved["hashes"]}
            if answer["mode"] == "exact":
                probe(saved["image_id"], saved["hashes"])
            answer["saved"] = saved
    require(not strict or answer["mode"] != "full", "Program-only requires a verified installation and unchanged Base/Tools/assembly; run an explicit full install first")
    return answer


def shell_plan(answer):
    fields = {"install_mode": answer["mode"], "program_parent": answer["foundation_image_id"]}
    for key, name in {"mcpgit":"mcpgit", "mcpgitgw":"mcpgitgw", "safe":"safe_recover", **{x:x for x in TOOLS}}.items():
        fields["expected_" + name + "_sha"] = answer["hashes"].get(key, "")
    return "\n".join(key + "=" + shlex.quote(value) for key, value in fields.items())


def record(args):
    value = manifest(args.manifest)
    previous_plan = json.loads(Path(args.plan).read_text())
    bundle = Path(args.bundle)
    if previous_plan["mode"] == "exact":
        hashes = previous_plan["hashes"]
    else:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                if previous_plan["mode"] == "full":
                    offline.command_verify(argparse.Namespace(manifest=args.manifest, asset_dir=str(bundle)))
                else:
                    offline.command_verify_layer(argparse.Namespace(manifest=args.manifest, kind="program",
                        asset=str(bundle / value["layers"][2]["file"])))
        except SystemExit:
            raise InstallError("package changed before installation receipt") from None
        hashes = executable_hashes(bundle / value["layers"][2]["file"], "program", PROGRAM)
        hashes.update({key: previous_plan["hashes"][key] for key in TOOLS} if previous_plan["mode"] == "program"
                      else executable_hashes(bundle / value["layers"][1]["file"], "tools", TOOLS))
    current = inspect("container", args.instance)
    require(current["State"]["Status"] == "running" and current["State"].get("Health", {}).get("Status") == "healthy", "Docker acceptance not healthy")
    require(current["RestartCount"] == 0, "unexpected restarts")
    labels = current["Config"].get("Labels") or {}
    require(labels.get(PREFIX + "manifest-sha256") == sha(args.manifest), "active manifest label differs")
    require(labels.get(PREFIX + "instance-name") == args.instance, "active instance differs")
    probe(current["Image"], hashes)
    probe(args.instance, hashes, container=True)
    mounts = {m["Destination"]: m for m in current["Mounts"]}
    require(mounts["/data"].get("Name") == args.volume, "active data volume differs")
    require(mounts["/config/mcpgit.toml"]["Source"] == str(Path(args.config).resolve()), "active config differs")
    org = run(["docker", "exec", args.instance, "cat", "/data/.mcpgit-org-id"])
    require(org == labels.get(PREFIX + "instance-id"), "persisted organization differs")
    require(sha(args.credential), "missing generated credential")
    state = {"schema": "mcpgit.install-state.v1", "instance": args.instance, "image_id": current["Image"],
             "docker_id": run(["docker", "info", "--format", "{{.ID}}"]), "manifest": value,
             "manifest_sha256": sha(args.manifest), "assembly_sha256": args.assembly, "hashes": hashes,
             "foundation_image_id": previous_plan["foundation_image_id"] or current["Image"],
             "foundation_hashes": previous_plan.get("saved", {}).get("foundation_hashes", hashes),
             "organization_id": org, "bundle": str(bundle.resolve()), "port": args.port,
             "data_volume": args.volume, "config": str(Path(args.config).resolve()),
             "credential_file": str(Path(args.credential).resolve()), "bin_dir": args.bin_dir,
             "netrc": mounts.get("/root/.netrc", {}).get("Source", ""),
             "executable_build_repository": dict(x.split('=',1) for x in current['Config'].get('Env') or []).get('MCPGIT_EXECUTABLE_BUILD_REPOSITORY', ''),
             "program_chain_depth": 0 if current["Image"] == (previous_plan["foundation_image_id"] or current["Image"]) else 1}
    atomic(state_path(args.instance), state)
    print(json.dumps({"ok": True, "instance": args.instance, "mode": previous_plan["mode"], "state_recorded": True}))


def upgrade(args):
    state = private_json(state_path(args.instance))
    require(state.get("instance") == args.instance, "wrong installation receipt")
    env = dict(os.environ)
    env.update(MCPGIT_BUNDLE_DIR=state["bundle"], MCPGIT_INSTANCE_CONFIG_DIR=str(Path(state["config"]).parent),
               MCPGIT_CREDENTIAL_DIR=str(Path(state["credential_file"]).parent), MCPGIT_BIN_DIR=state["bin_dir"],
               MCPGIT_NETRC=state.get("netrc", ""))
    if 'executable_build_repository' in state:
        env['MCPGIT_EXECUTABLE_BUILD_REPOSITORY'] = state['executable_build_repository']
    else:
        current = inspect('container', args.instance)
        env['MCPGIT_EXECUTABLE_BUILD_REPOSITORY'] = dict(x.split('=',1) for x in current['Config'].get('Env') or []).get('MCPGIT_EXECUTABLE_BUILD_REPOSITORY', '')
    with tempfile.TemporaryDirectory(prefix="mcpgit-upgrade-") as directory:
        file = Path(directory) / "install.sh"
        run(["curl", "-fsSL", "--connect-timeout", "10", "--max-time", "60",
             "https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/install.sh", "-o", str(file)], timeout=70)
        command = ["sh", str(file), "--instance", args.instance, "--port", str(state["port"]),
                   "--data-volume", state["data_volume"], "--program-only"]
        if args.check:
            command.append("--check")
        return subprocess.call(command, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    selected = commands.add_parser("select")
    selected.add_argument("--pointer", required=True)
    selected.add_argument("--platform", choices=TARGETS, required=True)
    selected.add_argument("--output", required=True)
    checked = commands.add_parser("manifest")
    checked.add_argument("--manifest", required=True)
    checked.add_argument("--selection")
    planned = commands.add_parser("plan")
    for key in ("manifest", "instance", "assembly", "output"):
        planned.add_argument("--" + key, required=True)
    planned.add_argument("--program-only", action="store_true")
    planned.add_argument("--full", action="store_true")
    saved = commands.add_parser("record")
    for key in ("manifest", "instance", "assembly", "plan", "bundle", "config", "credential", "volume", "port", "bin-dir"):
        saved.add_argument("--" + key, required=True)
    upgraded = commands.add_parser("upgrade")
    upgraded.add_argument("--instance", required=True)
    upgraded.add_argument("--check", action="store_true")
    preserved = commands.add_parser('preserve')
    preserved.add_argument('--instance', required=True)
    args = parser.parse_args()
    try:
        if args.command == "select":
            entry = select(json.loads(Path(args.pointer).read_text()), args.platform)
            atomic(Path(args.output), entry)
            print(entry["tag"])
        elif args.command == "manifest":
            selected = json.loads(Path(args.selection).read_text()) if args.selection else None
            manifest(args.manifest, selected)
        elif args.command == "plan":
            answer = plan(args.manifest, args.instance, args.assembly, args.program_only, args.full)
            atomic(Path(args.output), answer)
            print(shell_plan(answer))
        elif args.command == "record":
            record(args)
        elif args.command == "upgrade":
            return upgrade(args)
        elif args.command == 'preserve':
            preserve(args.instance)
        return 0
    except (InstallError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print("install-state: " + (str(error) if isinstance(error, InstallError) else type(error).__name__), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
