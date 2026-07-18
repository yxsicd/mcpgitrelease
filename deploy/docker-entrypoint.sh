#!/bin/sh
set -eu
PATH=/opt/mcpgit/runtime:$PATH
export PATH

configure_repo() {
  repo_dir=$1
  git -C "$repo_dir" config user.name "mcpgit agent"
  git -C "$repo_dir" config user.email "mcpgit-agent@example.invalid"
  if command -v git-credential-netrc >/dev/null 2>&1; then
    git -C "$repo_dir" config credential.helper netrc
  fi
}

configure_existing_repos() {
  [ -d /data/repos ] || return 0
  for repo_dir in /data/repos/*; do
    [ -d "$repo_dir/.git" ] || continue
    configure_repo "$repo_dir"
  done
}

bootstrap_remote_repos() {
  repos=${MCPGIT_BOOTSTRAP_REMOTE_REPOS:-}
  [ -n "$repos" ] || return 0
  base=${MCPGIT_REMOTE_BACKEND_WEB_BASE_URL:-}
  org=${MCPGIT_REMOTE_ORG:-}
  if [ -z "$base" ] || [ -z "$org" ]; then
    echo "bootstrap repositories require remote base URL and organization" >&2
    exit 1
  fi
  base=${base%/}
  mkdir -p /data/repos
  old_ifs=$IFS
  IFS=,
  for repo in $repos; do
    IFS=$old_ifs
    repo=$(printf '%s' "$repo" | tr -d '[:space:]')
    case "$repo" in
      "" | *[!abcdefghijklmnopqrstuvwxyz0123456789]*)
        echo "invalid bootstrap repository name: $repo" >&2
        exit 1
        ;;
    esac
    repo_dir=/data/repos/$repo
    if [ -d "$repo_dir/.git" ]; then
      configure_repo "$repo_dir"
    else
      if [ -e "$repo_dir" ] && [ "$(find "$repo_dir" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')" != 0 ]; then
        echo "refusing to clone over non-empty directory: $repo_dir" >&2
        exit 1
      fi
      rm -rf "$repo_dir"
      git clone "$base/$org/$repo.git" "$repo_dir"
      configure_repo "$repo_dir"
    fi
    IFS=,
  done
  IFS=$old_ifs
}

configure_existing_repos
bootstrap_remote_repos
exec /opt/mcpgit/current/mcpgit "$@"
