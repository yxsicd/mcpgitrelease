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
# 安装内容快照：根 install.sh 会把它固定到一次解析出的 main Git SHA，
# 避免同一轮安装从区域 CDN 混到不同代的 helper / Dockerfile / wrapper。
MCPGIT_INSTALL_CONTENT_BASE="${MCPGIT_INSTALL_CONTENT_BASE:-https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main}"
MCPGIT_INSTALL_CONTENT_BASE="${MCPGIT_INSTALL_CONTENT_BASE%/}"
# 发布指针：根 install.sh 默认把它固定到同一个安装快照中的
# offline-latest.json；直接运行本脚本时保留 main 兼容路径。
MCPGIT_CHANNEL_URL="${MCPGIT_CHANNEL_URL:-$MCPGIT_INSTALL_CONTENT_BASE/offline-latest.json}"
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
# 私有凭据目录：fresh install 会把随机 systemadmin Basic 凭据写到这里，0600。
MCPGIT_CREDENTIAL_DIR="${MCPGIT_CREDENTIAL_DIR:-$HOME/.mcpgit/credentials}"
# ===== do not edit below =====

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo "MCPGit installer requires sha256sum or shasum" >&2
    return 1
  fi
}

fetch_snapshot_file() (
  snapshot_source=$1
  snapshot_target=$2
  snapshot_temporary="${snapshot_target}.tmp.$$"
  rm -f "$snapshot_temporary"
  if ! curl -fsSL --retry 5 --retry-delay 5 --retry-all-errors \
    "$snapshot_source" -o "$snapshot_temporary"; then
    rm -f "$snapshot_temporary"
    return 1
  fi
  mv "$snapshot_temporary" "$snapshot_target"
)

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
      actual=$(sha256_file "$target/$file")
      [ "$actual" = "$expected" ] && { echo "    unchanged: $file (cached)"; continue; }
      echo "    changed: $file"
    fi
    echo "    download: $file"
    curl -fsSL --retry 5 --retry-delay 5 --retry-all-errors \
      "$base_url/$file" -o "$target/$file"
  done < "$layer_list"
  rm -f "$layer_list"
  mkdir -p "$target/scripts"
  for helper in scripts/mcpgit-offline-release.py scripts/bootstrap-builtin-auth.py; do
    fetch_snapshot_file "$MCPGIT_INSTALL_CONTENT_BASE/$helper" "$target/$helper"
  done
  fetch_snapshot_file \
    "$MCPGIT_INSTALL_CONTENT_BASE/Dockerfile.offline-runtime" \
    "$target/Dockerfile.offline-runtime"
  for product_file in novice-install.sh mcpgit-install.sh mcpgitctl; do
    fetch_snapshot_file \
      "$MCPGIT_INSTALL_CONTENT_BASE/deploy/$product_file" \
      "$target/$product_file"
    chmod 0755 "$target/$product_file"
  done
  python3 "$target/scripts/mcpgit-offline-release.py" verify \
    --manifest "$manifest" --asset-dir "$target"
}

platform_key() {
  case "$(uname -m)" in
    arm64|aarch64) echo linux-arm64 ;;
    x86_64|amd64) echo linux-amd64 ;;
    *) echo "unsupported MCPGit host architecture: $(uname -m)" >&2; return 1 ;;
  esac
}

program_target_compatible() {
  case "$(platform_key):$1" in
    linux-arm64:aarch64-unknown-linux-gnu|linux-arm64:aarch64-unknown-linux-musl) return 0 ;;
    linux-amd64:x86_64-unknown-linux-gnu|linux-amd64:x86_64-unknown-linux-musl) return 0 ;;
    *) return 1 ;;
  esac
}

expected_program_targets() {
  case "$(platform_key)" in
    linux-arm64) echo 'aarch64-unknown-linux-{gnu,musl}' ;;
    linux-amd64) echo 'x86_64-unknown-linux-{gnu,musl}' ;;
  esac
}

