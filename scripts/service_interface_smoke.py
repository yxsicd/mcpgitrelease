#!/usr/bin/env python3
"""Black-box HTTP + MCP + Website Skills smoke for an installed MCPGit."""

from __future__ import annotations
import argparse, json, pathlib, urllib.error, urllib.parse, urllib.request

MCP_VERSION = "2026-07-28"

def request(url: str, *, payload: dict | None = None, headers: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()

def get_text(url: str, expected: int = 200) -> str:
    status, _, body = request(url)
    if status != expected:
        raise RuntimeError(f"GET {url} returned HTTP {status}: {body[:300]!r}")
    return body.decode()

def mcp_call(url: str, method: str, name: str | None = None) -> dict:
    params = {"_meta": {"io.modelcontextprotocol/protocolVersion": MCP_VERSION,
                        "io.modelcontextprotocol/clientCapabilities": {}}}
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": MCP_VERSION, "Mcp-Method": method}
    if name:
        params.update({"name": name, "arguments": {}})
        headers["Mcp-Name"] = name
    status, _, body = request(url, payload={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, headers=headers)
    if status != 200:
        raise RuntimeError(f"MCP {method} returned HTTP {status}: {body[:500]!r}")
    response = json.loads(body)
    if "error" in response:
        raise RuntimeError(f"MCP {method} returned {response['error']}")
    return response["result"]

def discover(root_url: str) -> tuple[str, dict]:
    skill = get_text(root_url).replace("\r\n", "\n")
    if not skill.startswith("---\n") or "\n---\n" not in skill[4:]:
        raise RuntimeError("root Skill has no YAML frontmatter")
    metadata, active = {}, False
    for line in skill[4:].split("\n---\n", 1)[0].splitlines():
        if line == "metadata:":
            active = True
        elif active and line.startswith("  ") and ":" in line:
            key, value = line.strip().split(":", 1)
            metadata[key] = value.strip().strip('"')
        elif active and line and not line.startswith("  "):
            active = False
    if metadata.get("service-discovery-version") != "1" or not metadata.get("service-manifest"):
        raise RuntimeError("unsupported or incomplete service discovery metadata")
    manifest_url = urllib.parse.urljoin(root_url, metadata["service-manifest"])
    if urllib.parse.urlsplit(manifest_url).netloc != urllib.parse.urlsplit(root_url).netloc:
        raise RuntimeError("service manifest escaped the discovery origin")
    descriptor = json.loads(get_text(manifest_url))
    if descriptor.get("schema") != "mcpgit.service-interfaces.v1" or descriptor.get("urlResolution") != "document-relative":
        raise RuntimeError("unsupported service descriptor")
    return manifest_url, descriptor

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-source-revision", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    expected = args.expected_source_revision
    if len(expected) != 40 or any(char not in "0123456789abcdef" for char in expected):
        raise SystemExit("--expected-source-revision must be 40 lowercase hex characters")
    base = args.base_url.rstrip("/") + "/"
    manifest_url, descriptor = discover(urllib.parse.urljoin(base, "SKILL.md"))
    if set(descriptor.get("surfaces", {})) != {"http", "mcp", "websiteSkills"}:
        raise RuntimeError("descriptor does not expose exactly three service surfaces")
    if descriptor["service"].get("softwareRevision") != expected:
        raise RuntimeError("installed source revision differs from release pointer")
    if len(descriptor.get("protocols", [])) != 6:
        raise RuntimeError("descriptor does not enumerate six external protocols")
    for relative in ("skills.json", "protocols.json", "SERVICE_INTERFACE_PROFILE.md", "http/SKILL.md",
                     "mcp/SKILL.md", "sdk/wasmc/SKILL.md", "sdk/rust/SKILL.md", "sdk/rust/README.md",
                     "sdk/rust/onboarding.rs", "sdk/rust/CLIENT_SDK_RELEASE.md"):
        get_text(urllib.parse.urljoin(manifest_url, relative))
    if request(urllib.parse.urljoin(manifest_url, "protocols/unknown/SKILL.md"))[0] != 404:
        raise RuntimeError("unknown protocol Skill did not return 404")
    if request(urllib.parse.urljoin(manifest_url, descriptor["surfaces"]["http"]["health"]))[0] != 204:
        raise RuntimeError("discovered health endpoint did not return 204")
    mcp_url = urllib.parse.urljoin(manifest_url, descriptor["surfaces"]["mcp"]["endpoint"])
    tools = mcp_call(mcp_url, "tools/list")["tools"]
    metadata = mcp_call(mcp_url, "tools/call", "service_metadata")
    if len(tools) != 8 or len({tool["name"] for tool in tools}) != 8:
        raise RuntimeError("MCP Kernel does not expose eight unique tools")
    if (metadata.get("structuredContent") or {}).get("application_contract") != "mcpgit.application.v7":
        raise RuntimeError("application contract changed")
    report = {"schema": "mcpgitrelease.service-interface-smoke.v1", "ok": True,
              "sourceRevision": expected, "target": "deployed-service",
              "surfaces": ["http", "mcp", "websiteSkills"], "mcpTools": len(tools),
              "protocols": len(descriptor["protocols"]), "businessMutationsInvoked": False}
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
