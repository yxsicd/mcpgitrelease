#!/usr/bin/env python3
"""Check a fresh instance through MCP using its private generated credential.

Read-only by default. --write-probe explicitly commits and reads one unique
sentinel in the already-authorized rootskills repository. No ACLs are changed.
"""
from __future__ import annotations

import argparse
import base64
import http.client
import json
import stat
import sys
import urllib.parse
import uuid
from pathlib import Path

KERNEL = {"service_metadata", "person_status", "person_select", "skill_list",
          "skill_get", "skill_run_read", "skill_run_write", "skill_run_publish"}
MAX_RESPONSE = 2 * 1024 * 1024


class ProbeError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ProbeError(message)


def credentials(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "credential must be a regular non-symlink file")
    require(stat.S_IMODE(path.stat().st_mode) == 0o600 and path.stat().st_size <= 8192,
            "credential file must be mode 0600 and bounded")
    values = {}
    for line in path.read_text().splitlines():
        require("=" in line, "invalid generated credential format")
        key, value = line.split("=", 1)
        require(key in {"MCPGIT_BASIC_USERNAME", "MCPGIT_BASIC_VERIFY"} and key not in values and value,
                "invalid generated credential fields")
        values[key] = value
    require(len(values) == 2, "generated credential pair is incomplete")
    return values["MCPGIT_BASIC_USERNAME"], values["MCPGIT_BASIC_VERIFY"]


def endpoint(url):
    value = urllib.parse.urlsplit(url)
    require(value.scheme in {"http", "https"} and value.hostname and not value.username
            and not value.password and not value.query and not value.fragment
            and value.path in {"", "/", "/mcp"} and not any(c.isspace() for c in url),
            "use an HTTP(S) origin or /mcp URL without credentials or query")
    require(value.scheme == "https" or value.hostname in {"127.0.0.1", "localhost", "::1"},
            "plaintext HTTP credentials are restricted to loopback")
    return value


def decode(body):
    events = [line[5:].strip() for line in body.splitlines()
              if line.startswith("data:") and line[5:].strip()]
    value = json.loads(events[-1] if events else body)
    require(isinstance(value, dict), "invalid MCP response object")
    return value


class Client:
    def __init__(self, url, username, password):
        self.url = endpoint(url)
        self.authorization = "Basic " + base64.b64encode((username + ":" + password).encode()).decode()
        self.sequence = 0
        self.session = None

    def rpc(self, method, params, notification=False):
        self.sequence += 1
        body = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            body["id"] = self.sequence
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "Authorization": self.authorization}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        cls = http.client.HTTPSConnection if self.url.scheme == "https" else http.client.HTTPConnection
        connection = cls(self.url.hostname, self.url.port, timeout=20)
        try:
            connection.request("POST", "/mcp", json.dumps(body).encode(), headers)
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE + 1)
            require(response.status in {200, 202, 204}, "MCP HTTP request rejected")
            require(len(raw) <= MAX_RESPONSE, "MCP response exceeds the probe budget")
            self.session = response.getheader("Mcp-Session-Id") or self.session
            if notification and not raw.strip():
                return {}
            document = decode(raw.decode())
            require("error" not in document and "result" in document, "MCP RPC failed")
            return document["result"]
        finally:
            connection.close()

    def call(self, name, arguments=None):
        result = self.rpc("tools/call", {"name": name, "arguments": arguments or {}})
        require(not result.get("isError"), "MCP tool rejected; check identity and scoped permissions")
        value = result.get("structuredContent")
        require(isinstance(value, dict) and value.get("outcome") != "error",
                "MCP tool returned a structured error")
        return value

    def operation(self, skill_id, name, arguments, caller=None):
        contract = self.call("skill_get", {"skill_id": skill_id, "operation": name})["skill"]
        selected = [op for op in contract["operations"] if op["name"] == name]
        require(len(selected) == 1 and selected[0]["access_lane"] in {"read", "write"},
                "operation contract does not match this bounded probe")
        payload = {"skill_id": skill_id, "skill_version": contract["summary"]["skill_version"],
                   "operation": name, "arguments": arguments}
        if caller:
            payload["caller_person_id"] = caller
        result = self.call("skill_run_" + selected[0]["access_lane"], payload)
        require(result.get("outcome") == "executed", "operation was not executed")
        return result["result"]


def probe(url, credential_file, expected_instance_id, write_probe=False):
    expected = str(uuid.UUID(expected_instance_id))
    username, password = credentials(credential_file)
    client = Client(url, username, password)
    client.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                              "clientInfo": {"name": "new-user-onboarding", "version": "1"}})
    require(client.session, "MCP initialize did not return a session")
    client.rpc("notifications/initialized", {}, notification=True)
    tools = client.rpc("tools/list", {})["tools"]
    require(len(tools) == 8 and {item["name"] for item in tools} == KERNEL, "unexpected MCP Kernel")
    metadata = client.call("service_metadata")
    require(metadata.get("instance_id") == expected, "instance identity mismatch")
    identity = client.call("person_status")
    person = identity.get("selected_person") or {}
    require(identity.get("outcome") == "authenticated_person" and person.get("handle") == username
            and person.get("person_id"), "generated credential did not authenticate its intended Person")
    # repo_list needs instance-wide mcp.read; do not widen grants to make it pass.
    repo = client.operation("repo.read", "repo_status", {"repo": "rootskills"})
    require(repo.get("dirty") is False and repo.get("head"), "rootskills is not a clean revisioned repository")
    wasmc = client.operation("executable.build", "wasmc_status", {})
    require(wasmc.get("outcome") == "ready" and wasmc.get("compiler_mode") == "embedded_offline"
            and wasmc.get("offline_sdk_available") is True, "offline WAsmC discovery is not ready")
    report = {"schema": "mcpgitrelease.agent-onboarding.v1", "ok": True,
              "checks": {"eight_kernel_tools": True, "expected_instance": True,
                         "generated_credential_authenticated": True, "scoped_repository_read": True,
                         "offline_wasmc_discovery": True},
              "credential_transport": "http_basic_header", "write_probe_requested": bool(write_probe),
              "permissions_changed": False, "wasmc_tag": wasmc.get("release_tag")}
    if write_probe:
        path = "acceptance/agent-probe-" + str(uuid.uuid4()) + ".txt"
        content = "Explicit fresh-instance Agent acceptance probe.\n"
        client.operation("repo.author", "write_file", {"repo": "rootskills", "path": path,
                         "content": content, "expected_revision": repo["head"],
                         "message": "Verify fresh Agent authoring"}, person["person_id"])
        readback = client.operation("repo.read", "read_file", {"repo": "rootskills", "path": path})
        require(readback.get("content") == content, "committed Agent readback mismatch")
        report["checks"]["committed_write_readback"] = True
        report["probe_path"] = path
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--credential-file", required=True)
    parser.add_argument("--expected-instance-id", required=True)
    parser.add_argument("--write-probe", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(probe(args.url, args.credential_file, args.expected_instance_id, args.write_probe),
                         sort_keys=True, indent=2))
        return 0
    except (ProbeError, OSError, ValueError, KeyError, TypeError, http.client.HTTPException) as error:
        # Do not serialize tool bodies, headers, credential values, or tracebacks.
        message = str(error) if isinstance(error, ProbeError) else type(error).__name__
        print(json.dumps({"ok": False, "error": message, "permissions_changed": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
