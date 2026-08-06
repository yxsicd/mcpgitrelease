#!/bin/sh
set -eu

# One-command MCPGit install: download the latest offline release from GitHub,
# assemble the runtime image, start the instance, and print a real connection
# you can use immediately. Run it as:
#
#   curl -fsSL https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/deploy/novice-install.sh | sh -s --
#
# Everything below has defaults that work as-is; change them via environment
# variables (recommended ones are marked 建议改).

# ===== environment configuration (defaults work as-is) =====
# 发布指针：公开库 offline-latest.json 指向最新离线 release（可改：自定义版本指针）
MCPGIT_CHANNEL_URL="${MCPGIT_CHANNEL_URL:-https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/offline-latest.json}"
# 实例名：容器/数据卷/配置名（建议改：每个环境唯一，例如 mcpgit-demo）
MCPGIT_INSTANCE="${MCPGIT_INSTANCE:-mcpgit}"
# 不可变组织 id（UUID）：实例核心身份，persons/grants/SafeGit 都绑定它；
# 名字可改，id 不可改。留空时首次安装自动生成并持久化到数据卷。
MCPGIT_ORG_ID="${MCPGIT_ORG_ID:-}"
# 服务端口：对外 MCP/Service 端口（可改：端口冲突时）
MCPGIT_PORT="${MCPGIT_PORT:-8001}"
# 数据卷：实例专属持久卷（建议改：正式环境用独立命名，如 mcpgit-demo-data）
MCPGIT_DATA_VOLUME="${MCPGIT_DATA_VOLUME:-}"
# 认证 zone：built-in auth 区域（可改：blue/green）
MCPGIT_ZONE="${MCPGIT_ZONE:-blue}"
# GitHub netrc：可选；不配则离线运行，之后可再配远端同步（可改）
MCPGIT_NETRC="${MCPGIT_NETRC:-}"
# bundle 目录：下载缓存位置（可改：磁盘空间紧张时换目录）
MCPGIT_BUNDLE_DIR="${MCPGIT_BUNDLE_DIR:-$HOME/.mcpgit/bundle}"
# 固定 release tag：显式指定时跳过 channel 解析，用于回滚/固定版本（建议改：仅在回滚时）
MCPGIT_RELEASE_TAG="${MCPGIT_RELEASE_TAG:-}"
# ===== do not edit below =====

fetch_bundle() {
  tag=$1
  target=$2
  mkdir -p "$target"
  base_url="https://github.com/yxsicd/mcpgitrelease/releases/download/$tag"
  echo "==> fetching offline release $tag"
  curl -fsSL --retry 5 --retry-delay 5 --retry-all-errors \
    "$base_url/mcpgit-offline-release-v1.json" -o "$target/mcpgit-offline-release-v1.json"
  manifest="$target/mcpgit-offline-release-v1.json"
  layer_list=$(mktemp "${TMPDIR:-/tmp}/mcpgit-layers.XXXXXX")
  trap 'rm -f "$layer_list"' EXIT INT TERM
  python3 - "$manifest" > "$layer_list" <<'PY'
import json
import sys
for layer in json.load(open(sys.argv[1]))["layers"]:
    print(layer["file"], layer["sha256"])
PY
  while read -r file expected; do
    [ -n "$file" ] || continue
    if [ -f "$target/$file" ]; then
      actual=$(shasum -a 256 "$target/$file" | awk '{print $1}')
      [ "$actual" = "$expected" ] && { echo "    unchanged: $file (cached)"; continue; }
      echo "    changed: $file"
    fi
    echo "    download: $file"
    curl -fsSL --retry 5 --retry-delay 5 --retry-all-errors \
      "$base_url/$file" -o "$target/$file"
  done < "$layer_list"
  mkdir -p "$target/scripts"
  for helper in scripts/mcpgit-offline-release.py scripts/bootstrap-builtin-auth.py; do
    if [ ! -f "$target/$helper" ]; then
      curl -fsSL --retry 5 --retry-delay 5 \
        "https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/$helper" \
        -o "$target/$helper"
    fi
  done
  if [ ! -f "$target/Dockerfile.offline-runtime" ]; then
    curl -fsSL --retry 5 --retry-delay 5 \
      "https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/Dockerfile.offline-runtime" \
      -o "$target/Dockerfile.offline-runtime"
  fi
  python3 "$target/scripts/mcpgit-offline-release.py" verify \
    --manifest "$manifest" --asset-dir "$target"
}

