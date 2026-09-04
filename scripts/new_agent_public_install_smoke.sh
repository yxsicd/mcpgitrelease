#!/usr/bin/env bash
set -euo pipefail

instance="mcpgit-newagent-$(git rev-parse --short=8 HEAD 2>/dev/null || date +%s)"
port=18041
expected_source_sha=""
install_url="https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/install.sh"
evidence=""
cleanup_on_success=true

usage() {
  cat <<'EOF'
Usage: scripts/new_agent_public_install_smoke.sh [OPTIONS]

Exercise the public GitHub installer exactly as a new agent would. The smoke
fetches install.sh from the public main branch, creates a disposable novice
instance, verifies health, mcpgitctl doctor, MCP initialize/tools-list, standard
repository initialization, credential-file mode, and release identity. Secrets
and credential file contents are never printed or written into evidence.

Options:
  --instance NAME             disposable instance name
  --port PORT                 host port (default: 18041)
  --expected-source-sha SHA   accepted MCPGit source SHA for release identity
  --install-url URL           public installer URL override
  --evidence FILE             output evidence JSON
  --keep                      keep container, data volume, bundle and credentials on success
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --instance) instance=${2:?}; shift 2 ;;
    --port) port=${2:?}; shift 2 ;;
    --expected-source-sha) expected_source_sha=${2:?}; shift 2 ;;
    --install-url) install_url=${2:?}; shift 2 ;;
    --evidence) evidence=${2:?}; shift 2 ;;
    --keep) cleanup_on_success=false; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

[[ "$instance" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || { echo "new-agent-smoke: invalid instance name" >&2; exit 1; }
[[ "$port" =~ ^[0-9]+$ ]] || { echo "new-agent-smoke: invalid port" >&2; exit 1; }
if [[ -n "$expected_source_sha" && ! "$expected_source_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "new-agent-smoke: --expected-source-sha must be a full Git SHA" >&2
  exit 1
fi

tmp_root="${TMPDIR:-/tmp}"
bundle="$tmp_root/${instance}-bundle"
credentials="$tmp_root/${instance}-creds"
installer="$tmp_root/${instance}-install.sh"
instance_config="${HOME:?HOME is required}/.mcpgit/instances/${instance}.toml"
evidence=${evidence:-"$tmp_root/${instance}-public-install-evidence.json"}
mkdir -p "$(dirname "$evidence")"

cleanup_old() {
  docker rm -f "$instance" >/dev/null 2>&1 || true
  docker volume rm "${instance}_data" >/dev/null 2>&1 || true
  rm -rf -- "$bundle" "$credentials" "$installer"
  rm -f -- "$instance_config"
}

cleanup_sensitive() {
  rm -rf -- "$credentials" "$installer"
  rm -f -- "$instance_config"
}

cleanup_failed_sensitive() {
  local status=$?
  if [[ "$status" != 0 && "$cleanup_on_success" == true ]]; then
    cleanup_sensitive
  fi
  return "$status"
}
trap cleanup_failed_sensitive EXIT

redact_log() {
  sed -E 's/(MCPGIT_[A-Z0-9_]*(TOKEN|SECRET|PASSWORD|VERIFY|AUTHORIZATION|KEY)[A-Z0-9_]*=).*/\1<redacted>/g'
}

wait_healthy() {
  local state= health=
  for _ in $(seq 1 90); do
    state=$(docker inspect "$instance" --format '{{.State.Status}}' 2>/dev/null || true)
    health=$(docker inspect "$instance" --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' 2>/dev/null || true)
    [[ "$state" == running && "$health" == healthy ]] && return 0
    sleep 2
  done
  echo "new-agent-smoke: Docker health did not settle: state=$state health=$health" >&2
  return 1
}

mcp_probe() {
  python3 - "$instance" "$port" "$tmp_root/${instance}.mcp.json" <<'PY'
import http.client, json, sys
instance, port, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
body = json.dumps({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "new-agent-smoke", "version": "0.0.1"},
    },
}).encode()
headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
conn.request("POST", "/mcp", body, headers)
resp = conn.getresponse()
text = resp.read().decode("utf-8", "replace")
response_headers = {key.lower(): value for key, value in resp.getheaders()}
value = {
    "initialize_status": resp.status,
    "initialize_headers": {key: response_headers[key] for key in ("content-type", "mcp-session-id") if key in response_headers},
    "initialize_body_tail": text[-2000:],
}
session = response_headers.get("mcp-session-id")
if session:
    headers_with_session = dict(headers)
    headers_with_session["Mcp-Session-Id"] = session
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("POST", "/mcp", json.dumps({"jsonrpc":"2.0","method":"notifications/initialized","params":{}}).encode(), headers_with_session)
    initialized = conn.getresponse()
    value["initialized_status"] = initialized.status
    value["initialized_body_tail"] = initialized.read().decode("utf-8", "replace")[-1000:]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("POST", "/mcp", json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}).encode(), headers_with_session)
    tools = conn.getresponse()
    value["tools_status"] = tools.status
    value["tools_body_tail"] = tools.read().decode("utf-8", "replace")[-4000:]
open(out, "w", encoding="utf-8").write(json.dumps(value, indent=2, sort_keys=True))
print(json.dumps({key: value.get(key) for key in ["initialize_status", "initialized_status", "tools_status"]}, indent=2))
PY
}

write_evidence() {
  local install_sha=$1 healthz=$2
  python3 - "$evidence" "$instance" "$port" "$install_sha" "$healthz" "$expected_source_sha" "$tmp_root/${instance}.mcp.json" "$credentials" <<'PY'
import glob, json, os, pathlib, subprocess, sys
out, instance, port, install_sha, healthz, expected, mcp_path, credentials_dir = sys.argv[1:]
container = json.loads(subprocess.check_output(["docker", "inspect", instance], text=True))[0]
labels = {key: value for key, value in (container.get("Config", {}).get("Labels") or {}).items() if key.startswith("com.yxsicd.mcpgit.")}
image = container.get("Config", {}).get("Image") or ""
release_id = labels.get("com.yxsicd.mcpgit.release-id", "")
program_version = labels.get("com.yxsicd.mcpgit.program-version", "")
source_label = labels.get("com.yxsicd.mcpgit.source-sha", "")
identity_match = True
if expected:
    identity_match = (
        source_label == expected
        or release_id == f"git-{expected}"
        or program_version == f"git-{expected}"
        or expected in image
    )
credential_files = []
for path in sorted(glob.glob(os.path.join(credentials_dir, "*"))):
    stat = os.stat(path)
    credential_files.append({"path": path, "mode": oct(stat.st_mode & 0o777), "size": stat.st_size})
repo_list = subprocess.check_output([
    "docker", "run", "--rm", "-v", f"{instance}_data:/data", "--entrypoint", "sh", image,
    "-lc", "find /data/repos -maxdepth 1 -mindepth 1 -type d -exec basename {} \\; | sort",
], text=True).splitlines()
locks = subprocess.check_output([
    "docker", "run", "--rm", "-v", f"{instance}_data:/data", "--entrypoint", "sh", image,
    "-lc", "find /data/repos \\( -path '*/config.lock' -o -path '*/.git/config.lock' \\) -type f -print | sed -n '1,20p' || true",
], text=True).splitlines()
mcp = json.loads(pathlib.Path(mcp_path).read_text(encoding="utf-8"))
def tail(path: str) -> str:
    p = pathlib.Path(path)
    return p.read_text(errors="replace")[-4000:] if p.exists() else ""
value = {
    "schema": "mcpgitrelease/new-agent-public-install-evidence/v1",
    "instance": instance,
    "port": int(port),
    "public_install_sha256": install_sha,
    "container": {
        "id": container["Id"][:12],
        "image": image,
        "state": container.get("State", {}).get("Status"),
        "health": container.get("State", {}).get("Health", {}).get("Status"),
        "labels": labels,
    },
    "healthz_code": int(healthz),
    "credential_files": credential_files,
    "standard_repos": repo_list,
    "remaining_config_locks": locks,
    "mcp_initialize": mcp,
    "checks": {
        "public_installer_fetched": True,
        "fresh_install": True,
        "docker_health": container.get("State", {}).get("Health", {}).get("Status") == "healthy",
        "healthz": int(healthz) == 204,
        "doctor": "Result: healthy" in tail(f"/tmp/{instance}.doctor.log"),
        "credentials_mode_0600": bool(credential_files) and all(item["mode"] == "0o600" for item in credential_files),
        "standard_repos_initialized": set(repo_list) >= {"works", "tablegit", "binarygit", "rootskills", "mcpgitsystem", "safegit", "systemconfig"},
        "no_config_locks": not locks,
        "release_identity_match": identity_match,
        "mcp_initialize": mcp.get("initialize_status") == 200,
        "mcp_tools_list": mcp.get("tools_status") == 200,
    },
    "status_log_tail": tail(f"/tmp/{instance}.status.log"),
    "doctor_log_tail": tail(f"/tmp/{instance}.doctor.log"),
}
pathlib.Path(out).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps({
    "evidence": out,
    "image": image,
    "health": value["container"]["health"],
    "healthz": value["healthz_code"],
    "checks": value["checks"],
}, indent=2))
if not all(value["checks"].values()):
    raise SystemExit(1)
PY
}

