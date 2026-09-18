---
id: release:mcpgitrelease
name: mcpgitrelease
kind: release-authority
description: "Public release authority and Agent-first discovery root for MCPGit deliverables."
disclosure: progressive
lifecycle: stable
authority: release:mcpgitrelease
metadata:
  skill-index: ./metadata/skills.json
  web-components: ./web-components/catalog.json
---

# mcpgitrelease

Public release authority for MCPGit deliverables.

## Agent entrypoints

- [Web Components](./web-components/SKILL.md)
- [README](./README.md)
- [MCP Agent Quickstart](./docs/MCP_AGENT_QUICKSTART.md)

## Rules

- Immutable tags/releases are artifact authority.
- Mutable channels are pointers only.
- Follow child `SKILL.md` files progressively.
- Use metadata pointers for large machine-readable state instead of expanding frontmatter.