resolve_tag() {
  if [ -n "$MCPGIT_RELEASE_TAG" ]; then
    echo "$MCPGIT_RELEASE_TAG"
    return 0
  fi
  platform=$(platform_key)
  curl -fsSL --retry 5 --retry-delay 5 "$MCPGIT_CHANNEL_URL" \
    | python3 -c '
import json, sys
data = json.load(sys.stdin)
platform = sys.argv[1]
architectures = data.get("architectures")
if architectures is None:
    print(data["tag"])
else:
    entry = architectures.get(platform)
    if entry is None:
        raise SystemExit(f"offline channel has no release for {platform}")
    print(entry["tag"] if isinstance(entry, dict) else entry)
' "$platform"
}

usage() {
  cat <<'EOF'
Usage: novice-install.sh [options]

  --bundle DIR        install from an explicit offline bundle directory;
                      with --download-only, write the latest bundle there
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
bundle_explicit=false
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
    --bundle) bundle=$2; bundle_explicit=true; shift 2 ;;
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

# The default bundle directory is a verified download cache, not a version
# pin. Every normal online install must re-read offline-latest.json (or the
# explicit MCPGIT_RELEASE_TAG) so re-running the one-command installer really
# upgrades to the current product release. An explicitly supplied, already
# complete --bundle remains the offline/pinned install path. --download-only
# always refreshes the requested output directory from the selected release.
refresh_bundle=false
if [ "$bundle_explicit" = false ] \
  || [ "$download_only" = true ] \
  || [ -n "$MCPGIT_RELEASE_TAG" ]; then
  refresh_bundle=true
fi

if [ "$refresh_bundle" = true ] \
  || [ -z "$bundle" ] \
  || [ ! -f "$bundle/mcpgit-offline-release-v1.json" ] \
  || [ ! -f "$bundle/scripts/mcpgit-offline-release.py" ]; then
  tag=$(resolve_tag)
  [ -n "$tag" ] || { echo "cannot resolve offline release tag" >&2; exit 1; }
  fetch_bundle "$tag" "$bundle"
fi

if [ "$download_only" = true ]; then
  echo "PASS: bundle ready at $bundle (no Docker required for downloading)"
  echo "Copy the directory to the install machine, then run:"
  echo "  ./mcpgit-install.sh --bundle $bundle --instance $instance"
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
program_target=$(field layers.2.target)
program_target_compatible "$program_target" || {
  echo "offline bundle target $program_target is not compatible with $(platform_key) (expected $(expected_program_targets))" >&2
  exit 1
}
templates_archive="$(field layers.3.file 2>/dev/null || true)"
release_id=$(field release_id)
source_sha=$(field source_sha)
base_archive_sha=$(field layers.0.sha256)
tools_archive_sha=$(field layers.1.sha256)
program_archive_sha=$(field layers.2.sha256)
manifest_sha=$(sha256_file "$manifest")
assembly_sha=$(sha256_file "$dockerfile")

[ -n "$data_volume" ] || data_volume="${instance}_data"

case "$port" in
  ''|*[!0-9]*) echo "invalid MCPGit port: $port" >&2; exit 1 ;;
