import { McpGitClient, McpGitError, McpGitView } from './core.js';

const HTMLElementBase = globalThis.HTMLElement ?? class {};

export class McpGitRuntimeElement extends HTMLElementBase {
  constructor() {
    super();
    this._client = null;
    this._readyResolve = null;
    this.ready = new Promise(resolve => {
      this._readyResolve = resolve;
    });
  }

  get client() {
    return this._client;
  }

  connect(options = {}) {
    const previous = this._client;
    const client = options instanceof McpGitClient
      ? options
      : new McpGitClient({
          ...options,
          emit: (type, detail) => {
            options.emit?.(type, detail);
            this.dispatchEvent?.(new CustomEvent(type, { detail }));
          },
        });
    this._client = client;
    if (this._readyResolve) {
      this._readyResolve(client);
      this._readyResolve = null;
    }
    this.dispatchEvent?.(new CustomEvent('clientchange', { detail: { client, previous } }));
    this.dispatchEvent?.(new CustomEvent('ready', { detail: { client } }));
    return client;
  }

  disconnect() {
    const previous = this._client;
    this._client = null;
    this.dispatchEvent?.(new CustomEvent('clientchange', { detail: { client: null, previous } }));
  }

  requireClient() {
    if (!this._client) throw new McpGitError('mcpgit-runtime is not connected', { code: 'runtime_unconfigured' });
    return this._client;
  }

  call(skillId, operation, args, options) {
    return this.requireClient().call(skillId, operation, args, options);
  }

  at(views) {
    return this.requireClient().at(views);
  }

  request(path, init) {
    return this.requireClient().request(path, init);
  }
}

if (globalThis.customElements && !globalThis.customElements.get('mcpgit-runtime')) {
  globalThis.customElements.define('mcpgit-runtime', McpGitRuntimeElement);
}

export { McpGitClient, McpGitError, McpGitView };
