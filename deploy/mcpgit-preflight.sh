#!/usr/bin/env bash
set -euo pipefail

die() { echo "mcpgit-preflight: $*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: mcpgit-preflight.sh --bundle DIR [OPTIONS]

Read-only deployment inspection. Prints mcpgitrelease/preflight/v1 JSON.
Exit 0: ready. Exit 2: JSON contains blockers. Exit 1: invalid invocation.

Options:
  --instance NAME              default: mcpgit
  --project-name NAME          default: instance name
  --compose-project NAME       exact legacy Compose project
  --install-root DIR
  --config FILE
  --data-source VALUE
  --toolchain-volume NAME
  --netrc FILE
  --network NAME
  --runtime-env FILE
  --traefik-host HOST
  --no-traefik
EOF
}

bundle_dir= instance=mcpgit project_name= compose_project= install_root=
config_path= data_source= netrc_path= network= runtime_env_input=
toolchain_volume=mcpgit-toolchain-node22.23.1-bun1.3.14
traefik_host= traefik_mode=auto

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle) bundle_dir=${2:?}; shift 2 ;;
    --instance) instance=${2:?}; shift 2 ;;
    --project-name) project_name=${2:?}; shift 2 ;;
    --compose-project) compose_project=${2:?}; shift 2 ;;
    --install-root) install_root=${2:?}; shift 2 ;;
    --config) config_path=${2:?}; shift 2 ;;
    --data-source) data_source=${2:?}; shift 2 ;;
    --toolchain-volume) toolchain_volume=${2:?}; shift 2 ;;
    --netrc) netrc_path=${2:?}; shift 2 ;;
    --network) network=${2:?}; shift 2 ;;
    --runtime-env) runtime_env_input=${2:?}; shift 2 ;;
    --traefik-host) traefik_host=${2:?}; traefik_mode=on; shift 2 ;;
    --no-traefik) traefik_mode=off; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "$bundle_dir" ]] || die "--bundle is required"