esac
if [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
  echo "invalid MCPGit port: $port" >&2
  exit 1
fi

current_container=false
current_program_version=
current_host_port=
current_was_running=false
current_image_id=
current_config_source=
current_netrc_source=
if docker container inspect "$instance" >/dev/null 2>&1; then
  current_container=true
  current_was_running=$(docker inspect "$instance" --format '{{.State.Running}}')
  current_image_id=$(docker inspect "$instance" --format '{{.Image}}')
  current_program_version=$(docker inspect "$instance" \
    --format '{{index .Config.Labels "com.yxsicd.mcpgit.program-version"}}' 2>/dev/null || true)
  current_data_volume=$(docker inspect "$instance" --format \
    '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}')
  if [ -z "$current_data_volume" ] || [ "$current_data_volume" != "$data_volume" ]; then
    echo "refusing to change data volume for existing instance $instance: current=$current_data_volume requested=$data_volume" >&2
    exit 1
  fi
  current_host_port=$(docker port "$instance" 8001/tcp 2>/dev/null \
    | sed -n '1s/.*://p' | tr -d '[:space:]')
  current_config_source=$(docker inspect "$instance" --format \
    '{{range .Mounts}}{{if eq .Destination "/config/mcpgit.toml"}}{{.Source}}{{end}}{{end}}')
  current_netrc_source=$(docker inspect "$instance" --format \
    '{{range .Mounts}}{{if eq .Destination "/root/.netrc"}}{{.Source}}{{end}}{{end}}')
fi

if [ "$current_host_port" != "$port" ]; then
  if ! python3 - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.bind(("127.0.0.1", port))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
  then
    echo "refusing MCPGit install because host port $port is already in use" >&2
    exit 1
  fi
fi

update_mode=false
created_data_volume=false
admin_credential_file=
admin_credential_created=false
if docker volume inspect "$data_volume" >/dev/null 2>&1; then
  update_mode=true
fi
if [ "$update_mode" = true ]; then
  echo "==> existing instance detected: update mode (data volume preserved)"
fi

echo "==> loading exact base image ($base_image_tag)"
actual_base_image_id=$(docker image inspect "$base_image_tag" \
  --format '{{.Id}}' 2>/dev/null || true)
if [ "$actual_base_image_id" != "$base_image_id" ]; then
  docker load < "$base_archive" >/dev/null
  actual_base_image_id=$(docker image inspect "$base_image_tag" \
    --format '{{.Id}}' 2>/dev/null || true)
fi
if [ "$actual_base_image_id" != "$base_image_id" ]; then
  echo "loaded base image identity does not match release manifest: expected=$base_image_id actual=$actual_base_image_id" >&2
  exit 1
fi
echo "    exact image id: $actual_base_image_id"

runtime_image="mcpgit-offline-runtime:$release_id"

work_dir="${MCPGIT_INSTANCE_CONFIG_DIR:-$HOME/.mcpgit}"
mkdir -p "$work_dir"
ctx=$(mktemp -d "$work_dir/work.XXXXXX")
trap 'rm -rf "$ctx"' EXIT INT TERM
echo "==> unpacking program and tools"
tar -xzf "$program_archive" -C "$ctx"
tar -xzf "$tools_archive" -C "$ctx"
cp "$dockerfile" "$ctx/Dockerfile.offline-runtime"

exec_sha() {
  sha256_file "$1"
}

expected_mcpgit_sha=$(exec_sha "$ctx/program/bin/mcpgit")
expected_mcpgitgw_sha=$(exec_sha "$ctx/program/bin/mcpgitgw")
expected_safe_recover_sha=
if [ -f "$ctx/program/bin/mcpgit-safe-recover" ]; then
  expected_safe_recover_sha=$(exec_sha "$ctx/program/bin/mcpgit-safe-recover")
fi
expected_node_sha=$(exec_sha "$ctx/tools/bin/node")
expected_bun_sha=$(exec_sha "$ctx/tools/bin/bun")
expected_credential_sha=$(exec_sha "$ctx/tools/bin/git-credential-netrc")

image_label() {
  docker image inspect "$runtime_image" --format "{{index .Config.Labels \"$1\"}}" 2>/dev/null || true
}

runtime_image_exact() {
  docker image inspect "$runtime_image" >/dev/null 2>&1 || return 1
  [ "$(image_label org.opencontainers.image.revision)" = "$source_sha" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.release-id)" = "$release_id" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.assembly-sha256)" = "$assembly_sha" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.base-image-id)" = "$base_image_id" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.tools-version)" = "$tools_version" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.program-version)" = "$program_version" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.manifest-sha256)" = "$manifest_sha" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.base-archive-sha256)" = "$base_archive_sha" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.tools-archive-sha256)" = "$tools_archive_sha" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.program-archive-sha256)" = "$program_archive_sha" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.exec.mcpgit-sha256)" = "$expected_mcpgit_sha" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.exec.mcpgitgw-sha256)" = "$expected_mcpgitgw_sha" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.exec.safe-recover-sha256)" = "$expected_safe_recover_sha" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.exec.node-sha256)" = "$expected_node_sha" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.exec.bun-sha256)" = "$expected_bun_sha" ] || return 1
  [ "$(image_label com.yxsicd.mcpgit.exec.credential-sha256)" = "$expected_credential_sha" ] || return 1

  probe=$(docker run --rm --entrypoint sh "$runtime_image" -c '
set -eu
printf "mcpgit=%s\n" "$(sha256sum /opt/mcpgit/program/bin/mcpgit | awk "{print \$1}")"
printf "mcpgitgw=%s\n" "$(sha256sum /opt/mcpgit/program/bin/mcpgitgw | awk "{print \$1}")"
if [ -f /opt/mcpgit/program/bin/mcpgit-safe-recover ]; then
  printf "safe=%s\n" "$(sha256sum /opt/mcpgit/program/bin/mcpgit-safe-recover | awk "{print \$1}")"
else
  printf "safe=\n"
fi
printf "node=%s\n" "$(sha256sum /opt/mcpgit/tools/bin/node | awk "{print \$1}")"
printf "bun=%s\n" "$(sha256sum /opt/mcpgit/tools/bin/bun | awk "{print \$1}")"
printf "credential=%s\n" "$(sha256sum /opt/mcpgit/tools/bin/git-credential-netrc | awk "{print \$1}")"
' 2>/dev/null) || return 1
  [ "$(printf '%s\n' "$probe" | sed -n 's/^mcpgit=//p')" = "$expected_mcpgit_sha" ] || return 1
  [ "$(printf '%s\n' "$probe" | sed -n 's/^mcpgitgw=//p')" = "$expected_mcpgitgw_sha" ] || return 1
  [ "$(printf '%s\n' "$probe" | sed -n 's/^safe=//p')" = "$expected_safe_recover_sha" ] || return 1
  [ "$(printf '%s\n' "$probe" | sed -n 's/^node=//p')" = "$expected_node_sha" ] || return 1
  [ "$(printf '%s\n' "$probe" | sed -n 's/^bun=//p')" = "$expected_bun_sha" ] || return 1
  [ "$(printf '%s\n' "$probe" | sed -n 's/^credential=//p')" = "$expected_credential_sha" ] || return 1
}

