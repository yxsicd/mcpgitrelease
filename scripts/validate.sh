#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$repo_root"

bash -n deploy/mcpgit-deploy.sh
sh -n deploy/docker-entrypoint.sh
sh -n deploy/git-credential-netrc
python3 -m unittest discover -s tests -v
git diff --check

if command -v ruby >/dev/null 2>&1; then
  ruby -e 'require "yaml"; Dir[".github/workflows/*.yml", "deploy/*.yaml"].each { |path| YAML.safe_load(File.read(path), aliases: true) }'
fi
