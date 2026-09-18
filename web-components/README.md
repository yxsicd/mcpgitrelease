# MCPGit Web Components

Public, versioned browser components distributed from this repository through jsDelivr.

## Upgrade model

Pages follow a small mutable channel pointer. The channel resolves an immutable registry, and each registry entry resolves an immutable component tag.

```text
page -> loader -> channels/stable.json -> registry/<release>.json -> exact component tag -> index.js
```

Typical page:

```html
<script type="module">
  import {loadComponent} from 'https://cdn.jsdelivr.net/gh/yxsicd/mcpgitrelease@main/web-components/loader.js';
  await loadComponent('pptx-presentation');
</script>
<pptx-presentation src="./deck.js"></pptx-presentation>
```

Production component artifacts are immutable. Updating stable only requires changing the channel pointer.
