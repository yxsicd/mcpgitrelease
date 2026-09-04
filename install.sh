#!/bin/sh
set -eu

BASE_URL="${MCPGIT_INSTALL_BASE_URL:-https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/deploy}"
TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/mcpgit-install.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT INT TERM
command -v curl >/dev/null 2>&1 || { echo "MCPGit installer requires curl" >&2; exit 1; }
curl -fsSL --retry 5 --retry-delay 5 --retry-all-errors \
  "$BASE_URL/mcpgit-install.sh" -o "$TMP_DIR/mcpgit-install.sh"
chmod 0755 "$TMP_DIR/mcpgit-install.sh"
exec "$TMP_DIR/mcpgit-install.sh" "$@"