cleanup_old
curl -fsSL --retry 3 "$install_url" -o "$installer"
chmod 0755 "$installer"
install_sha=$(python3 - "$installer" <<'PY'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)
echo "new-agent-smoke: fetched public installer sha256=$install_sha"
set +e
MCPGIT_INSTANCE="$instance" MCPGIT_PORT="$port" MCPGIT_BUNDLE_DIR="$bundle" MCPGIT_CREDENTIAL_DIR="$credentials" \
  bash "$installer" --instance "$instance" --port "$port" >"/tmp/${instance}.install.log" 2>&1
install_status=$?
set -e
redact_log <"/tmp/${instance}.install.log" | tail -220
[[ "$install_status" == 0 ]] || exit "$install_status"
wait_healthy
healthz=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$port/healthz" || true)
[[ "$healthz" == 204 ]] || { echo "new-agent-smoke: /healthz returned $healthz" >&2; exit 1; }
"$HOME/.local/bin/mcpgitctl" --instance "$instance" --url "http://127.0.0.1:$port" status >"/tmp/${instance}.status.log"
"$HOME/.local/bin/mcpgitctl" --instance "$instance" --url "http://127.0.0.1:$port" doctor >"/tmp/${instance}.doctor.log"
mcp_probe
if ! write_evidence "$install_sha" "$healthz"; then
  if [[ "$cleanup_on_success" == true ]]; then
    cleanup_sensitive
  fi
  exit 1
fi
if [[ "$cleanup_on_success" == true ]]; then
  cleanup_old
fi
echo "new-agent-smoke: PASS evidence=$evidence"
