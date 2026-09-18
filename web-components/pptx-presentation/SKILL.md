---
name: pptx-presentation
description: "Render source-driven PPTX projections in the browser while keeping projection internals and fact binding unconstrained."
disclosure: on_demand
lifecycle: active
profile: web-component
metadata:
  component-id: pptx-presentation
  component-api: "1"
  stable-version: "0.1.0"
---

# pptx-presentation

## Purpose

`<pptx-presentation>` is a thin presentation runtime. It loads one projection module, asks it to build a PPTX, and renders the result in-browser.

The runtime does **not** own business facts, data schemas, templates, inheritance, module structure or projection internals.

## Minimal usage

Load through the registry loader:

```js
import { loadComponent } from '../loader.js';
await loadComponent('pptx-presentation');
```

Then:

```html
<pptx-presentation src="./deck.js"></pptx-presentation>
```

Projection contract:

```js
export async function buildDeck(PptxGenJS, context) {
  // Any internal imports, templates, inheritance/composition,
  // fact loading and adapters are allowed.
  return arrayBuffer;
}
```

Also accepted:

```js
return {
  bytes: arrayBuffer,
  revision: 'fact-r42',
  provenance: { source: '...' }
};
```

## Design boundary

The component owns:

- projection execution lifecycle
- rendering
- navigation
- fullscreen fallback
- error surface
- future caching/export hooks

The projection owns:

- canonical fact binding
- data adapters
- template strategy
- theme/layout code
- internal imports
- inheritance/composition
- provenance metadata

## Published artifact

- Version manifest: [0.1.0/manifest.json](./0.1.0/manifest.json)
- Demo: [0.1.0/demo/](./0.1.0/demo/)
- Stable discovery is controlled by the parent Web Components registry, not by this file.

## Source lineage

The source authority is recorded in each version manifest. Public artifacts are release projections of that source revision.