resolve_tag() {
  if [ -n "$MCPGIT_RELEASE_TAG" ]; then
    echo "$MCPGIT_RELEASE_TAG"
    return 0
  fi
  curl -fsSL --retry 5 --retry-delay 5 "$MCPGIT_CHANNEL_URL" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag"])'
}

usage() {
  cat <<'EOF'
Usage: novice-install.sh [options]

  --bundle DIR        offline bundle directory (default: $MCPGIT_BUNDLE_DIR,
                      auto-downloaded from the latest release when absent)
  --instance NAME     instance name (default: $MCPGIT_INSTANCE)
  --data-volume VOL   named data volume (default: <instance>_data)
  --netrc FILE        GitHub netrc for remote repo sync (optional, offline-first)
  --zone ZONE         built-in auth zone (default: $MCPGIT_ZONE)
  --port PORT         host port for the Service endpoint (default: $MCPGIT_PORT)
  --guest-repo REPO   guest-readable repo (default: works)
  --builder-repos R   builder repos, comma separated (default: works,tablegit,binarygit)
  --download-only     download the bundle and stop (no Docker needed for this)
  --rebuild           force rebuilding the offline runtime image
All settings can also be set via MCPGIT_* environment variables; see the top
of this script for defaults and which ones to customize.
EOF
  exit 1
}

bundle=${MCPGIT_BUNDLE_DIR}
instance=${MCPGIT_INSTANCE}
data_volume=${MCPGIT_DATA_VOLUME}
netrc=${MCPGIT_NETRC}
zone=${MCPGIT_ZONE}
port=${MCPGIT_PORT}
guest_repo=works
builder_repos=works,tablegit,binarygit
rebuild=false
download_only=false
while [ $# -gt 0 ]; do
  case "$1" in
    --bundle) bundle=$2; shift 2 ;;
    --instance) instance=$2; shift 2 ;;
    --data-volume) data_volume=$2; shift 2 ;;
    --netrc) netrc=$2; shift 2 ;;
    --zone) zone=$2; shift 2 ;;
    --port) port=$2; shift 2 ;;
    --guest-repo) guest_repo=$2; shift 2 ;;
    --builder-repos) builder_repos=$2; shift 2 ;;
    --download-only) download_only=true; shift ;;
    --rebuild) rebuild=true; shift ;;
    *) usage ;;
  esac
done
[ -n "$instance" ] || usage

if [ -z "$bundle" ] \
  || [ ! -f "$bundle/mcpgit-offline-release-v1.json" ] \
  || [ ! -f "$bundle/scripts/mcpgit-offline-release.py" ]; then
  tag=$(resolve_tag)
  [ -n "$tag" ] || { echo "cannot resolve offline release tag" >&2; exit 1; }
  fetch_bundle "$tag" "$bundle"
fi

if [ "$download_only" = true ]; then
  echo "PASS: bundle ready at $bundle (no Docker required for downloading)"
  echo "Copy the directory to the install machine, then run:"
  echo "  deploy/novice-install.sh --bundle $bundle --instance $instance"
  exit 0
fi

manifest="$bundle/mcpgit-offline-release-v1.json"
if [ ! -f "$manifest" ]; then
  manifest="$bundle/offline-release-v1.json"
fi
parser="$bundle/scripts/mcpgit-offline-release.py"
bootstrap="$bundle/scripts/bootstrap-builtin-auth.py"
dockerfile="$bundle/Dockerfile.offline-runtime"
[ -f "$manifest" ] || { echo "bundle missing manifest: $manifest" >&2; exit 1; }
[ -f "$parser" ] || { echo "bundle missing parser: $parser" >&2; exit 1; }
[ -f "$bootstrap" ] || { echo "bundle missing bootstrap script: $bootstrap" >&2; exit 1; }
[ -f "$dockerfile" ] || { echo "bundle missing Dockerfile.offline-runtime" >&2; exit 1; }

echo "==> verifying bundle integrity"
python3 "$parser" verify --manifest "$manifest" --asset-dir "$bundle"

field() {
  python3 "$parser" field --manifest "$manifest" --path "$1"
}

base_archive="$bundle/$(field layers.0.file)"
base_image_tag=$(field layers.0.image_tag)
base_version=$(field layers.0.version)
base_image_id=$(field layers.0.image_id)
tools_archive="$bundle/$(field layers.1.file)"
tools_version=$(field layers.1.version)
program_archive="$bundle/$(field layers.2.file)"
program_version=$(field layers.2.version)
templates_archive="$(field layers.3.file 2>/dev/null || true)"
release_id=$(field release_id)
source_sha=$(field source_sha)
base_archive_sha=$(field layers.0.sha256)
tools_archive_sha=$(field layers.1.sha256)
program_archive_sha=$(field layers.2.sha256)

