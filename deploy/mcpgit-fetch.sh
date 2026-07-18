#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "mcpgit-fetch: $*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: mcpgit-fetch.sh [dev|main|prod] [TARGET_DIR]

Downloads the correct Linux architecture assets and deployment kit from the
selected public MCPGit channel, then verifies every SHA-256 checksum.
EOF
}

channel=${1:-prod}
target=${2:-./mcpgit-bundle}
[[ "$channel" == dev || "$channel" == main || "$channel" == prod ]] || {
  usage >&2
  die "channel must be dev, main, or prod"
}

case "$(uname -m)" in
  x86_64 | amd64) arch=amd64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) die "unsupported host architecture: $(uname -m)" ;;
esac

for command_name in curl tar; do
  command -v "$command_name" >/dev/null 2>&1 || die "required command is missing: $command_name"
done

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    die "sha256sum or shasum is required"
  fi
}

target=$(mkdir -p "$target" && cd "$target" && pwd -P)
manifest=$target/install-linux-$arch.env
manifest_part=$target/.install-linux-$arch.env.part.$$
trap 'rm -f -- "$manifest_part"' EXIT
manifest_url=https://raw.githubusercontent.com/yxsicd/mcpgitrelease/$channel/install-linux-$arch.env
curl --fail --silent --show-error --location --retry 3 --output "$manifest_part" "$manifest_url"

allowed='|MCPGIT_INSTALL_SCHEMA|MCPGIT_CHANNEL|MCPGIT_ARCH|MCPGIT_BINARY_FILE|MCPGIT_BINARY_URL|MCPGIT_BINARY_SHA256|MCPGIT_DEVBASE_FILE|MCPGIT_DEVBASE_URL|MCPGIT_DEVBASE_SHA256|MCPGIT_DEPLOY_FILE|MCPGIT_DEPLOY_URL|MCPGIT_DEPLOY_SHA256|'
seen='|'
while IFS= read -r line || [[ -n "$line" ]]; do
  line=${line%$'\r'}
  [[ "$line" =~ ^([A-Z][A-Z0-9_]*)=([A-Za-z0-9._:/?&=%+-]+)$ ]] || die "invalid installer manifest line"
  key=${BASH_REMATCH[1]}
  value=${BASH_REMATCH[2]}
  if [[ "$allowed" == *"|$key|"* ]]; then
    [[ "$seen" != *"|$key|"* ]] || die "duplicate installer key: $key"
    printf -v "$key" '%s' "$value"
    seen=$seen$key'|'
  fi
done < "$manifest_part"

for key in MCPGIT_INSTALL_SCHEMA MCPGIT_CHANNEL MCPGIT_ARCH MCPGIT_BINARY_FILE MCPGIT_BINARY_URL MCPGIT_BINARY_SHA256 MCPGIT_DEVBASE_FILE MCPGIT_DEVBASE_URL MCPGIT_DEVBASE_SHA256 MCPGIT_DEPLOY_FILE MCPGIT_DEPLOY_URL MCPGIT_DEPLOY_SHA256; do
  [[ "$seen" == *"|$key|"* ]] || die "installer manifest is missing $key"
done
[[ "$MCPGIT_INSTALL_SCHEMA" == mcpgitrelease/install/v1 ]] || die "unsupported installer schema"
[[ "$MCPGIT_CHANNEL" == "$channel" ]] || die "downloaded manifest channel mismatch"
[[ "$MCPGIT_ARCH" == "$arch" ]] || die "downloaded manifest architecture mismatch"
[[ "$MCPGIT_BINARY_FILE" == mcpgit-linux-$arch.tar.gz ]] || die "unexpected binary filename"
[[ "$MCPGIT_DEVBASE_FILE" == mcpgit-devbase-linux-$arch.docker.tar.zst ]] || die "unexpected devbase filename"
[[ "$MCPGIT_DEPLOY_FILE" == mcpgit-deploy.tar.gz ]] || die "unexpected deployment filename"

download() {
  local file=$1 url=$2 checksum=$3 part
  [[ "$url" == https://github.com/yxsicd/mcpgitrelease/releases/download/*"/$file" ]] || die "untrusted asset URL"
  [[ "$checksum" =~ ^[0-9a-f]{64}$ ]] || die "invalid checksum for $file"
  part=$target/.$file.part.$$
  curl --fail --show-error --location --retry 3 --output "$part" "$url"
  if [[ "$(sha256_file "$part")" != "$checksum" ]]; then
    rm -f -- "$part"
    die "checksum mismatch for $file"
  fi
  mv -f "$part" "$target/$file"
}

download "$MCPGIT_BINARY_FILE" "$MCPGIT_BINARY_URL" "$MCPGIT_BINARY_SHA256"
download "$MCPGIT_DEVBASE_FILE" "$MCPGIT_DEVBASE_URL" "$MCPGIT_DEVBASE_SHA256"
download "$MCPGIT_DEPLOY_FILE" "$MCPGIT_DEPLOY_URL" "$MCPGIT_DEPLOY_SHA256"

mkdir -p "$target/deploy"
while IFS= read -r entry; do
  [[ -n "$entry" && "$entry" != /* && "$entry" != *".."* ]] || die "unsafe deployment archive path"
done < <(tar -tzf "$target/$MCPGIT_DEPLOY_FILE")
tar -xzf "$target/$MCPGIT_DEPLOY_FILE" -C "$target/deploy"
for required in mcpgit-deploy.sh compose.yaml docker-entrypoint.sh git-credential-netrc mcpgit.toml mcpgit-runtime.env.example; do
  [[ -r "$target/deploy/$required" ]] || die "deployment archive is missing $required"
done
chmod 0755 "$target/deploy/mcpgit-deploy.sh" "$target/deploy/mcpgit-fetch.sh" "$target/deploy/docker-entrypoint.sh" "$target/deploy/git-credential-netrc"
mv -f "$manifest_part" "$manifest"
trap - EXIT

echo "mcpgit-fetch: verified $channel/$arch bundle at $target"
echo "mcpgit-fetch: copy $target/deploy/mcpgit-runtime.env.example to $target/mcpgit-runtime.env, configure the remote, then run:"
echo "  $target/deploy/mcpgit-deploy.sh --bundle $target --instance mcpgit --runtime-env $target/mcpgit-runtime.env --netrc /path/to/netrc"
