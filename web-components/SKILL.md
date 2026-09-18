---
id: registry:web-components
name: mcpgitrelease-web-components
kind: skill-registry
description: "Registry and distribution surface for public MCPGit browser Web Components."
disclosure: progressive
lifecycle: active
api: "1"
authority: release:mcpgitrelease
metadata:
  catalog: ./catalog.json
  channel: ./channels/stable.json
  registry-schema: ./registry.schema.json
  auth-policy: ./auth-policy.json
---

# MCPGit Web Components

Agent-first registry for browser components.

## Discovery

1. Read `channels/stable.json`.
2. Resolve its immutable registry document.
3. Select a component id.
4. Read that component's `SKILL.md`.
5. Load the exact artifact only after resolving integrity metadata.

## Runtime

[loader.js](./loader.js) resolves channel -> registry -> immutable artifact and performs SHA-256/SRI verification before Blob import.

## Components

- [pptx-presentation](./pptx-presentation/SKILL.md)
