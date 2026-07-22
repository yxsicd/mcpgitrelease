#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "mcpgit-toolchain-init: $*" >&2
  exit 1
}

volume=mcpgit-toolchain-node22.23.1-bun1.3.14
if [[ ${1:-} == --volume ]]; then
  [[ $# -eq 2 ]] || die "usage: mcpgit-toolchain-init.sh [--volume NAME]"
  volume=$2
elif [[ $# -ne 0 ]]; then
  die "usage: mcpgit-toolchain-init.sh [--volume NAME]"
fi
[[ "$volume" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || die "invalid volume name"

command -v docker >/dev/null 2>&1 || die "docker is required"
case "$(uname -m)" in
  x86_64 | amd64)
    arch=amd64
    node_digest=sha256:8607a9064d4a571140998ae9e52a3b3fcf9cff361d04642d5971e6cd76d39e27
    bun_digest=sha256:50317d83cd5a5ae1d8b35b3379c69f57ce1a0dbf4def91f0965653d767851834
    ;;
  aarch64 | arm64)
    arch=arm64
    node_digest=sha256:ef03a3d0e663b3c9d38c95be3fd31a100514d41df2599562b68a58a57f979adf
    bun_digest=sha256:d8a4c24744b290bf789d58966a6f2521fc4d8bec36ec02cead6c541147b7d550
    ;;
  *) die "unsupported host architecture: $(uname -m)" ;;
esac

node_image="node:22.23.1-bookworm-slim@$node_digest"
bun_image="oven/bun:1.3.14@$bun_digest"

verify_volume() {
  docker run --rm --pull never \
    -v "$volume:/opt/mcpgit-toolchain:ro" \
    --entrypoint sh "$node_image" -ceu '
      test "$(/opt/mcpgit-toolchain/node/bin/node --version)" = v22.23.1
      test "$(/opt/mcpgit-toolchain/bun/bin/bun --version)" = 1.3.14
      ! touch /opt/mcpgit-toolchain/.write-probe 2>/dev/null
    '
}

pull_public_image() {
  local image=$1
  local docker_host public_config rc
  docker_host="${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}"
  public_config="$(mktemp -d "${TMPDIR:-/tmp}/mcpgit-toolchain-docker.XXXXXX")"
  printf '{}\n' > "$public_config/config.json"
  set +e
  DOCKER_HOST="$docker_host" docker --config "$public_config" pull "$image" >/dev/null
  rc=$?
  set -e
  rm -rf -- "$public_config"
  (( rc == 0 )) || die "failed to pull public image: $image"
}

pull_public_image "$node_image"
pull_public_image "$bun_image"

if docker volume inspect "$volume" >/dev/null 2>&1; then
  [[ "$(docker volume inspect --format '{{index .Labels "com.yxsicd.mcpgit.toolchain"}}' "$volume")" == node22.23.1-bun1.3.14 ]] \
    || die "existing volume has an unexpected toolchain label: $volume"
  [[ "$(docker volume inspect --format '{{index .Labels "com.yxsicd.mcpgit.arch"}}' "$volume")" == "$arch" ]] \
    || die "existing volume has an unexpected architecture: $volume"
  verify_volume
  echo "mcpgit-toolchain-init: verified existing $volume ($arch)"
  exit 0
fi

created=false
cleanup() {
  if [[ "$created" == true ]]; then
    docker volume rm "$volume" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

docker volume create \
  --label com.yxsicd.mcpgit.toolchain=node22.23.1-bun1.3.14 \
  --label "com.yxsicd.mcpgit.arch=$arch" \
  --label "com.yxsicd.mcpgit.node-digest=$node_digest" \
  --label "com.yxsicd.mcpgit.bun-digest=$bun_digest" \
  "$volume" >/dev/null
created=true

docker run --rm --pull never \
  -v "$volume:/toolchain" \
  --entrypoint sh "$node_image" -ceu '
    mkdir -p /toolchain/node
    cp -a /usr/local/bin /usr/local/include /usr/local/lib /usr/local/share /toolchain/node/
  '

docker run --rm --pull never \
  -v "$volume:/toolchain" \
  --entrypoint sh "$bun_image" -ceu '
    mkdir -p /toolchain/bun/bin
    cp -L "$(command -v bun)" /toolchain/bun/bin/bun
    ln -s bun /toolchain/bun/bin/bunx
    chmod -R a-w /toolchain
  '

verify_volume
created=false
trap - EXIT
echo "mcpgit-toolchain-init: created and verified $volume ($arch)"
