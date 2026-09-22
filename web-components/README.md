# MCPGit Web Components

Public, versioned browser components distributed from this repository through jsDelivr.

## Upgrade model

Pages follow a small mutable channel pointer. The channel resolves an immutable registry, and each registry entry resolves an immutable component tag.

```text
page -> loader -> channels/stable.json -> registry/<release>.json -> exact component tag -> index.js
```

The mutable channel pointer is control-plane state and is read from the
repository authority rather than a branch-cached artifact CDN. Immutable
component bytes still come from exact tags through jsDelivr and are verified
with SHA-256/SRI before import.

Typical page:

```html
<script type="module">
  import {loadComponent} from 'https://cdn.jsdelivr.net/gh/yxsicd/mcpgitrelease@main/web-components/loader.js';
  await loadComponent('pptx-presentation');
</script>
<pptx-presentation src="./deck.js"></pptx-presentation>
```

Production component artifacts are immutable. Updating stable only requires changing the channel pointer.