echo "==> loading base image ($base_image_tag)"
if docker image inspect "$base_image_tag" >/dev/null 2>&1; then
  echo "    already present"
else
  docker load < "$base_archive"
fi

runtime_image="mcpgit-offline-runtime:offline"
[ -n "$data_volume" ] || data_volume="${instance}_data"
update_mode=false
if docker volume inspect "$data_volume" >/dev/null 2>&1; then
  update_mode=true
fi
deployed_program_version=
if docker image inspect "$runtime_image" >/dev/null 2>&1; then
  deployed_program_version=$(docker image inspect \
    --format '{{index .Config.Labels "com.yxsicd.mcpgit.program-version"}}' \
    "$runtime_image" 2>/dev/null || true)
fi
if [ "$update_mode" = true ]; then
  echo "==> existing instance detected: update mode (data volume preserved)"
fi

work_dir="${MCPGIT_INSTANCE_CONFIG_DIR:-$HOME/.mcpgit}"
mkdir -p "$work_dir"
ctx=$(mktemp -d "$work_dir/work.XXXXXX")
trap 'rm -rf "$ctx"' EXIT INT TERM
echo "==> unpacking program and tools"
tar -xzf "$program_archive" -C "$ctx"
tar -xzf "$tools_archive" -C "$ctx"
cp "$dockerfile" "$ctx/Dockerfile.offline-runtime"

exec_sha() {
  shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'
}

if [ "$rebuild" = true ] \
  || ! docker image inspect "$runtime_image" >/dev/null 2>&1 \
  || [ "$deployed_program_version" != "$program_version" ]; then
  echo "==> assembling offline runtime image ($runtime_image)"
  docker build \
    --file "$ctx/Dockerfile.offline-runtime" \
    --build-arg "MCPGIT_BASE_IMAGE=$base_image_tag" \
    --build-arg "MCPGIT_SOURCE_SHA=$source_sha" \
    --build-arg "MCPGIT_RELEASE_ID=$release_id" \
    --build-arg "MCPGIT_BASE_VERSION=$base_version" \
    --build-arg "MCPGIT_BASE_IMAGE_ID=$base_image_id" \
    --build-arg "MCPGIT_TOOLS_VERSION=$tools_version" \
    --build-arg "MCPGIT_PROGRAM_VERSION=$program_version" \
    --build-arg "MCPGIT_BASE_ARCHIVE_SHA256=$base_archive_sha" \
    --build-arg "MCPGIT_TOOLS_ARCHIVE_SHA256=$tools_archive_sha" \
    --build-arg "MCPGIT_PROGRAM_ARCHIVE_SHA256=$program_archive_sha" \
    --build-arg "MCPGIT_EXEC_MCPGIT_SHA256=$(exec_sha "$ctx/program/bin/mcpgit")" \
    --build-arg "MCPGIT_EXEC_MCPGITGW_SHA256=$(exec_sha "$ctx/program/bin/mcpgitgw")" \
    --build-arg "MCPGIT_EXEC_NODE_SHA256=$(exec_sha "$ctx/tools/bin/node")" \
    --build-arg "MCPGIT_EXEC_BUN_SHA256=$(exec_sha "$ctx/tools/bin/bun")" \
    --build-arg "MCPGIT_EXEC_CREDENTIAL_SHA256=$(exec_sha "$ctx/tools/bin/git-credential-netrc")" \
    --tag "$runtime_image" \
    "$ctx"
else
  echo "==> offline runtime image already present: $runtime_image"
fi

org_id=${MCPGIT_ORG_ID:-}
if [ -z "$org_id" ] && docker volume inspect "$data_volume" >/dev/null 2>&1; then
  org_id=$(docker run --rm -v "$data_volume":/data \
    --entrypoint sh "$runtime_image" -c \
    'cat /data/.mcpgit-org-id 2>/dev/null || true' 2>/dev/null \
    | tr -d '[:space:]')
fi
if [ -z "$org_id" ]; then
  org_id=$(python3 -c 'import uuid; print(uuid.uuid4())')
fi
echo "==> organization id (immutable identity): $org_id"

