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

## Consumer rules

- Agent discovery starts from this Skill and the selected child component Skill.
- Machine resolution follows `channels/stable.json` -> immutable registry -> version manifest.
- Normal consumers should follow `stable`; pin an immutable version only for reproducibility, evidence or rollback.
- Public loader/registry/artifacts are fetched without protected-host credentials.
- Protected same-origin projection/data resources use the hosting origin's authentication; component code must not forward Basic credentials.
- Record immutable tag + integrity when exact evidence matters.
- Do not duplicate component contracts in local consumer repositories; route to the public child Skill instead.

## Components

- [pptx-presentation](./pptx-presentation/SKILL.md)