if [ "$rebuild" = true ] || ! runtime_image_exact; then
  echo "==> assembling offline runtime image ($runtime_image)"
  docker build \
    --file "$ctx/Dockerfile.offline-runtime" \
    --build-arg "MCPGIT_BASE_IMAGE=$base_image_tag" \
    --build-arg "MCPGIT_SOURCE_SHA=$source_sha" \
    --build-arg "MCPGIT_RELEASE_ID=$release_id" \
    --build-arg "MCPGIT_ASSEMBLY_SHA256=$assembly_sha" \
    --build-arg "MCPGIT_BASE_VERSION=$base_version" \
    --build-arg "MCPGIT_BASE_IMAGE_ID=$base_image_id" \
    --build-arg "MCPGIT_TOOLS_VERSION=$tools_version" \
    --build-arg "MCPGIT_PROGRAM_VERSION=$program_version" \
    --build-arg "MCPGIT_MANIFEST_SHA256=$manifest_sha" \
    --build-arg "MCPGIT_BASE_ARCHIVE_SHA256=$base_archive_sha" \
    --build-arg "MCPGIT_TOOLS_ARCHIVE_SHA256=$tools_archive_sha" \
    --build-arg "MCPGIT_PROGRAM_ARCHIVE_SHA256=$program_archive_sha" \
    --build-arg "MCPGIT_EXEC_MCPGIT_SHA256=$expected_mcpgit_sha" \
    --build-arg "MCPGIT_EXEC_MCPGITGW_SHA256=$expected_mcpgitgw_sha" \
    --build-arg "MCPGIT_EXEC_SAFE_RECOVER_SHA256=$expected_safe_recover_sha" \
    --build-arg "MCPGIT_EXEC_NODE_SHA256=$expected_node_sha" \
    --build-arg "MCPGIT_EXEC_BUN_SHA256=$expected_bun_sha" \
    --build-arg "MCPGIT_EXEC_CREDENTIAL_SHA256=$expected_credential_sha" \
    --tag "$runtime_image" \
    "$ctx"
  if ! runtime_image_exact; then
    echo "assembled runtime image failed exact release verification" >&2
    exit 1
  fi
