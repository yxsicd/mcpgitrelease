# Agent composition: MCPGit runtime + PPTX presentation

Use this recipe when an Agent needs a browser page that discovers released
MCPGit Web Components, connects to MCPGit, injects a host-owned client into a
source-driven PPTX projection, and keeps application policy in ordinary
JavaScript.

This is a consumer recipe. It does not add a runtime API, change a component
version, or make one component depend on the other.

## 1. Discover before loading

Start from the public release Skill rather than guessing component URLs:

```text
SKILL.md
  -> web-components/SKILL.md
  -> channels/stable.json
  -> immutable registry
  -> child component SKILL.md
  -> version manifest
  -> immutable tagged artifact
```

Normal consumers follow `stable`. Record the resolved registry, version and
integrity only when exact evidence, reproducibility or rollback matters. Do not
hard-code today's stable component versions into application policy.

## 2. Load both released components

The public loader resolves the mutable control plane and verifies the immutable
component bytes before import:

```js
import { loadComponent } from
  'https://cdn.jsdelivr.net/gh/yxsicd/mcpgitrelease@main/web-components/loader.js';

const runtimeRelease = await loadComponent('mcpgit-runtime');
const presentationRelease = await loadComponent('pptx-presentation');

console.log({
  runtime: runtimeRelease.version,
  presentation: presentationRelease.version,
  registry: runtimeRelease.registry,
});
```

The resolved values are evidence. Application logic should still depend on the
documented API contract, not on a specific current version string.

## 3. Connect one shared MCPGit runtime

For a page hosted with a same-origin MCPGit endpoint:

```js
const runtime = document.createElement('mcpgit-runtime');
document.body.prepend(runtime);

const client = runtime.connect({ endpoint: '/mcp' });
```

When the host already owns an MCP transport, inject its `callTool` function
instead:

```js
const client = runtime.connect({ callTool: hostCallTool });
```

Do not put Basic credentials, Authorization headers, or credential-discovery
logic into a projection or presentation component. The direct browser transport
uses same-origin credentials; an injected transport remains host-owned.

## 4. Inject the client as opaque presentation context

`pptx-presentation` forwards `context` unchanged to
`buildDeck(PptxGenJS, context)`. A host can therefore compose the two released
components without extending either public API:

```js
const presentation = document.querySelector('pptx-presentation');

presentation.context = {
  mcpgit: client,
  tablegitRevision: exactRevision,
};
presentation.src = './deck.js';
```

`context.mcpgit` and `context.tablegitRevision` are conventions owned by this
host/application. They are not new `pptx-presentation` attributes or state
fields.

Assigning a new context does not rebuild the deck. Call
`presentation.refresh()` when host policy requires a rebuild.

## 5. Let the projection use dynamic Skills

The projection can use the generic `McpGitClient` instead of depending on a
fixed browser SDK surface:

```js
export async function buildDeck(PptxGenJS, context) {
  const mcpgit = context?.mcpgit;
  if (!mcpgit) throw new Error('host must provide context.mcpgit');

  const skillCatalog = await mcpgit.skills.list();

  const exact = mcpgit.at({
    tablegit: {
      kind: 'committed',
      revision: context.tablegitRevision,
    },
  });

  const facts = await exact.table.rowsGet({
    repo: 'tablegit',
    path: 'data/tables/example',
    keys: ['example'],
  });

  const pptx = new PptxGenJS();
  // Ordinary application code decides how facts become slides.
  return {
    bytes: await pptx.write({ outputType: 'arraybuffer' }),
    revision: facts.revision,
    provenance: {
      source: 'TableGit',
      revision: facts.revision,
      discoveredSkills: Array.isArray(skillCatalog) ? skillCatalog.length : null,
    },
  };
}
```

The table name, key, projection semantics and visual layout above are examples,
not runtime policy. An Agent should obtain real repositories, paths, revisions
and operation contracts from the owning application and MCPGit Skill discovery;
it must not guess them.

For a capability without a typed convenience facade, use dynamic dispatch:

```js
const result = await mcpgit.call(
  discoveredSkillId,
  discoveredOperation,
  operationArguments,
);
```

`call()` performs `skill_get`, retains the returned Skill version and access
lane, and dispatches through the correct `skill_run_*` runner. This is the
forward-compatible Agent path for newly introduced MCPGit Skills.

## 6. Authority and ownership boundaries

Keep these boundaries explicit:

- `mcpgit-runtime` owns MCP transport, Skill discovery, exact views and generic
  capability mechanics.
- `pptx-presentation` owns projection execution, PPTX bytes, rendering,
  navigation, download and presentation state.
- the host owns authentication, capability injection, persistence and refresh
  policy.
- the projection owns repositories, table schemas, business facts, joins,
  presentation semantics, themes and layout.

The presentation component does not discover privileged objects from ambient
page state. Inject only capabilities that the selected projection is trusted to
receive.

## 7. Acceptance checklist

An Agent may call the composition integrated only when all applicable checks
pass:

1. stable discovery resolves both component ids;
2. immutable integrity verification succeeds for both artifacts;
3. one shared `mcpgit-runtime` client connects successfully;
4. the projection receives the exact same client object through
   `presentation.context`;
5. MCPGit Skill discovery succeeds through that client;
6. exact-revision reads remain exact when the application requires them;
7. `pptx-presentation` emits `ready` only after the projection builds and the
   viewer opens;
8. browser-visible behavior is checked for presentation changes; HTTP 200,
   module import or Promise resolution alone is not visual acceptance.

For exact evidence, retain the stable registry release plus each resolved
component version and integrity digest.

## 8. Failure recovery

- component discovery failure: refresh the mutable `stable` pointer; do not
  invent a version;
- integrity mismatch: stop and do not import the artifact;
- unknown or stale MCPGit Skill: refresh `skills.list()` / `skills.get()`;
- authorization failure: follow the operation's returned authorization and
  recovery guidance; do not move the operation to another runner;
- projection failure: keep it projection-side unless repeated evidence proves a
  generic runtime primitive is missing;
- presentation behavior failure: validate the browser-visible behavior before
  changing a generic component contract.
