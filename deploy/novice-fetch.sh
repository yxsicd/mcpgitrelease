#!/bin/sh
set -eu

# Novice fetch: download one immutable mcpgit offline Release bundle on the
# online machine (A). Nothing is built or installed here; the resulting
# bundle directory is copied to the offline machine (B) and installed with
# novice-install.sh. The bundle carries its own manifest parser, the built-in
# auth bootstrap script, and the offline runtime Dockerfile, so machine B
# never needs network access or the private source repository.

usage() {
  cat <<'EOF'
Usage: novice-fetch.sh <release-tag> <bundle-dir> [--source DIR]

  <release-tag>   GitHub Release tag, e.g. mcpgit-git-<full-source-sha>
  <bundle-dir>    directory that receives the offline bundle (created if absent)
  --source DIR    optional path to a local MCPGit source checkout used for the
                  two helper scripts and the runtime Dockerfile. Without it the
                  scripts are fetched from the private source repo raw URL
                  (requires GitHub credentials in ~/.netrc).
EOF
  exit 1
}

release_tag=${1:-}
bundle_dir=${2:-}
source_dir=
while [ $# -gt 0 ]; do
  case "$1" in
    --source) source_dir=$2; shift 2 ;;
    *) shift ;;
  esac
done
[ -n "$release_tag" ] && [ -n "$bundle_dir" ] || usage

base_url="https://github.com/yxsicd/mcpgitrelease/releases/download/$release_tag"
mkdir -p "$bundle_dir"

echo "==> fetching manifest"
curl -fsSL --retry 5 --retry-delay 5 --retry-all-errors \
  "$base_url/mcpgit-offline-release-v1.json" \
  -o "$bundle_dir/mcpgit-offline-release-v1.json"

manifest="$bundle_dir/mcpgit-offline-release-v1.json"
parser="scripts/mcpgit-offline-release.py"
bootstrap="scripts/bootstrap-builtin-auth.py"
dockerfile="Dockerfile.offline-runtime"

fetch_source_file() {
  target=$1
  relative=$2
  if [ -n "$source_dir" ] && [ -f "$source_dir/$relative" ]; then
    cp "$source_dir/$relative" "$bundle_dir/$target"
    return 0
  fi
  if curl -fsSLn --retry 5 --retry-delay 5 --retry-all-errors \
    "https://raw.githubusercontent.com/yxsicd/MCPGit/main/$relative" \
    -o "$bundle_dir/$target" 2>/dev/null; then
    return 0
  fi
  echo "cannot obtain $relative: pass --source DIR with an MCPGit checkout" >&2
  exit 1
}

mkdir -p "$bundle_dir/scripts"
fetch_source_file "scripts/mcpgit-offline-release.py" "$parser"
fetch_source_file "scripts/bootstrap-builtin-auth.py" "$bootstrap"
fetch_source_file "Dockerfile.offline-runtime" "$dockerfile"
fetch_source_file "novice-install.sh" "deploy/novice-install.sh"
fetch_source_file "mcpgit-install.sh" "deploy/mcpgit-install.sh"
fetch_source_file "mcpgitctl" "deploy/mcpgitctl"
chmod 0755 \
  "$bundle_dir/novice-install.sh" \
  "$bundle_dir/mcpgit-install.sh" \
  "$bundle_dir/mcpgitctl"

echo "==> downloading release assets"
python3 "$bundle_dir/$parser" verify \
  --manifest "$manifest" \
  --asset-dir "$bundle_dir" >/dev/null 2>&1 || true

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
  if [ -f "$bundle_dir/$file" ]; then
    actual=$(shasum -a 256 "$bundle_dir/$file" | awk '{print $1}')
    if [ "$actual" = "$expected" ]; then
      echo "    unchanged: $file (cached)"
      continue
    fi
    echo "    changed: $file (new layer hash)"
  fi
  echo "    download: $file"
  curl -fsSL --retry 5 --retry-delay 5 --retry-all-errors \
    "$base_url/$file" -o "$bundle_dir/$file"
done < "$layer_list"

echo "==> verifying bundle integrity"
python3 "$bundle_dir/$parser" verify \
  --manifest "$manifest" \
  --asset-dir "$bundle_dir"

source_sha=$(python3 "$bundle_dir/$parser" field --manifest "$manifest" --path source_sha)
cat > "$bundle_dir/FETCHED.md" <<EOF
# Offline MCPGit bundle (novice fetch)

- Release tag: $release_tag
- Source revision: $source_sha
- Fetched at: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- Helper script hashes:
  - scripts/mcpgit-offline-release.py $(shasum -a 256 "$bundle_dir/scripts/mcpgit-offline-release.py" | awk '{print $1}')
  - scripts/bootstrap-builtin-auth.py $(shasum -a 256 "$bundle_dir/scripts/bootstrap-builtin-auth.py" | awk '{print $1}')

Copy this whole directory to the offline machine and run the product installer:

    ./mcpgit-install.sh --bundle <this-dir> --instance <name>
EOF

echo
echo "PASS: bundle ready at $bundle_dir ($release_tag, source $source_sha)"
echo "Copy the whole directory to the offline machine, then run"
echo "  ./mcpgit-install.sh --bundle $bundle_dir --instance <name>"