else
  echo "==> exact offline runtime image already present: $runtime_image"
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
  created_data_volume=true
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
          mkdir -p "$dir"
          if [ -z "$(find "$dir" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
            printf "# %s\n" "$r" > "$dir/README.md"
          fi
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
config_created=false
if [ -f "$config" ] && ! grep -q "instance_id = \"$org_id\"" "$config" 2>/dev/null; then
  echo "refusing to replace existing instance config with a different organization identity: $config" >&2
  exit 1
fi
if [ ! -f "$config" ]; then
  {
    echo "[system_config]"
    echo "instance_id = \"$org_id\""
    echo "path = \"/data/repos/systemconfig\""
    echo "revision = \"refs/heads/main\""
  } > "$config"
  config_created=true
fi

desired_runtime_id=$(docker image inspect "$runtime_image" --format '{{.Id}}')
requested_config_source=$(python3 - "$config" <<'PY'
import os
import sys
print(os.path.abspath(sys.argv[1]))
PY
)
requested_netrc_source=
if [ -n "$netrc" ]; then
  requested_netrc_source=$(python3 - "$netrc" <<'PY'
import os
import sys
print(os.path.abspath(sys.argv[1]))
PY
)
fi

if [ "$current_container" = true ] \
  && [ "$current_was_running" = true ] \
  && [ "$current_image_id" = "$desired_runtime_id" ] \
  && [ "$current_host_port" = "$port" ] \
  && [ "$current_config_source" = "$requested_config_source" ] \
  && [ "$current_netrc_source" = "$requested_netrc_source" ] \
  && [ "$(curl -s -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:$port/healthz" 2>/dev/null || true)" = "204" ]; then
  docker update --restart unless-stopped "$instance" >/dev/null
  echo
  echo "PASS: instance $instance already matches the selected release; no restart required"
  echo "  organization id (immutable identity): $org_id"
  echo "  endpoint:  http://127.0.0.1:$port"
  echo "  data volume: $data_volume"
  exit 0
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

echo "==> initializing random systemadmin credential"
credential_dir="$MCPGIT_CREDENTIAL_DIR"
mkdir -p "$credential_dir"
chmod 0700 "$credential_dir"
admin_credential_file="$credential_dir/${instance}-systemadmin.env"
if [ -L "$admin_credential_file" ]; then
  echo "refusing symlink credential file: $admin_credential_file" >&2
  exit 1
fi
initial_admin_password=$(python3 -c 'import secrets; print("Aa9!" + secrets.token_urlsafe(24))')
credential_tmp="${admin_credential_file}.tmp.$$"
bootstrap_password_env="${credential_dir}/.${instance}-bootstrap-password.$$"
umask 077
printf 'MCPGIT_BASIC_USERNAME=systemadmin\nMCPGIT_BASIC_VERIFY=%s\n' \
  "$initial_admin_password" > "$credential_tmp"
chmod 0600 "$credential_tmp"
mv "$credential_tmp" "$admin_credential_file"
admin_credential_created=true
printf 'MCPGIT_SYSTEMADMIN_PASSWORD=%s\n' "$initial_admin_password" > "$bootstrap_password_env"
chmod 0600 "$bootstrap_password_env"
initial_admin_password=

auth_bootstrap_container="${instance}-auth-bootstrap"
docker rm -f "$auth_bootstrap_container" >/dev/null 2>&1 || true
if ! docker run -d \
  --name "$auth_bootstrap_container" \
  --restart no \
  --env-file "$bootstrap_password_env" \
  -v "$data_volume":/data \
  -v "$config":/config/mcpgit.toml:ro \
  ${netrc:+-v "$netrc":/root/.netrc:ro} \
  -e MCPGIT_BOOTSTRAP_REMOTE_REPOS= \
  -e MCPGIT_BOOTSTRAP_REPO_SOURCES=none \
  -e MCPGIT_ALLOWED_HOSTS=localhost,127.0.0.1,::1 \
  -e MCPGIT_PUBLIC_BASE_URL="http://127.0.0.1:$port" \
  "$runtime_image" >/dev/null; then
  rm -f "$bootstrap_password_env"
  docker rm -f "$auth_bootstrap_container" >/dev/null 2>&1 || true
  [ "$admin_credential_created" = true ] && rm -f "$admin_credential_file"
  [ "$created_data_volume" = true ] && docker volume rm "$data_volume" >/dev/null 2>&1 || true
  [ "$config_created" = true ] && rm -f "$config"
  echo "systemadmin credential bootstrap container failed to start" >&2
  exit 1
fi
rm -f "$bootstrap_password_env"

bootstrap_deadline=$(( $(date +%s) + 60 ))
bootstrap_ready=false
while [ "$(date +%s)" -lt "$bootstrap_deadline" ]; do
  if docker exec "$auth_bootstrap_container" \
    curl -fsS -o /dev/null http://127.0.0.1:8001/healthz >/dev/null 2>&1; then
    bootstrap_ready=true
    break
  fi
  if [ "$(docker inspect "$auth_bootstrap_container" --format '{{.State.Running}}' 2>/dev/null || true)" != "true" ]; then
    break
  fi
  sleep 1
done
if [ "$bootstrap_ready" != true ]; then
  docker logs "$auth_bootstrap_container" 2>&1 | tail -40 >&2 || true
  docker rm -f "$auth_bootstrap_container" >/dev/null 2>&1 || true
  [ "$admin_credential_created" = true ] && rm -f "$admin_credential_file"
  [ "$created_data_volume" = true ] && docker volume rm "$data_volume" >/dev/null 2>&1 || true
  [ "$config_created" = true ] && rm -f "$config"
  echo "systemadmin credential bootstrap did not become healthy" >&2
  exit 1
fi
if ! docker exec "$auth_bootstrap_container" sh -lc '
  code=$(curl -sS -o /dev/null -w "%{http_code}" \
    -u "systemadmin:$MCPGIT_SYSTEMADMIN_PASSWORD" \
    http://127.0.0.1:8001/__mcpgit/auth/session)
  test "$code" = 200
'; then
  docker rm -f "$auth_bootstrap_container" >/dev/null 2>&1 || true
  [ "$admin_credential_created" = true ] && rm -f "$admin_credential_file"
  [ "$created_data_volume" = true ] && docker volume rm "$data_volume" >/dev/null 2>&1 || true
  [ "$config_created" = true ] && rm -f "$config"
  echo "generated systemadmin credential failed authentication probe" >&2
  exit 1
fi
docker rm -f "$auth_bootstrap_container" >/dev/null
fi

rollback_container="${instance}-rollback"
previous_preserved=false
previous_host_port="$current_host_port"

restore_previous_instance() {
  docker rm -f "$instance" >/dev/null 2>&1 || true
  if [ "$previous_preserved" = true ] \
    && docker container inspect "$rollback_container" >/dev/null 2>&1; then
    if ! docker rename "$rollback_container" "$instance" >/dev/null; then
      echo "automatic rollback could not restore previous container name: $rollback_container" >&2
      return 1
    fi
    if [ "$current_was_running" = true ]; then
      if ! docker start "$instance" >/dev/null; then
        echo "automatic rollback could not restart previous container: $instance" >&2
        return 1
      fi
      if [ -n "$previous_host_port" ]; then
        rollback_deadline=$(( $(date +%s) + 60 ))
        while [ "$(curl -s -o /dev/null -w '%{http_code}' \
          "http://127.0.0.1:$previous_host_port/healthz" 2>/dev/null || true)" != "204" ]; do
          if [ "$(date +%s)" -ge "$rollback_deadline" ]; then
            echo "automatic rollback restarted the previous container but health did not recover" >&2
            return 1
          fi
          sleep 1
        done
      fi
    fi
    echo "==> restored previous instance $instance after candidate failure" >&2
    return 0
  fi
  if [ "$created_data_volume" = true ]; then
    docker volume rm "$data_volume" >/dev/null 2>&1 || true
  fi
  if [ "$config_created" = true ]; then
    rm -f "$config"
  fi
  if [ "$admin_credential_created" = true ]; then
    rm -f "$admin_credential_file"
  fi
  return 0
}

echo "==> starting candidate instance $instance (port $port)"
if [ "$current_container" = true ]; then
  docker rm -f "$rollback_container" >/dev/null 2>&1 || true
  if [ "$current_was_running" = true ]; then
    docker stop "$instance" >/dev/null
  fi
  if ! docker rename "$instance" "$rollback_container" >/dev/null; then
    [ "$current_was_running" = true ] && docker start "$instance" >/dev/null 2>&1 || true
    echo "could not preserve current container for rollback" >&2
    exit 1
  fi
  previous_preserved=true
fi

if ! docker run -d \
  --name "$instance" \
  --restart no \
  --label "org.opencontainers.image.version=git-$source_sha" \
  --label "org.opencontainers.image.revision=$source_sha" \
  --label "com.yxsicd.mcpgit.distribution=github-offline-v2" \
  --label "com.yxsicd.mcpgit.release-id=$release_id" \
  --label "com.yxsicd.mcpgit.program-version=$program_version" \
  --label "com.yxsicd.mcpgit.manifest-sha256=$manifest_sha" \
  --label "com.yxsicd.mcpgit.instance-id=$org_id" \
  --label "com.yxsicd.mcpgit.instance-name=$instance" \
  --label "com.yxsicd.mcpgit.data-volume=$data_volume" \
  -v "$data_volume":/data \
  -v "$config":/config/mcpgit.toml:ro \
  ${netrc:+-v "$netrc":/root/.netrc:ro} \
  -e MCPGIT_BOOTSTRAP_REMOTE_REPOS= \
  -e MCPGIT_BOOTSTRAP_REPO_SOURCES=none \
  -e MCPGIT_ALLOWED_HOSTS=localhost,127.0.0.1,::1 \
  -e MCPGIT_PUBLIC_BASE_URL="http://127.0.0.1:$port" \
  -p "$port":8001 \
  "$runtime_image" >/dev/null; then
  echo "candidate container failed to start; restoring previous instance" >&2
  restore_previous_instance || true
  exit 1
fi

echo "==> waiting for health"
deadline=$(( $(date +%s) + 120 ))
candidate_healthy=false
while [ "$(date +%s)" -lt "$deadline" ]; do
  if [ "$(curl -s -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:$port/healthz" 2>/dev/null || true)" = "204" ]; then
    candidate_healthy=true
    break
  fi
  if [ "$(docker inspect "$instance" --format '{{.State.Running}}' 2>/dev/null || true)" != "true" ]; then
    break
  fi
  sleep 2
done

if [ "$candidate_healthy" != true ]; then
  echo "candidate instance did not become healthy; restoring previous instance" >&2
  docker logs "$instance" 2>&1 | tail -40 >&2 || true
  restore_previous_instance || true
  exit 1
fi

if [ "$update_mode" = false ]; then
  if ! (
    set -a
    . "$admin_credential_file"
    set +a
    code=$(curl -sS -o /dev/null -w '%{http_code}' \
      -u "$MCPGIT_BASIC_USERNAME:$MCPGIT_BASIC_VERIFY" \
      "http://127.0.0.1:$port/__mcpgit/auth/session")
    test "$code" = 200
  ); then
    echo "final systemadmin credential authentication probe failed; removing candidate" >&2
    restore_previous_instance || true
    exit 1
  fi
fi

docker update --restart unless-stopped "$instance" >/dev/null

echo
if [ "$update_mode" = true ]; then
  echo "PASS: updated instance $instance (program ${current_program_version:-unknown} -> $program_version)"
else
  echo "PASS: offline instance $instance is healthy"
fi
echo "  skills table: run Service table.initialize (repo=rootskills,"
echo "    root=.agents/skills) once; see rootskills/docs/SKILLS_TABLE.md"
echo "  organization id (immutable identity): $org_id"
echo "  instance name (renameable label): $instance"
echo "  endpoint:  http://127.0.0.1:$port"
echo "  data volume: $data_volume"
if [ "$previous_preserved" = true ]; then
  echo "  rollback container: $rollback_container (stopped)"
fi
if [ "$update_mode" = false ]; then
  echo "  systemadmin credential file (0600): $admin_credential_file"
  echo "  load it with: . \"$admin_credential_file\""
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