[[ "$instance" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || die "invalid instance"
[[ -z "$project_name" || -z "$compose_project" ]] || die "project options are mutually exclusive"
if [[ -n "$compose_project" ]]; then project=$compose_project; else project=mcpgitrelease-${project_name:-$instance}; fi
for name in docker tar; do command -v "$name" >/dev/null 2>&1 || die "missing command: $name"; done

abs() { case "$1" in /*) printf '%s' "$1";; *) printf '%s/%s' "$PWD" "$1";; esac; }
escape() { local v=$1; v=${v//\/\\}; v=${v//\"/\\\"}; v=${v//$'\n'/\\n}; printf '"%s"' "$v"; }
array() { local first=1 v; printf '['; for v in "$@"; do ((first)) || printf ','; first=0; escape "$v"; done; printf ']'; }
sha() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}';
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}';
  else die "sha256sum or shasum is required"; fi
}
mount_source() {
  docker inspect --format '{{range .Mounts}}{{if eq .Destination "'"$2"'"}}{{if .Name}}{{.Name}}{{else}}{{.Source}}{{end}}{{end}}{{end}}' "$1" 2>/dev/null || true
}

blockers=() warnings=() blocker_count=0 warning_count=0
block() { blockers[$blocker_count]=$*; blocker_count=$((blocker_count + 1)); }
warn() { warnings[$warning_count]=$*; warning_count=$((warning_count + 1)); }

case "$(uname -m)" in x86_64|amd64) arch=amd64;; aarch64|arm64) arch=arm64;; *) die "unsupported architecture";; esac
host=$(hostname 2>/dev/null || printf unknown)
context=$(docker context show 2>/dev/null || printf unknown)
server=$(docker version --format '{{.Server.Version}}' 2>/dev/null || printf unavailable)
compose=false; docker compose version >/dev/null 2>&1 && compose=true || block "docker compose plugin is unavailable"

bundle_dir=$(abs "$bundle_dir")
[[ -d "$bundle_dir" ]] || die "bundle directory is missing"
manifest=$bundle_dir/install-linux-$arch.env
[[ -r "$manifest" ]] || die "installer manifest is missing"
required='|MCPGIT_INSTALL_SCHEMA|MCPGIT_CHANNEL|MCPGIT_ARCH|MCPGIT_BINARY_TAG|MCPGIT_BINARY_REVISION|MCPGIT_BINARY_FILE|MCPGIT_BINARY_URL|MCPGIT_BINARY_SHA256|MCPGIT_DEVBASE_TAG|MCPGIT_DEVBASE_IMAGE|MCPGIT_DEVBASE_FILE|MCPGIT_DEVBASE_URL|MCPGIT_DEVBASE_SHA256|MCPGIT_DEPLOY_TAG|MCPGIT_DEPLOY_FILE|MCPGIT_DEPLOY_URL|MCPGIT_DEPLOY_SHA256|'
seen='|'
while IFS= read -r line || [[ -n "$line" ]]; do
  line=${line%$'\r'}
  [[ "$line" =~ ^([A-Z][A-Z0-9_]*)=([A-Za-z0-9._:/-]+)$ ]] || die "invalid manifest line"
  key=${BASH_REMATCH[1]}; value=${BASH_REMATCH[2]}
  [[ "$required" == *"|$key|"* && "$seen" != *"|$key|"* ]] || die "invalid manifest key"
  printf -v "$key" '%s' "$value"; seen=$seen$key'|'
done < "$manifest"
for key in ${required//|/ }; do [[ -z "$key" || "$seen" == *"|$key|"* ]] || die "missing manifest key: $key"; done

[[ "$MCPGIT_INSTALL_SCHEMA" == mcpgitrelease/install/v1 ]] || block "unsupported installer schema"
[[ "$MCPGIT_ARCH" == "$arch" ]] || block "installer architecture mismatch"
[[ "$MCPGIT_BINARY_REVISION" =~ ^[0-9a-f]{40}$ ]] || block "invalid binary revision"

verify_asset() { [[ -r "$1" && "$(sha "$1")" == "$2" ]]; }
binary_ok=false; verify_asset "$bundle_dir/$MCPGIT_BINARY_FILE" "$MCPGIT_BINARY_SHA256" && binary_ok=true || block "binary archive is missing or invalid"
deploy_ok=false; verify_asset "$bundle_dir/$MCPGIT_DEPLOY_FILE" "$MCPGIT_DEPLOY_SHA256" && deploy_ok=true || block "deployment archive is missing or invalid"
devbase_ok=false; reusable_base=false
verify_asset "$bundle_dir/$MCPGIT_DEVBASE_FILE" "$MCPGIT_DEVBASE_SHA256" && devbase_ok=true || true
state_root=${XDG_DATA_HOME:-${HOME:-}/.local/share}/mcpgitrelease/devbase
if [[ -r "$state_root/$MCPGIT_DEVBASE_TAG.image-id" ]] && docker image inspect "$MCPGIT_DEVBASE_IMAGE" >/dev/null 2>&1; then
  expected=$(cat "$state_root/$MCPGIT_DEVBASE_TAG.image-id")
  actual=$(docker image inspect --format '{{.Id}}' "$MCPGIT_DEVBASE_IMAGE" 2>/dev/null || true)
  image_arch=$(docker image inspect --format '{{.Architecture}}' "$MCPGIT_DEVBASE_IMAGE" 2>/dev/null || true)
  [[ "$expected" == "$actual" && "$image_arch" == "$arch" ]] && reusable_base=true
fi
[[ "$devbase_ok" == true || "$reusable_base" == true ]] || block "no verified devbase archive or reusable local image"

toolchain_ok=false; docker volume inspect "$toolchain_volume" >/dev/null 2>&1 && toolchain_ok=true || block "toolchain volume is missing"

exists=false managed=false id= state=absent health= restarts=0 current_rev=
current_data= current_config= current_netrc= current_network=
if docker container inspect "$instance" >/dev/null 2>&1; then
  exists=true
  id=$(docker inspect --format '{{.Id}}' "$instance" 2>/dev/null || true)
  state=$(docker inspect --format '{{.State.Status}}' "$instance" 2>/dev/null || true)
  health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$instance" 2>/dev/null || true)
  restarts=$(docker inspect --format '{{.RestartCount}}' "$instance" 2>/dev/null || printf 0)
  [[ "$(docker inspect --format '{{index .Config.Labels "com.yxsicd.mcpgitrelease.managed"}}' "$instance" 2>/dev/null || true)" == true ]] && managed=true
  current_rev=$(docker inspect --format '{{index .Config.Labels "com.yxsicd.mcpgitrelease.binary"}}' "$instance" 2>/dev/null || true)
  current_data=$(mount_source "$instance" /data); current_config=$(mount_source "$instance" /config/mcpgit.toml)
  current_netrc=$(mount_source "$instance" /root/.netrc)
  current_network=$(docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$instance" 2>/dev/null | head -1)
  [[ "$state" == running && "$health" == healthy ]] || warn "current container is not running and healthy"
fi

if [[ -z "$install_root" ]]; then install_root=${XDG_DATA_HOME:-${HOME:-}/.local/share}/mcpgit/$instance; fi
install_root=$(abs "$install_root"); [[ -d "$install_root" ]] || warn "install root will be created"

if [[ -z "$config_path" ]]; then config_path=$current_config; fi
[[ -n "$config_path" ]] || config_path=$bundle_dir/deploy/mcpgit.toml
[[ -r "$config_path" ]] || config_path=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/mcpgit.toml
[[ -r "$config_path" ]] || block "MCPGit config cannot be resolved"

explicit_data=$([[ -n "$data_source" ]] && echo true || echo false)
[[ -n "$data_source" ]] || data_source=$current_data
[[ -n "$data_source" ]] || data_source=${instance}_data
[[ "$exists" == false || "$explicit_data" == true || -n "$current_data" ]] || block "existing /data source cannot be inferred; pass --data-source"
if [[ "$data_source" == */* ]]; then [[ -d "$data_source" ]] || warn "data bind directory will be created";
elif ! docker volume inspect "$data_source" >/dev/null 2>&1; then warn "data volume will be created"; fi

[[ -n "$netrc_path" ]] || netrc_path=$current_netrc
[[ -n "$netrc_path" || ! -r "${HOME:-}/.netrc" ]] || netrc_path=$HOME/.netrc
if [[ -n "$netrc_path" && ! -f "$netrc_path" ]]; then block "netrc is not a regular file";
elif [[ -z "$netrc_path" ]]; then netrc_path=$install_root/state/empty.netrc; warn "an empty netrc will be created"; fi

explicit_network=$([[ -n "$network" ]] && echo true || echo false)
[[ -n "$network" ]] || network=$current_network
[[ -n "$network" ]] || network=mcpgit
[[ "$exists" == false || "$explicit_network" == true || -n "$current_network" ]] || block "existing network cannot be inferred; pass --network"
docker network inspect "$network" >/dev/null 2>&1 || warn "Docker network will be created"

if [[ -n "$runtime_env_input" && ! -r "$runtime_env_input" ]]; then block "runtime env is not readable"; fi
[[ -n "$runtime_env_input" ]] || runtime_env_input=$bundle_dir/mcpgit-runtime.env
[[ -r "$runtime_env_input" || "$exists" == true ]] || warn "no runtime env supplied"
[[ "$traefik_mode" != on || -n "$traefik_host" ]] || block "Traefik is enabled without a hostname"

managed_rollback=false; legacy_rollback=false
[[ -r "$install_root/state/previous-release" && -r "$install_root/state/previous-instance.env" ]] && managed_rollback=true
if [[ -r "$install_root/state/legacy-container" ]]; then legacy=$(cat "$install_root/state/legacy-container"); docker container inspect "$legacy" >/dev/null 2>&1 && legacy_rollback=true || true; fi
[[ "$exists" == true && "$managed" == false ]] && warn "unmanaged container will be retained as a legacy rollback candidate"
warn "confirm this exact hostname and Docker context are user-approved"

ready=true; (( blocker_count == 0 )) || ready=false
printf '{"schema":"mcpgitrelease/preflight/v1","ready":%s,' "$ready"
printf '"host":{"hostname":'; escape "$host"; printf ',"architecture":'; escape "$arch"; printf ',"docker_context":'; escape "$context"; printf ',"docker_server_version":'; escape "$server"; printf ',"compose_available":%s},' "$compose"
printf '"target":{"instance":'; escape "$instance"; printf ',"compose_project":'; escape "$project"; printf ',"install_root":'; escape "$install_root"; printf '},'
printf '"bundle":{"directory":'; escape "$bundle_dir"; printf ',"channel":'; escape "$MCPGIT_CHANNEL"; printf ',"binary_revision":'; escape "$MCPGIT_BINARY_REVISION"; printf ',"binary_verified":%s,"devbase_archive_verified":%s,"devbase_reusable":%s,"deployment_verified":%s},' "$binary_ok" "$devbase_ok" "$reusable_base" "$deploy_ok"
printf '"current":{"exists":%s,"managed":%s,"container_id":' "$exists" "$managed"; escape "$id"; printf ',"state":'; escape "$state"; printf ',"health":'; escape "$health"; printf ',"restart_count":%s,"binary_revision":' "$restarts"; escape "$current_rev"; printf ',"data_source":'; escape "$current_data"; printf ',"config_source":'; escape "$current_config"; printf ',"netrc_source":'; escape "$current_netrc"; printf ',"network":'; escape "$current_network"; printf '},'
printf '"proposed":{"data_source":'; escape "$data_source"; printf ',"config":'; escape "$config_path"; printf ',"netrc":'; escape "$netrc_path"; printf ',"network":'; escape "$network"; printf ',"runtime_env":'; escape "$runtime_env_input"; printf ',"toolchain_volume":'; escape "$toolchain_volume"; printf ',"toolchain_exists":%s,"traefik_mode":' "$toolchain_ok"; escape "$traefik_mode"; printf ',"traefik_host":'; escape "$traefik_host"; printf '},'
printf '"rollback":{"managed_available":%s,"legacy_available":%s},"blockers":' "$managed_rollback" "$legacy_rollback"
if (( blocker_count > 0 )); then array "${blockers[@]}"; else printf '[]'; fi
printf ',"warnings":'
if (( warning_count > 0 )); then array "${warnings[@]}"; else printf '[]'; fi
printf '}\n'
[[ "$ready" == true ]] || exit 2
