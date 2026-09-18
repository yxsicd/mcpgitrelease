---
name: mcpgitrelease-web-components
description: "Discover, load, publish, promote, and roll back MCPGit browser Web Components."
disclosure: progressive
lifecycle: active
profile: web-components-registry
---

# MCPGit Web Components

This directory is the Agent-first registry and distribution surface for public browser components.

## Discovery

1. Read [channels/stable.json](./channels/stable.json) for the mutable stable pointer.
2. Resolve its `registry` field to an immutable registry document under [registry/](./registry/).
3. Select a component by id.
4. Follow the exact immutable component entry URL and integrity value from that registry item.
5. Read the component's own `SKILL.md` before integrating it.

## Runtime loader

- [loader.js](./loader.js) resolves channel -> registry -> immutable artifact.
- The loader fetches component bytes, verifies SHA-256/SRI, then imports from a Blob URL for CSP-restricted hosts.
- Pages should follow a channel or compatibility policy; artifacts remain immutable.

## Available components

- [pptx-presentation](./pptx-presentation/SKILL.md) — presentation projection runtime.

## Publishing model

```text
source authority
  -> build/test
  -> immutable component version
  -> immutable registry
  -> mutable channel pointer
  -> consumer loader
```

A component directory owns its own usage contract, build contract, manifest and examples.
