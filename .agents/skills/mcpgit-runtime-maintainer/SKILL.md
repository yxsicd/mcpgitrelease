---
id: maintainer:mcpgit-runtime
name: mcpgit-runtime-maintainer
kind: maintainer-skill
description: "Architecture and release discipline for the MCPGit browser programmable runtime."
disclosure: on_demand
lifecycle: active
authority: source:mcpgitrelease
metadata:
  consumer-skill: ../../../web-components/mcpgit-runtime/SKILL.md
  source: ../../../web-components/mcpgit-runtime/src/index.js
  release-indexer: ../../../scripts/index_skills.py
---

# mcpgit-runtime Maintainer Skill

`mcpgit-runtime` is the foundational programmable MCPGit runtime for browser
applications. It is headless and must not become a frozen mirror of today's
page endpoints.

## Stable floor

The dynamic floor is:

`Skill discovery -> operation contract -> access lane -> skill_run_*`.

`call(skill, operation, args)` must continue to reach newly introduced MCPGit
Skills before a hand-written convenience API exists.

The browser-native direct transport follows MCPGit's stable
`mcpgit.application.v7` contract: modern MCP `2026-07-28`, sessionless
`tools/call`, routing headers matching the JSON-RPC body, and the eight-tool
Kernel. Keep the wire transport isolated below `McpGitClient` so protocol
evolution does not leak into application components.

## Layering

- L0: host transports such as `callTool`, same-origin fetch, and optional
  Binary byte readers.
- L1: native MCPGit capabilities discovered from the Skill kernel.
- L2: reusable JavaScript mechanics such as exact views, immutable Binary
  dedupe, cancellation and transaction helpers.
- L3: applications such as pptx-presentation and Agent3D.

Keep application schemas and workflow policy out of L0-L2.

## Evolution

1. Do not duplicate the complete backend schema in JavaScript.
2. Read Skill version and operation lane from `skill_get`.
3. Add typed facades only for repeatedly proven mechanical semantics.
4. Keep `call()` as the compatibility escape hatch.
5. Prefer normal JavaScript composition over configuration DSLs.

Transport diagnostics are part of the reusable mechanism boundary. Preserve
HTTP failure identity before attempting to classify malformed successful MCP
payloads: non-2xx undecodable responses are HTTP errors; only successful
undecodable responses are decode errors.

## TableGit and Binary

Exact revision binding, relation revision injection, immutable Binary identity,
failed-read eviction and large-object transport selection are runtime
mechanics. Table names, row schemas, report periods and asset roles are
application policy.

## Future WebAssembly

JavaScript is the first execution layer, not the final ceiling. Future WASM
guests should consume the same capability substrate rather than reimplement
transport or TableGit semantics. Do not publish a speculative WASM API before
a concrete workload proves the minimum stable ABI.

## Release gate

- Node contract tests pass.
- A real browser verifies one shared runtime instance can serve multiple
  consumers and dynamic MCP operations.
- Consumer Skill covers every manifest method and event.
- Skill index and catalog validation pass.
- Immutable artifact, registry and tag integrity are recorded.
- Commits record Development-Node and Development-Worktree.