repos="works rootskills mcpgitsystem safegit systemconfig tablegit binarygit"
if [ "$update_mode" = false ]; then
  echo "==> preparing data volume $data_volume"
  docker volume create "$data_volume" >/dev/null
  if [ -n "$templates_archive" ] && [ -f "$bundle/$templates_archive" ]; then
    cp "$bundle/$templates_archive" "$ctx/instance-templates.tar.gz"
    docker run --rm -e ORG_ID="$org_id" \
      -v "$data_volume":/data -v "$ctx":/provision:ro \
      --entrypoint sh "$runtime_image" -c '
        set -eu
        mkdir -p /data/repos
        tar -xzf /provision/instance-templates.tar.gz -C /data/repos
        for r in works rootskills mcpgitsystem safegit systemconfig tablegit binarygit; do
          dir=/data/repos/$r
          if [ ! -d "$dir/.git" ]; then
            git -C "$dir" init --initial-branch=main -q
            git -C "$dir" config user.name mcpgit
            git -C "$dir" config user.email mcpgit@example.invalid
            git -C "$dir" add .
            git -C "$dir" commit -qm "Initialize $r from template"
          fi
        done
        printf "%s\n" "$ORG_ID" > /data/.mcpgit-org-id
      '
  else
    docker run --rm -v "$data_volume":/data --entrypoint sh "$runtime_image" -c "
set -eu
for r in $repos; do
  dir=/data/repos/\$r
  if [ -d \"\$dir/.git\" ]; then continue; fi
  mkdir -p \"\$dir\"
  git -C \"\$dir\" init --initial-branch=main -q
  git -C \"\$dir\" config user.name mcpgit
  git -C \"\$dir\" config user.email mcpgit@example.invalid
  echo \"# \$r\" > \"\$dir/README.md\"
  git -C \"\$dir\" add .
  git -C \"\$dir\" commit -qm init
done
printf "%s\n" "$org_id" > /data/.mcpgit-org-id
"
  fi
fi

config_dir="${MCPGIT_INSTANCE_CONFIG_DIR:-$HOME/.mcpgit/instances}"
mkdir -p "$config_dir"
config="$config_dir/$instance.toml"
if [ ! -f "$config" ] || ! grep -q "instance_id = \"$org_id\"" "$config" 2>/dev/null; then
  {
    echo "[system_config]"
    echo "instance_id = \"$org_id\""
    echo "path = \"/data/repos/systemconfig\""
    echo "revision = \"refs/heads/main\""
  } > "$config"
fi

if [ "$update_mode" = false ]; then
cat > "$ctx/provision-repositories.py" <<'PY'
#!/usr/bin/env python3
import argparse
import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path

ROW = "mcpgit.table-row.v1"
TABLE = "mcpgit.table.v1"


def row_path(repo: Path, table: str, key: str) -> Path:
    digest = hashlib.sha256(key.encode()).hexdigest()
    return repo / "data" / "tables" / table / "rows" / digest[:2] / f"{digest}.json"


def ensure_table(repo: Path, table: str, definition: dict) -> Path:
    table_root = repo / "data" / "tables" / table
    table_root.joinpath("rows").mkdir(parents=True, exist_ok=True)
    definition_path = table_root / "_table.json"
    if not definition_path.exists():
        definition_path.write_text(
            json.dumps(definition, indent=2) + "\n"
        )
    return table_root


def write_row(repo: Path, table: str, key: str, row: dict) -> None:
    target = row_path(repo, table, key)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return
    target.write_text(
        json.dumps(
            {
                "schema": ROW,
                "key": key,
                "row_version": 1,
                "deleted": False,
                "recorded_at_unix_ms": int(time.time() * 1000),
                "transaction_id": str(uuid.uuid4()),
                "row": row,
            },
            indent=2,
        )
        + "\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--instance-id", required=True)
    ap.add_argument("--repos", required=True)
    args = ap.parse_args()
    repo = Path(args.repo)
    ensure_table(
        repo,
        "system_repositories",
        {
            "schema": TABLE,
            "key_field": "repository_id",
            "required_fields": ["instance_id", "repository_id", "path"],
            "indexes": [],
            "description": "MCPGit instance repository paths",
        },
    )
    ensure_table(
        repo,
        "system_grants",
        {
            "schema": TABLE,
            "key_field": "grant_id",
            "required_fields": ["grant_id", "instance_id", "role_id", "status"],
            "indexes": [
                {"name": "person_id", "field": "person_id"},
                {"name": "role_id", "field": "role_id"},
                {"name": "repository_id", "field": "repository_id"},
            ],
            "description": "MCPGit instance role grants",
        },
    )
    for spec in args.repos.split(","):
        rid, path = spec.split("=", 1)
        mode = "read-write"
        if ";" in path:
            path, mode = path.split(";", 1)
        write_row(
            repo,
            "system_repositories",
            rid,
            {
                "instance_id": args.instance_id,
                "repository_id": rid,
                "path": path,
                "mode": mode,
            },
        )
    systemadmin_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"mcpgit:{args.instance_id}:person:systemadmin")
    )
    write_row(
        repo,
        "system_grants",
        "builtin-systemadmin-rootskills",
        {
            "grant_id": "builtin-systemadmin-rootskills",
            "person_id": systemadmin_id,
            "instance_id": args.instance_id,
            "role_id": "builtin-builder",
            "repository_id": "rootskills",
            "resource": None,
            "status": "active",
        },
    )
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "commit",
            "--allow-empty",
            "-m",
            "Provision system repositories",
        ],
        check=True,
    )


