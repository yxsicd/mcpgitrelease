#!/bin/sh
set -eu

REPOSITORY="${MCPGIT_INSTALL_REPOSITORY:-yxsicd/mcpgitrelease}"
REVISION="${MCPGIT_INSTALL_REVISION:-}"

command -v curl >/dev/null 2>&1 || { echo "MCPGit installer requires curl" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "MCPGit installer requires python3" >&2; exit 1; }

if [ -z "${MCPGIT_INSTALL_BASE_URL:-}" ]; then
  if [ -z "$REVISION" ]; then
    REVISION=$(curl -fsSL --retry 5 --retry-delay 5 --retry-all-errors \
      -H 'Accept: application/vnd.github+json' \
      "https://api.github.com/repos/$REPOSITORY/commits/main" \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])')
  fi
  case "$REVISION" in
    *[!0-9a-f]*|'') echo "invalid MCPGit install revision: $REVISION" >&2; exit 1 ;;
  esac
  [ "${#REVISION}" -eq 40 ] || { echo "MCPGit install revision must be a full Git SHA" >&2; exit 1; }
  CONTENT_BASE="https://raw.githubusercontent.com/$REPOSITORY/$REVISION"
  BASE_URL="$CONTENT_BASE/deploy"
  export MCPGIT_INSTALL_REVISION="$REVISION"
  export MCPGIT_INSTALL_BASE_URL="$BASE_URL"
  export MCPGIT_INSTALL_CONTENT_BASE="$CONTENT_BASE"
  if [ -z "${MCPGIT_CHANNEL_URL:-}" ]; then
    export MCPGIT_CHANNEL_URL="$CONTENT_BASE/offline-latest.json"
  fi
  echo "==> MCPGit install snapshot $REVISION"
else
  BASE_URL="${MCPGIT_INSTALL_BASE_URL%/}"
fi

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/mcpgit-install.XXXXXX")
cleanup() {
  rm -rf "$TMP_DIR"
  return 0
}
trap cleanup EXIT INT TERM
curl -fsSL --retry 5 --retry-delay 5 --retry-all-errors \
  "$BASE_URL/mcpgit-install.sh" -o "$TMP_DIR/mcpgit-install.sh"
chmod 0755 "$TMP_DIR/mcpgit-install.sh"
set +e
"$TMP_DIR/mcpgit-install.sh" "$@"
status=$?
set -e
exit "$status"
