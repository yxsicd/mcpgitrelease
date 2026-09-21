---
id: web-component:mcpgit-runtime
name: mcpgit-runtime
kind: web-component
description: "Headless MCPGit browser application runtime for dynamic Skill discovery and programmable capability composition."
disclosure: on_demand
lifecycle: active
api: "1"
channel: stable
authority: release:mcpgitrelease
metadata:
  manifest: ./0.1.0/manifest.json
  parent-registry: ../catalog.json
---

# mcpgit-runtime

`mcpgit-runtime` is a headless browser runtime. The reusable JavaScript core is
`McpGitClient`; the custom element is only a DOM lifecycle host.

## Dynamic programming

`call(skillId, operation, arguments, options?)` discovers the current Skill
contract and dispatches through the operation's declared access lane.
New MCPGit Skills remain reachable through `call()` without waiting for a new
typed facade.

Discovery helpers are `skills.list()`, `skills.get()` and
`skills.invalidate()`.

## Shared runtime

`connect(options)` installs one client for the page. Other Web Components can
share `runtime.client`. `disconnect()` detaches it. `runtime.ready` resolves
to the first connected client.

The element proxies `call()`, `at()` and `request()`.

Events: `ready`, `clientchange`, `operation`, `error`.

## TableGit

Typed read facades are `table.query()`, `table.rowsGet()` and
`table.relationQuery()`. Use `at(views)` to snapshot exact committed revisions.
Other TableGit operations remain available through `call()`.

## Binary

`binary.get()` normalizes immutable object identity and deduplicates repeated
reads. A host may provide a direct Binary byte reader behind the same method.
`binary.clearCache()` clears memoized objects.

## Hosted

`request(path, init?)` and `hosted.request()` expose generic same-origin Hosted
requests so future page endpoints do not require a new SDK method.

## Errors and cancellation

Calls accept an optional AbortSignal. Structured failures surface as
`McpGitError` while preserving original details.

## Composition boundary

The runtime owns reusable MCPGit mechanics. Product schemas, report semantics,
visual layout, workflow policy and application-specific locators remain normal
JavaScript.

JavaScript is the initial programmable layer. The capability model remains
transport-neutral so future WebAssembly execution can share the same MCPGit
authority model.
