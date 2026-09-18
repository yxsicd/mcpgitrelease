---
id: web-component:pptx-presentation
name: pptx-presentation
kind: web-component
description: "Source-driven PPTX projection runtime for browser rendering."
disclosure: on_demand
lifecycle: active
api: "1"
channel: stable
authority: release:mcpgitrelease
metadata:
  manifest: ./0.1.1/manifest.json
  parent-registry: ../catalog.json
---

# pptx-presentation

Thin runtime for source-driven PPTX projections.

## Use

```html
<pptx-presentation src="./deck.js"></pptx-presentation>
```

Projection entry:

```js
export async function buildDeck(PptxGenJS, context) {
  return arrayBuffer;
}
```

Also accepted: `{ bytes: arrayBuffer, ...metadata }`.

## Boundary

The runtime owns execution lifecycle, rendering, navigation and fullscreen.
The projection owns facts, data adapters, templates, module structure, inheritance/composition and provenance.

Read the version manifest referenced by frontmatter for exact artifact/source metadata.
