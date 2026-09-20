---
id: web-component:pptx-presentation
name: pptx-presentation
kind: web-component
description: "Source-driven PPTX projection runtime for browser rendering, navigation, export and host-owned state."
disclosure: on_demand
lifecycle: active
api: "1"
channel: stable
authority: release:mcpgitrelease
metadata:
  manifest: ./0.1.8/manifest.json
  parent-registry: ../catalog.json
---

# pptx-presentation

Thin browser runtime for source-driven PPTX projections. Keep the runtime generic: projection code owns business facts, templates and presentation decisions; the component owns execution, rendering and player lifecycle.

This file is the consumer contract for released behavior. It tells a CodeAgent
what it can rely on when using the component; maintainer architecture and
capability-admission rationale are intentionally kept out of this public
contract.

## When to use

Use this component when an Agent or browser page needs to:

- build PPTX bytes from source code and render them in-browser;
- navigate slides with mouse, wheel, keyboard or host code;
- enter fullscreen presentation mode;
- download the already-built PPTX without rebuilding it;
- expose current slide and presentation state to the host;
- follow a centrally managed public component release while keeping projection source local.

## When not to use

Do not use it as:

- a PPTX editor;
- a business-data store or canonical fact authority;
- a template DSL that constrains projection internals;
- a replacement for the projection's own modules, themes, adapters or provenance;
- an implicit persistence layer. The component does not write browser storage.

## Quick start

```html
<pptx-presentation
  src="./deck.js"
  chrome="minimal"
  initial-slide="1">
</pptx-presentation>
```

The component's public custom element is `pptx-presentation`.

## Projection contract

The projection module must export:

```js
export async function buildDeck(PptxGenJS, context) {
  const pptx = new PptxGenJS();
  // Projection internals are unrestricted.
  return await pptx.write({ outputType: 'arraybuffer' });
}
```

A metadata-rich result is also supported:

```js
export async function buildDeck(PptxGenJS, context) {
  const bytes = await buildPptxSomehow(PptxGenJS);

  return {
    bytes,
    title: 'Architecture Review',
    filename: 'architecture-review.pptx',
    revision: 'r428',
    provenance: {
      source: 'TableGit: experiment-results',
      revision: 'r428'
    }
  };
}
```

`bytes` is the only required field of the object form. Unknown metadata is tolerated. Common metadata such as `title`, `filename`, `revision` and `provenance` belongs to the projection, not to the runtime's business model.

### Host-owned context and optional capabilities

The host may assign any JavaScript value to the element's `context` property
before loading or refreshing a projection. The runtime forwards that value
unchanged as the second argument to `buildDeck(runtime, context)`.

```js
const presentation = document.querySelector('pptx-presentation');

presentation.context = {
  capabilities: {
    tablegit: pageTableGit,
    binary: pageBinary
  },
  data: hostOwnedData
};

presentation.src = './deck.js';
```

The object shape above is only a host convention. `pptx-presentation` does
not define a TableGit schema, table locator, row model, query language,
revision policy, cache policy or Binary asset model. A projection may use an
injected capability when present and fall back to ordinary local or
caller-provided data when it is absent.

```js
export async function buildDeck(PptxGenJS, context) {
  const tablegit = context?.capabilities?.tablegit;
  const facts = tablegit
    ? await loadFactsWithApplicationOwnedCode(tablegit)
    : localFallbackFacts;

  return buildPresentation(PptxGenJS, facts);
}
```

`context` is deliberately not an HTML attribute or configuration DSL. The
runtime does not interpret, clone, serialize, persist or merge it into
`getState()`. Assigning a new context does not implicitly rebuild the deck;
the host calls `refresh()` when its own policy requires a rebuild.

Capability injection is explicit. The component does not discover privileged
objects from ambient page state. Because the selected projection module
receives `context`, a host should inject privileged capabilities only when it
trusts that projection source. Omitting `context` remains a complete,
supported way to use the component.

## Ownership boundary

The runtime owns:

- projection execution;
- PPTX byte lifecycle;
- rendering;
- slide navigation;
- fullscreen/player controls;
- download of built bytes;
- controlled slide state;
- serializable presentation state;
- cancellation/load sequencing.

The projection owns:

- canonical facts and data access;
- joins and transformations;
- themes and templates;
- PptxGenJS composition;
- arbitrary imports and module graphs;
- inheritance/composition;
- presentation-specific metadata and provenance.

Thin contract, open projection: do not move projection semantics into the component.

For custom interaction policy, UI, orchestration or workflow, prefer ordinary
host/deck JavaScript composed around the runtime primitives. Component
attributes are declarative conveniences, not a configuration language.

## Attributes

`src`
: Projection module URL.

`chrome="normal|minimal|none"`
: Player chrome. `normal` shows title/meta plus controls, `minimal` hides nonessential meta, and `none` removes component chrome.

`initial-slide="N"`
: 1-based slide requested for first load when no controlled `current-slide` overrides it.

`current-slide="N"`
: 1-based controlled/current slide. External changes drive navigation; internal navigation canonicalizes this attribute to the actual clamped slide.

## Navigation and lifecycle

Slide numbers exposed to humans/attributes are 1-based. `goTo(index)` uses the existing 0-based programmatic index.

