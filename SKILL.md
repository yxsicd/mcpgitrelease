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
  agent-composition: ./web-components/AGENT_COMPOSITION.md
---

# mcpgitrelease

Public release authority for MCPGit deliverables.

## Agent entrypoints

- [Web Components](./web-components/SKILL.md)
- [Web Component Agent Composition](./web-components/AGENT_COMPOSITION.md)
- [README](./README.md)
- [MCP Agent Quickstart](./docs/MCP_AGENT_QUICKSTART.md)

## Rules

- Immutable tags/releases are artifact authority.
- Mutable channels are pointers only.
- Offline Program promotion is ordered: publish immutable assets, select them in
  `dev-latest.json`, copy the exact selection to `main-latest.json`, then explicitly
  promote that exact selection to the production compatibility pointer
  `offline-latest.json`. Default instances follow production; dev/main movement
  alone must not activate them.
- Follow child `SKILL.md` files progressively.
- Use metadata pointers for large machine-readable state instead of expanding frontmatter.
