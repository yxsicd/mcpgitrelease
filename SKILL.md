---
name: mcpgitrelease
description: "Public release authority and Agent-first discovery root for MCPGit runtime artifacts, SDKs, deployment assets, and Web Components."
disclosure: progressive
lifecycle: stable
profile: release-authority
---

# mcpgitrelease

This repository is the public release authority for MCPGit deliverables.

## Agent entrypoints

- [Web Components](./web-components/SKILL.md) — browser components distributed through jsDelivr.
- [README](./README.md) — human-oriented release and installation documentation.
- [MCP Agent Quickstart](./docs/MCP_AGENT_QUICKSTART.md) — MCP client discovery and usage.

## Rules

- Treat immutable tags/releases as published artifact authority.
- Treat mutable channels as pointers only; resolve them to immutable artifacts before execution.
- Follow child `SKILL.md` files for progressive disclosure instead of scanning the whole repository.
- Do not infer source authority from release artifacts; use each artifact's source revision metadata.
