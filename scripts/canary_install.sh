#!/usr/bin/env bash
set -euo pipefail

instance="mcpgit-canary-$(git rev-parse --short=8 HEAD 2>/dev/null || date +%s)"
port=18031
revision="$(git rev-parse HEAD 2>/dev/null || true)"
bundle=""
credential_dir=""
evidence=""
cleanup_on_success=true

usage() {
  cat <<'EOF'
Usage: scripts/canary_install.sh [OPTIONS]

Run a disposable MCPGit one-command installer canary from this repository.
The canary verifies fresh install, post-install Docker health, /healthz,
mcpgitctl doctor, and exact-current no-restart re-run. Credentials are never
printed into evidence. On failure, runtime resources are retained for debugging.

Options:
  --instance NAME        disposable instance name
  --port PORT            host port for canary (default: 18031)
  --revision SHA         install repository revision to pin (default: HEAD)
  --bundle DIR           temporary bundle/cache directory
  --credential-dir DIR   temporary credential directory
  --evidence FILE        evidence JSON output path
  --keep                 keep canary container, data, bundle and credentials on success
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --instance) instance=${2:?}; shift 2 ;;
    --port) port=${2:?}; shift 2 ;;
    --revision) revision=${2:?}; shift 2 ;;
    --bundle) bundle=${2:?}; shift 2 ;;
    --credential-dir) credential_dir=${2:?}; shift 2 ;;
    --evidence) evidence=${2:?}; shift 2 ;;
    --keep) cleanup_on_success=false; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

[[ -n "$revision" && "$revision" =~ ^[0-9a-f]{40}$ ]] || { echo "canary: --revision must be a full Git SHA" >&2; exit 1; }
[[ "$instance" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || { echo "canary: invalid instance name" >&2; exit 1; }
[[ "$port" =~ ^[0-9]+$ ]] || { echo "canary: invalid port" >&2; exit 1; }
[[ -x ./install.sh ]] || { echo "canary: run from mcpgitrelease root with ./install.sh" >&2; exit 1; }

bundle=${bundle:-"${TMPDIR:-/tmp}/${instance}-bundle"}
credential_dir=${credential_dir:-"${TMPDIR:-/tmp}/${instance}-creds"}
evidence=${evidence:-"${TMPDIR:-/tmp}/${instance}-canary.json"}
mkdir -p "$(dirname "$evidence")"

cleanup_old() {
  docker rm -f "$instance" >/dev/null 2>&1 || true
  docker volume rm "${instance}_data" >/dev/null 2>&1 || true
  rm -rf -- "$bundle" "$credential_dir"
}

wait_healthy() {
  local observed_state= observed_health=
  for attempt in $(seq 1 90); do
    observed_state=$(docker inspect "$instance" --format '{{.State.Status}}' 2>/dev/null || true)
    observed_health=$(docker inspect "$instance" --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' 2>/dev/null || true)
    if [[ "$observed_state" == running && "$observed_health" == healthy ]]; then
      return 0
    fi
    sleep 2
  done
  echo "canary: Docker health did not settle: state=$observed_state health=$observed_health" >&2
  return 1
}

healthz() {
  curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$port/healthz" || true
}

write_evidence() {
  local cid=$1 created=$2 code=$3
  python3 - "$evidence" "$revision" "$instance" "$port" "$cid" "$created" "$code" <<'PY'
import json, pathlib, subprocess, sys
path, revision, instance, port, cid, created, code = sys.argv[1:]
container = json.loads(subprocess.check_output(["docker", "inspect", instance], text=True))[0]
labels = {
    key: value
    for key, value in (container.get("Config", {}).get("Labels") or {}).items()
    if key.startswith("com.yxsicd.mcpgit.")
}
def tail(path: str) -> str:
    p = pathlib.Path(path)
    return p.read_text(errors="replace")[-4000:] if p.exists() else ""
value = {
    "schema": "mcpgitrelease/canary-evidence/v1",
    "release_repo_revision": revision,
    "instance": instance,
    "port": int(port),
    "container_id": cid[:12],
    "created": created,
    "healthz_code": int(code),
    "docker_health": container.get("State", {}).get("Health", {}).get("Status"),
    "image": container.get("Config", {}).get("Image"),
    "labels": labels,
    "checks": {
        "fresh_install": True,
        "post_install_health_wait": True,
        "healthz": True,
        "doctor": True,
        "exact_current_no_restart": True,
    },
    "status_log_tail": tail(f"/tmp/{instance}.status.log"),
    "doctor_log_tail": tail(f"/tmp/{instance}.doctor.log"),
    "install2_log_tail": tail(f"/tmp/{instance}.install2.log"),
}
pathlib.Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
print(json.dumps({"evidence": path, "image": value["image"], "health": value["docker_health"], "checks": value["checks"]}, indent=2))
PY
}

cleanup_old
started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "canary: start instance=$instance port=$port revision=$revision started_at=$started_at"
MCPGIT_INSTALL_REVISION="$revision" MCPGIT_INSTANCE="$instance" MCPGIT_PORT="$port" MCPGIT_BUNDLE_DIR="$bundle" MCPGIT_CREDENTIAL_DIR="$credential_dir" \
  ./install.sh --instance "$instance" --port "$port" 2>&1 | tee "/tmp/${instance}.install1.log"
wait_healthy
code=$(healthz)
[[ "$code" == 204 ]] || { echo "canary: /healthz returned $code" >&2; exit 1; }
"${HOME}/.local/bin/mcpgitctl" --instance "$instance" --url "http://127.0.0.1:$port" status > "/tmp/${instance}.status.log"
"${HOME}/.local/bin/mcpgitctl" --instance "$instance" --url "http://127.0.0.1:$port" doctor > "/tmp/${instance}.doctor.log"
cid1=$(docker inspect "$instance" --format '{{.Id}}')
created1=$(docker inspect "$instance" --format '{{.Created}}')
MCPGIT_INSTALL_REVISION="$revision" MCPGIT_INSTANCE="$instance" MCPGIT_PORT="$port" MCPGIT_BUNDLE_DIR="$bundle" MCPGIT_CREDENTIAL_DIR="$credential_dir" \
  ./install.sh --instance "$instance" --port "$port" > "/tmp/${instance}.install2.log" 2>&1
cid2=$(docker inspect "$instance" --format '{{.Id}}')
created2=$(docker inspect "$instance" --format '{{.Created}}')
[[ "$cid1" == "$cid2" ]] || { echo "canary: exact-current re-run recreated the container" >&2; exit 1; }
[[ "$created1" == "$created2" ]] || { echo "canary: exact-current re-run changed created timestamp" >&2; exit 1; }
write_evidence "$cid1" "$created1" "$code"
if [[ "$cleanup_on_success" == true ]]; then
  docker rm -f "$instance" >/dev/null
  docker volume rm "${instance}_data" >/dev/null || true
  rm -rf -- "$bundle" "$credential_dir"
fi
echo "canary: PASS evidence=$evidence"
