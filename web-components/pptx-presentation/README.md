# pptx-presentation

First MCPGit public Web Component release candidate.

Contract:

```js
export async function buildDeck(PptxGenJS, context) {
  // Internal imports, templates, inheritance/composition and data loading are unrestricted.
  return arrayBuffer; // or { bytes: arrayBuffer, ...metadata }
}
```

The component owns projection execution lifecycle and rendering. The projection module owns facts, data adapters, templates and its internal module graph.