Hidden physical slides are excluded from the public navigation set when the
renderer supplies complete hidden-slide metadata. Public `slideCount`,
`current-slide`, `next()`, `previous()` and `goTo(index)` therefore
address visible slides only. If renderer metadata is absent or incomplete, the
component fails open and keeps the physical slide set rather than guessing.

Source change and refresh intentionally have different semantics:

```text
new src
  -> treat as a different deck
  -> resolve current-slide / initial-slide
  -> do not inherit the old deck's current page

refresh()
  -> rebuild the same deck
  -> preserve the current slide by default

refresh({ preserveSlide: false })
  -> rebuild
  -> resolve current-slide / initial-slide again
```

Out-of-range slide requests are clamped. The canonical `current-slide` attribute is updated to the real slide.

## Methods

`refresh(options?)`
: Rebuild the current projection. Defaults to preserving the current slide.

`download(filename?)`
: Download the cached PPTX bytes. This does not rebuild the deck. Projection `filename` or `title` metadata is used when no explicit filename is supplied.

`next()`
: Navigate to the next slide.

`previous()`
: Navigate to the previous slide.

`goTo(index)`
: Navigate by 0-based slide index.

`toggleFullscreen()`
: Enter or leave presentation fullscreen, with CSS fallback where native fullscreen is unavailable.

`getState()`
: Return a serializable presentation state snapshot.

`restoreState(state, options?)`
: Restore a state snapshot. By default it does not replace `src`; pass `{ restoreSource: true }` to explicitly allow source restoration.

## State contract

Current state schema: `pptx-presentation/state-v1`.

```js
const state = presentation.getState();
// {
//   schema: 'pptx-presentation/state-v1',
//   src: './deck.js',
//   slide: 4,
//   chrome: 'minimal',
//   buildRevision: 'r428'
// }

await presentation.restoreState(state);
```

The state is JSON-serializable.

The component deliberately has no built-in persistence. It does not write:

- localStorage;
- sessionStorage;
- IndexedDB;
- URL/query/hash state;
- TableGit or server state.

The host owns persistence policy. A host may persist `statechange.detail.state` anywhere appropriate, or nowhere.

## Events

`ready`
: Projection built and viewer opened. Detail includes `src`, `slideCount`, build metadata and current state.

`slidechange`
: Slide navigation completed. Detail includes both 0-based `index` and 1-based `slide`.

`download`
: A PPTX download was initiated.

`statechange`
: Serializable state changed. Detail contains `reason` and `state`. Current reasons include `ready`, `slide` and `chrome`.

`error`
: Projection import/build or viewer opening failed.

## Presentation controls

Fullscreen controls are overlays rather than layout rows, so hiding them does not resize the slide.

Current presentation behavior includes:

- compact previous/next/download/fullscreen controls;
- automatic control hiding during presentation;
- top-edge pointer wake behavior;
- first pointer action after hidden controls wakes controls without accidental navigation;
- delayed single-click navigation so double-click fullscreen does not also change slide.

These are runtime behavior, not projection-template requirements.

## Authentication boundary

Public loader, registry and immutable component artifacts are public distribution resources and must not receive protected-host Basic credentials.

For public component distribution:

```text
credentials = omit
```

For a protected same-origin projection, authentication belongs to the hosting origin/browser protection space. Component code must not construct, persist or forward Basic Authorization credentials.

Injected capabilities follow the same rule. A TableGit, Binary or other
capability is supplied by the host page already operating in that page's
authentication/authorization context. The presentation component must not
prompt for an additional login, request credentials, manufacture
`Authorization` headers, persist tokens, or turn capability availability
into a prerequisite for opening the component.

Read the parent registry Skill and `auth-policy.json` for the distribution policy.

## Versioning and authority

Normal consumers should follow the stable channel through the public loader/registry.

Use an immutable component tag only when exact pinning is required for evidence, reproduction or rollback.

Authority chain:

```text
stable channel
  -> immutable registry
  -> version manifest
  -> immutable tag
  -> artifact + integrity
```

The version manifest referenced in this Skill frontmatter is the machine-readable exact contract and release evidence for the current stable component.

## Failure and recovery

Projection module cannot import
: Check `src`, same-origin authentication and module syntax. The component emits `error`.

`buildDeck()` throws or returns an invalid value
: Fix the projection. It must return `ArrayBuffer` or `{ bytes: ArrayBuffer, ... }`.

Viewer open/render fails
: Treat as runtime/render compatibility failure; inspect the `error` event rather than silently regenerating different content.

Invalid state passed to `restoreState()`
: The method throws. Do not silently accept a different state schema.

Unknown `chrome`
: Runtime canonicalizes to `normal`.

Out-of-range slide
: Runtime clamps and canonicalizes `current-slide`.

Public artifact integrity mismatch
: Fail closed. Do not import unverified bytes.

## Agent integration rule

Prefer native PptxGenJS composition in the projection and ordinary JavaScript
for host policy. Use the component's small imperative API and events where a
stable runtime boundary is useful. Do not invent a thick helper/configuration
DSL unless a missing runtime primitive has been demonstrated.

Use the component for reality-facing primitives and lifecycle; let capable Agents retain freedom over slide design.