main()
PY

repo_specs=
for r in $repos; do
  [ -n "$repo_specs" ] && repo_specs="$repo_specs,"
  repo_specs="${repo_specs}${r}=/data/repos/${r}"
done
docker run --rm \
  -v "$data_volume":/data \
  -v "$ctx":/provision:ro \
  --entrypoint python3 \
  "$runtime_image" \
  /provision/provision-repositories.py \
  --repo /data/repos/systemconfig \
  --instance-id "$org_id" \
  --repos "$repo_specs"

echo "==> provisioning built-in auth persons"
cp "$bootstrap" "$ctx/bootstrap-builtin-auth.py"
docker run --rm \
  -v "$ctx":/bundle:ro \
  -v "$data_volume":/data \
  --entrypoint python3 \
  "$runtime_image" \
  /bundle/bootstrap-builtin-auth.py \
  --repo /data/repos/systemconfig \
  --instance-id "$org_id" \
  --zone "$zone" \
    --guest-repository "$guest_repo" \
    --builder-repositories "$builder_repos" \
    --apply
fi

echo "==> starting instance $instance (port $port)"
docker rm -f "$instance" >/dev/null 2>&1 || true
docker run -d \
  --name "$instance" \
  --restart unless-stopped \
  -v "$data_volume":/data \
  -v "$config":/config/mcpgit.toml:ro \
  ${netrc:+-v "$netrc":/root/.netrc:ro} \
  -e MCPGIT_BOOTSTRAP_REMOTE_REPOS= \
  -e MCPGIT_BOOTSTRAP_REPO_SOURCES=none \
  -e MCPGIT_ALLOWED_HOSTS=localhost,127.0.0.1,::1 \
  -e MCPGIT_PUBLIC_BASE_URL="http://127.0.0.1:$port" \
  -p "$port":8001 \
  "$runtime_image" >/dev/null

echo "==> waiting for health"
deadline=$(( $(date +%s) + 120 ))
until [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/healthz" 2>/dev/null || true)" = "204" ]; do
  [ "$(date +%s)" -lt "$deadline" ] || { echo "instance did not become healthy" >&2; docker logs "$instance" | tail -40 >&2; exit 1; }
  sleep 2
done

echo
if [ "$update_mode" = true ]; then
  echo "PASS: updated instance $instance (program $deployed_program_version -> $program_version)"
else
  echo "PASS: offline instance $instance is healthy"
fi
echo "  skills table: run Service table.initialize (repo=rootskills,"
echo "    root=.agents/skills) once; see rootskills/docs/SKILLS_TABLE.md"
echo "  organization id (immutable identity): $org_id"
echo "  instance name (renameable label): $instance"
echo "  endpoint:  http://127.0.0.1:$port"
echo "  data volume: $data_volume"
if [ "$update_mode" = false ]; then
  echo "  first login: systemadmin / change-me (change it after login)"
  echo
  echo "SafeGit novice material (from container logs):"
  docker logs "$instance" 2>&1 | grep 'novice mode' || true
  echo
  shares_path=$(docker logs "$instance" 2>&1 \
    | sed -n 's/.*Shamir 3-of-5 shares persisted at //p' | tail -1)
  if [ -n "$shares_path" ]; then
    echo "Copy the persisted Shamir shares file to an external location"
    echo "  docker cp $instance:$shares_path ./${instance}-shares.json"
    echo "It is the only recovery path if the whole volume is lost."
  fi
fi
