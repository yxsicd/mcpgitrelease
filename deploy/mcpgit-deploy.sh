#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "mcpgit-deploy: $*" >&2
  exit 1
}

info() {
  echo "mcpgit-deploy: $*"
}

usage() {
  cat <<'EOF'
Usage:
  mcpgit-deploy.sh --bundle DIR [OPTIONS]
  mcpgit-deploy.sh --instance NAME --rollback [OPTIONS]

The bundle directory must contain install-linux-<arch>.env and the matching
MCPGit binary tar.gz. A cold install also needs the matching devbase Docker
tar.zst; a managed hot update reuses the previously verified local devbase.

Options:
  --instance NAME       Container and instance name (default: mcpgit)
  --install-root DIR    Persistent deployment state directory
  --config FILE         MCPGit configuration; old or bundled config is used by default
  --data-source VALUE   Named volume or bind directory mounted at /data
  --netrc FILE          Netrc file; inferred from an old container
  --network NAME        Docker network; inferred or created as mcpgit
  --runtime-env FILE    Remote/backend environment; old or bundled env is used by default
  --traefik-host HOST   Enable Traefik and route this hostname
  --no-traefik          Disable Traefik even if a legacy instance used it
  --rollback            Roll back to the previous managed or legacy instance
EOF
}

bundle_dir=
instance=mcpgit
install_root=
config_path=
data_source=
netrc_path=
network=
runtime_env_input=
traefik_host=
traefik_mode=auto
rollback=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle) [[ $# -ge 2 ]] || die "--bundle requires a value"; bundle_dir=$2; shift 2 ;;
    --instance) [[ $# -ge 2 ]] || die "--instance requires a value"; instance=$2; shift 2 ;;
    --install-root) [[ $# -ge 2 ]] || die "--install-root requires a value"; install_root=$2; shift 2 ;;
    --config) [[ $# -ge 2 ]] || die "--config requires a value"; config_path=$2; shift 2 ;;
    --data-source) [[ $# -ge 2 ]] || die "--data-source requires a value"; data_source=$2; shift 2 ;;
    --netrc) [[ $# -ge 2 ]] || die "--netrc requires a value"; netrc_path=$2; shift 2 ;;
    --network) [[ $# -ge 2 ]] || die "--network requires a value"; network=$2; shift 2 ;;
    --runtime-env) [[ $# -ge 2 ]] || die "--runtime-env requires a value"; runtime_env_input=$2; shift 2 ;;
    --traefik-host) [[ $# -ge 2 ]] || die "--traefik-host requires a value"; traefik_host=$2; traefik_mode=on; shift 2 ;;
    --no-traefik) traefik_mode=off; shift ;;
    --rollback) rollback=true; shift ;;
    -h | --help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ "$instance" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || die "invalid instance name"
if [[ -z "$install_root" ]]; then
  state_home=${XDG_DATA_HOME:-${HOME:-}/.local/share}
  [[ -n "$state_home" ]] || die "HOME or --install-root is required"
  install_root=$state_home/mcpgit/$instance
fi
install_root=$(mkdir -p "$install_root" && cd "$install_root" && pwd -P)
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
compose_file=$install_root/runtime/compose.yaml
instance_env=$install_root/state/instance.env
runtime_env=$install_root/state/runtime.env
project=mcpgitrelease-$instance

for command_name in docker tar; do
  command -v "$command_name" >/dev/null 2>&1 || die "required command is missing: $command_name"
done
docker compose version >/dev/null 2>&1 || die "docker compose plugin is required"

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    die "sha256sum or shasum is required"
  fi
}

cleanup_staging() {
  if [[ -n ${staging:-} && "$staging" == "$install_root/releases/.staging."* ]]; then
    rm -rf -- "$staging"
  fi
}

mount_source() {
  local container=$1 destination=$2
  docker inspect --format '{{range .Mounts}}{{if eq .Destination "'"$destination"'"}}{{if .Name}}{{.Name}}{{else}}{{.Source}}{{end}}{{end}}{{end}}' "$container"
}

old_env() {
  local container=$1 key=$2
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$container" | awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}'
}

wait_healthy() {
  local container=$1 state health
  for attempt in $(seq 1 60); do
    state=$(docker inspect --format '{{.State.Status}}' "$container" 2>/dev/null || true)
    health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container" 2>/dev/null || true)
    [[ "$state" == restarting || "$state" == exited || "$state" == dead ]] && return 1
    [[ "$state" == running && "$health" == healthy ]] && return 0
    sleep 2
  done
  return 1
}

compose() {
  docker compose --project-name "$project" --env-file "$instance_env" -f "$compose_file" "$@"
}

atomic_link() {
  local target=$1 link=$2
  ln -sfn "$target" "$link"
  [[ "$(readlink "$link")" == "$target" ]] || die "failed to update release link"
}

write_instance_env() {
  local temp=$instance_env.new.$$
  umask 077
  {
    printf 'MCPGIT_DEVBASE_IMAGE=%s\n' "$MCPGIT_DEVBASE_IMAGE"
    printf 'MCPGIT_BINARY_REVISION=%s\n' "$MCPGIT_BINARY_REVISION"
    printf 'MCPGIT_CONTAINER_NAME=%s\n' "$instance"
    printf 'MCPGIT_INSTALL_ROOT=%s\n' "$install_root"
    printf 'MCPGIT_CONFIG=%s\n' "$config_path"
    printf 'MCPGIT_DATA_SOURCE=%s\n' "$data_source"
    printf 'MCPGIT_NETRC=%s\n' "$netrc_path"
    printf 'MCPGIT_NETWORK=%s\n' "$network"
    printf 'MCPGIT_RUNTIME_ENV_FILE=%s\n' "$runtime_env"
    printf 'MCPGIT_TRAEFIK_ENABLE=%s\n' "$traefik_enable"
    printf 'MCPGIT_TRAEFIK_SERVICE=%s\n' "$instance"
    printf 'MCPGIT_TRAEFIK_HOST=%s\n' "${traefik_host:-localhost}"
  } > "$temp"
  mv -f "$temp" "$instance_env"
}

rollback_managed() {
  [[ -r "$install_root/state/previous-release" ]] || return 1
  [[ -r "$install_root/state/previous-instance.env" ]] || return 1
  previous_release=$(cat "$install_root/state/previous-release")
  [[ "$previous_release" =~ ^releases/[0-9a-f]{40}$ ]] || die "invalid previous release state"
  [[ -x "$install_root/$previous_release/mcpgit" ]] || die "previous binary is missing"
  current_release=$(readlink "$install_root/current")
  cp "$instance_env" "$install_root/state/next-instance.env"
  cp "$install_root/state/previous-instance.env" "$instance_env"
  printf '%s\n' "$current_release" > "$install_root/state/next-release"
  atomic_link "$previous_release" "$install_root/current"
  if compose up -d --force-recreate --no-build --pull never && wait_healthy "$instance"; then
    mv -f "$install_root/state/next-instance.env" "$install_root/state/previous-instance.env"
    mv -f "$install_root/state/next-release" "$install_root/state/previous-release"
    info "rollback complete: $previous_release"
    return 0
  fi
  atomic_link "$current_release" "$install_root/current"
  cp "$install_root/state/next-instance.env" "$instance_env"
  compose up -d --force-recreate --no-build --pull never || true
  die "rollback candidate failed health checks; restored current deployment"
}

rollback_legacy() {
  [[ -r "$install_root/state/legacy-container" ]] || return 1
  legacy=$(cat "$install_root/state/legacy-container")
  docker container inspect "$legacy" >/dev/null 2>&1 || return 1
  compose down >/dev/null 2>&1 || true
  docker rename "$legacy" "$instance"
  docker start "$instance" >/dev/null
  info "legacy container restored: $instance"
}

mkdir -p "$install_root/runtime" "$install_root/releases" "$install_root/state"
install -m 0644 "$script_dir/compose.yaml" "$compose_file"
install -m 0755 "$script_dir/docker-entrypoint.sh" "$install_root/runtime/docker-entrypoint.sh"
install -m 0755 "$script_dir/git-credential-netrc" "$install_root/runtime/git-credential-netrc"

if [[ "$rollback" == true ]]; then
  [[ -r "$instance_env" ]] || die "instance has no managed deployment state"
  rollback_managed || rollback_legacy || die "no rollback target is available"
  exit 0
fi

[[ -n "$bundle_dir" ]] || die "--bundle is required for installation"
bundle_dir=$(cd "$bundle_dir" && pwd -P)
case "$(uname -m)" in
  x86_64 | amd64) host_arch=amd64 ;;
  aarch64 | arm64) host_arch=arm64 ;;
  *) die "unsupported host architecture: $(uname -m)" ;;
esac
install_manifest=$bundle_dir/install-linux-$host_arch.env
[[ -r "$install_manifest" ]] || die "installer manifest is missing: $install_manifest"

required_keys='|MCPGIT_INSTALL_SCHEMA|MCPGIT_CHANNEL|MCPGIT_ARCH|MCPGIT_BINARY_TAG|MCPGIT_BINARY_REVISION|MCPGIT_BINARY_FILE|MCPGIT_BINARY_URL|MCPGIT_BINARY_SHA256|MCPGIT_DEVBASE_TAG|MCPGIT_DEVBASE_IMAGE|MCPGIT_DEVBASE_FILE|MCPGIT_DEVBASE_URL|MCPGIT_DEVBASE_SHA256|MCPGIT_DEPLOY_TAG|MCPGIT_DEPLOY_FILE|MCPGIT_DEPLOY_URL|MCPGIT_DEPLOY_SHA256|'
seen='|'
while IFS= read -r line || [[ -n "$line" ]]; do
  line=${line%$'\r'}
  [[ "$line" =~ ^([A-Z][A-Z0-9_]*)=([A-Za-z0-9._:/-]+)$ ]] || die "invalid installer manifest line"
  key=${BASH_REMATCH[1]}
  value=${BASH_REMATCH[2]}
  [[ "$required_keys" == *"|$key|"* ]] || die "unsupported installer key: $key"
  [[ "$seen" != *"|$key|"* ]] || die "duplicate installer key: $key"
  printf -v "$key" '%s' "$value"
  seen=$seen$key'|'
done < "$install_manifest"
for key in ${required_keys//|/ }; do
  [[ -z "$key" ]] && continue
  [[ "$seen" == *"|$key|"* ]] || die "missing installer key: $key"
done

[[ "$MCPGIT_INSTALL_SCHEMA" == mcpgitrelease/install/v1 ]] || die "unsupported installer schema"
[[ "$MCPGIT_ARCH" == "$host_arch" ]] || die "installer architecture mismatch"
[[ "$MCPGIT_BINARY_REVISION" =~ ^[0-9a-f]{40}$ ]] || die "invalid binary revision"
[[ "$MCPGIT_DEVBASE_TAG" =~ ^devbase-[0-9]{4}\.[0-9]{2}\.[0-9]+$ ]] || die "invalid devbase tag"
[[ "$MCPGIT_DEVBASE_IMAGE" == "mcpgit-devbase:$MCPGIT_DEVBASE_TAG" ]] || die "invalid devbase image"
[[ "$MCPGIT_BINARY_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "invalid binary checksum"
[[ "$MCPGIT_DEVBASE_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "invalid devbase checksum"
[[ "$MCPGIT_DEPLOY_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "invalid deployment checksum"
[[ "$MCPGIT_BINARY_FILE" == mcpgit-linux-$host_arch.tar.gz ]] || die "unexpected binary filename"
[[ "$MCPGIT_DEVBASE_FILE" == mcpgit-devbase-linux-$host_arch.docker.tar.zst ]] || die "unexpected devbase filename"
[[ "$MCPGIT_DEPLOY_FILE" == mcpgit-deploy.tar.gz ]] || die "unexpected deployment filename"

binary_archive=$bundle_dir/$MCPGIT_BINARY_FILE
devbase_archive=$bundle_dir/$MCPGIT_DEVBASE_FILE
[[ -r "$binary_archive" ]] || die "binary archive is missing"
[[ "$(sha256_file "$binary_archive")" == "$MCPGIT_BINARY_SHA256" ]] || die "binary checksum mismatch"

if [[ -n ${XDG_DATA_HOME:-} ]]; then
  devbase_state_root=$XDG_DATA_HOME/mcpgitrelease/devbase
elif [[ -n ${HOME:-} ]]; then
  devbase_state_root=$HOME/.local/share/mcpgitrelease/devbase
else
  devbase_state_root=$install_root/state/devbase
fi
mkdir -p "$devbase_state_root"
devbase_identity=$devbase_state_root/$MCPGIT_DEVBASE_TAG.image-id
reuse_devbase=false
if [[ -r "$devbase_identity" ]] && docker image inspect "$MCPGIT_DEVBASE_IMAGE" >/dev/null 2>&1; then
  expected_image_id=$(cat "$devbase_identity")
  actual_image_id=$(docker image inspect --format '{{.Id}}' "$MCPGIT_DEVBASE_IMAGE")
  image_arch=$(docker image inspect --format '{{.Architecture}}' "$MCPGIT_DEVBASE_IMAGE")
  if [[ "$expected_image_id" =~ ^sha256:[0-9a-f]{64}$ && "$actual_image_id" == "$expected_image_id" && "$image_arch" == "$host_arch" ]]; then
    reuse_devbase=true
  fi
fi

if [[ "$reuse_devbase" == true ]]; then
  info "reusing verified cold base $MCPGIT_DEVBASE_IMAGE"
else
  [[ -r "$devbase_archive" ]] || die "verified devbase identity is unavailable and the cold archive is missing"
  [[ "$(sha256_file "$devbase_archive")" == "$MCPGIT_DEVBASE_SHA256" ]] || die "devbase checksum mismatch"
  info "loading verified cold base image $MCPGIT_DEVBASE_IMAGE"
  docker load -i "$devbase_archive" >/dev/null
  docker image inspect "$MCPGIT_DEVBASE_IMAGE" >/dev/null 2>&1 || die "loaded archive did not provide $MCPGIT_DEVBASE_IMAGE"
  image_arch=$(docker image inspect --format '{{.Architecture}}' "$MCPGIT_DEVBASE_IMAGE")
  [[ "$image_arch" == "$host_arch" ]] || die "devbase image architecture mismatch: $image_arch"
  actual_image_id=$(docker image inspect --format '{{.Id}}' "$MCPGIT_DEVBASE_IMAGE")
  [[ "$actual_image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || die "invalid loaded devbase image id"
  temp_identity=$devbase_identity.new.$$
  printf '%s\n' "$actual_image_id" > "$temp_identity"
  mv -f "$temp_identity" "$devbase_identity"
fi

release_relative=releases/$MCPGIT_BINARY_REVISION
release_dir=$install_root/$release_relative
if [[ ! -x "$release_dir/mcpgit" ]]; then
  staging=$(mktemp -d "$install_root/releases/.staging.XXXXXX")
  trap cleanup_staging EXIT
  contents=$(tar -tzf "$binary_archive")
  [[ "$contents" == mcpgit ]] || die "binary archive must contain exactly one mcpgit file"
  tar -xzf "$binary_archive" -C "$staging"
  chmod 0755 "$staging/mcpgit"
  docker run --rm --entrypoint /opt/release/mcpgit -v "$staging:/opt/release:ro" "$MCPGIT_DEVBASE_IMAGE" --help >/dev/null
  mv "$staging" "$release_dir"
  staging=
  trap - EXIT
fi

old_exists=false
old_managed=false
if docker container inspect "$instance" >/dev/null 2>&1; then
  old_exists=true
  old_label=$(docker inspect --format '{{index .Config.Labels "com.yxsicd.mcpgitrelease.managed"}}' "$instance" 2>/dev/null || true)
  [[ "$old_label" == true ]] && old_managed=true
fi

if [[ -z "$config_path" && "$old_exists" == true ]]; then config_path=$(mount_source "$instance" /config/mcpgit.toml); fi
if [[ -z "$config_path" && -r "$bundle_dir/mcpgit.toml" ]]; then config_path=$bundle_dir/mcpgit.toml; fi
if [[ -z "$config_path" && -r "$script_dir/mcpgit.toml" ]]; then config_path=$script_dir/mcpgit.toml; fi
[[ -n "$config_path" && -r "$config_path" ]] || die "MCPGit config is required"
config_path=$(cd "$(dirname "$config_path")" && pwd -P)/$(basename "$config_path")

if [[ -z "$data_source" && "$old_exists" == true ]]; then data_source=$(mount_source "$instance" /data); fi
[[ -n "$data_source" ]] || data_source=${instance}_data
if [[ "$data_source" == */* ]]; then
  data_source=$(mkdir -p "$data_source" && cd "$data_source" && pwd -P)
  bind_volume=mcpgitrelease-$instance-data
  if docker volume inspect "$bind_volume" >/dev/null 2>&1; then
    existing_device=$(docker volume inspect --format '{{index .Options "device"}}' "$bind_volume")
    [[ "$existing_device" == "$data_source" ]] || die "data bind volume already points to $existing_device"
  else
    docker volume create --driver local --opt type=none --opt o=bind --opt "device=$data_source" "$bind_volume" >/dev/null
  fi
  data_source=$bind_volume
fi
docker volume inspect "$data_source" >/dev/null 2>&1 || docker volume create "$data_source" >/dev/null

if [[ -z "$netrc_path" && "$old_exists" == true ]]; then netrc_path=$(mount_source "$instance" /root/.netrc); fi
if [[ -z "$netrc_path" && -r "${HOME:-}/.netrc" ]]; then netrc_path=$HOME/.netrc; fi
if [[ -z "$netrc_path" ]]; then
  netrc_path=$install_root/state/empty.netrc
  umask 077
  : > "$netrc_path"
fi
[[ -f "$netrc_path" ]] || die "netrc path is not a regular file"
netrc_path=$(cd "$(dirname "$netrc_path")" && pwd -P)/$(basename "$netrc_path")

if [[ -z "$network" && "$old_exists" == true ]]; then
  network=$(docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$instance" | head -1)
fi
[[ -n "$network" ]] || network=mcpgit
docker network inspect "$network" >/dev/null 2>&1 || docker network create "$network" >/dev/null

if [[ -n "$runtime_env_input" ]]; then
  [[ -r "$runtime_env_input" ]] || die "runtime env is not readable"
  install -m 0600 "$runtime_env_input" "$runtime_env"
elif [[ "$old_exists" == true ]]; then
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$instance" | grep -E '^(MCPGIT_[A-Z0-9_]*|RUST_LOG)=[^[:cntrl:]]*$' > "$runtime_env" || true
  chmod 0600 "$runtime_env"
elif [[ -r "$bundle_dir/mcpgit-runtime.env" ]]; then
  install -m 0600 "$bundle_dir/mcpgit-runtime.env" "$runtime_env"
else
  : > "$runtime_env"
  chmod 0600 "$runtime_env"
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  line=${line%$'\r'}
  [[ -z "$line" || "$line" == \#* || "$line" =~ ^(MCPGIT_[A-Z0-9_]*|RUST_LOG)=[^[:cntrl:]]*$ ]] \
    || die "runtime env contains an unsupported line"
done < "$runtime_env"

if [[ "$traefik_mode" == auto && "$old_exists" == true ]]; then
  old_traefik=$(docker inspect --format '{{index .Config.Labels "traefik.enable"}}' "$instance" 2>/dev/null || true)
  [[ "$old_traefik" == true ]] && traefik_mode=on || traefik_mode=off
  if [[ "$traefik_mode" == on && -z "$traefik_host" ]]; then
    public_url=$(old_env "$instance" MCPGIT_PUBLIC_BASE_URL)
    traefik_host=${public_url#*://}
    traefik_host=${traefik_host%%/*}
  fi
fi
[[ "$traefik_mode" == on ]] && traefik_enable=true || traefik_enable=false
[[ "$traefik_enable" == false || -n "$traefik_host" ]] || die "Traefik hostname could not be inferred; pass --traefik-host"

previous_release=
if [[ -L "$install_root/current" ]]; then previous_release=$(readlink "$install_root/current"); fi
if [[ -n "$previous_release" ]]; then
  [[ "$previous_release" =~ ^releases/[0-9a-f]{40}$ ]] || die "current release link is invalid"
  printf '%s\n' "$previous_release" > "$install_root/state/previous-release"
fi
if [[ -r "$instance_env" ]]; then cp "$instance_env" "$install_root/state/previous-instance.env"; fi
atomic_link "$release_relative" "$install_root/current"
write_instance_env

legacy_backup=
if [[ "$old_exists" == true && "$old_managed" == false ]]; then
  legacy_backup=$instance-legacy-$(date -u +%Y%m%d%H%M%S)
  docker stop "$instance" >/dev/null
  docker rename "$instance" "$legacy_backup"
  printf '%s\n' "$legacy_backup" > "$install_root/state/legacy-container"
fi

if ! compose up -d --force-recreate --no-build --pull never || ! wait_healthy "$instance"; then
  info "new deployment failed health checks; rolling back"
  compose down >/dev/null 2>&1 || true
  if [[ -n "$legacy_backup" ]]; then
    docker rename "$legacy_backup" "$instance"
    docker start "$instance" >/dev/null
  elif [[ -n "$previous_release" && -r "$install_root/state/previous-instance.env" ]]; then
    atomic_link "$previous_release" "$install_root/current"
    cp "$install_root/state/previous-instance.env" "$instance_env"
    if ! compose up -d --force-recreate --no-build --pull never || ! wait_healthy "$instance"; then
      die "deployment and automatic rollback both failed; inspect docker logs $instance"
    fi
  fi
  die "deployment failed and the previous instance was restored"
fi

printf '%s\n' "$MCPGIT_BINARY_REVISION" > "$install_root/state/managed"
info "deployment healthy: instance=$instance channel=$MCPGIT_CHANNEL revision=$MCPGIT_BINARY_REVISION"
if [[ -n "$legacy_backup" ]]; then info "legacy rollback container retained as $legacy_backup"; fi
