#!/bin/sh
set -eu

# MCPGit user-facing installer. It is a small product facade over
# novice-install.sh. When invoked through `curl | sh`, backend files are fetched
# into a temporary directory; a source checkout reuses its local copies.

PUBLIC_DEPLOY_BASE="${MCPGIT_INSTALL_BASE_URL:-https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/deploy}"
BIN_DIR="${MCPGIT_BIN_DIR:-$HOME/.local/bin}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd || pwd)
TEMP_DIR=

usage() {
  cat <<'EOF'
Usage: mcpgit-install.sh [common options]

  --instance NAME     instance name (default: mcpgit)
  --port PORT         local service port (default: 8001)
  --bundle DIR        install from an already downloaded offline bundle
  --data-volume VOL   use an explicit persistent Docker volume
  --netrc FILE        optional Git remote credentials
  --zone ZONE         authentication zone (default: blue)
  --download-only     fetch/verify the release bundle without installing
  --rebuild           force runtime image reconstruction

Advanced MCPGIT_* environment settings are passed through to the backend.
EOF
}

case "${1:-}" in
  help|--help|-h) usage; exit 0 ;;
esac

instance=${MCPGIT_INSTANCE:-mcpgit}
port=${MCPGIT_PORT:-8001}
download_only=false
expect=
for arg in "$@"; do
  if [ "$expect" = instance ]; then instance=$arg; expect=; continue; fi
  if [ "$expect" = port ]; then port=$arg; expect=; continue; fi
  case "$arg" in
    --instance) expect=instance ;;
    --port) expect=port ;;
    --download-only) download_only=true ;;
  esac
done

cleanup() {
  if [ -n "$TEMP_DIR" ]; then
    rm -rf "$TEMP_DIR"
  fi
  return 0
}
trap cleanup EXIT INT TERM

fetch_file() {
  name=$1
  target=$2
  command -v curl >/dev/null 2>&1 || { echo "curl is required to bootstrap MCPGit" >&2; exit 1; }
  curl -fsSL --retry 5 --retry-delay 5 --retry-all-errors "$PUBLIC_DEPLOY_BASE/$name" -o "$target"
}

backend="$SCRIPT_DIR/novice-install.sh"
ctl_source="$SCRIPT_DIR/mcpgitctl"
if [ ! -f "$backend" ] || [ ! -f "$ctl_source" ]; then
  TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/mcpgit-product-install.XXXXXX")
  backend="$TEMP_DIR/novice-install.sh"
  ctl_source="$TEMP_DIR/mcpgitctl"
  echo "==> preparing MCPGit installer"
  fetch_file novice-install.sh "$backend"
  fetch_file mcpgitctl "$ctl_source"
fi
chmod 0755 "$backend" "$ctl_source"

echo "MCPGit Installer"
echo "================"
echo "Instance: $instance"
echo "Port: $port"
echo

MCPGIT_INSTANCE="$instance" MCPGIT_PORT="$port" sh "$backend" "$@"

if [ "$download_only" = true ]; then
  exit 0
fi

mkdir -p "$BIN_DIR"
cp "$ctl_source" "$BIN_DIR/mcpgitctl"
chmod 0755 "$BIN_DIR/mcpgitctl"

echo
echo "MCPGit product tools"
echo "  mcpgitctl: $BIN_DIR/mcpgitctl"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "  add $BIN_DIR to PATH to run mcpgitctl directly" ;;
esac
echo "  status: $BIN_DIR/mcpgitctl --instance $instance --url http://127.0.0.1:$port status"
