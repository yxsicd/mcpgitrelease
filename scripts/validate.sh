#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$repo_root"

bash -n deploy/mcpgit-deploy.sh
bash -n deploy/mcpgit-preflight.sh
sh -n deploy/mcpgit-install.sh
sh -n deploy/mcpgitctl
sh -n deploy/novice-install.sh
sh -n deploy/novice-fetch.sh
python3 scripts/client_sdk_tool.py validate client-sdk.json
sh -n deploy/docker-entrypoint.sh
sh -n deploy/git-credential-netrc
python3 -c 'compile(open("scripts/mcpgit-offline-release.py", encoding="utf-8").read(), "scripts/mcpgit-offline-release.py", "exec")'
python3 -c 'compile(open("scripts/bootstrap-builtin-auth.py", encoding="utf-8").read(), "scripts/bootstrap-builtin-auth.py", "exec")'
python3 -m unittest discover -s tests -v
git diff --check

if command -v ruby >/dev/null 2>&1; then
  ruby -e 'require "yaml"; Dir[".github/workflows/*.yml", "deploy/*.yaml"].each { |path| YAML.safe_load(File.read(path), aliases: true) }'
fi
