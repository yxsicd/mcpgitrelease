const RUN_TOOL = Object.freeze({
  read: 'skill_run_read',
  write: 'skill_run_write',
  publish: 'skill_run_publish',
});

const MCP_PROTOCOL_VERSION = '2026-07-28';
const MCP_ACCEPT = 'application/json, text/event-stream';

function modernMcpMeta(clientInfo) {
  return {
    'io.modelcontextprotocol/protocolVersion': MCP_PROTOCOL_VERSION,
    'io.modelcontextprotocol/clientInfo': clientInfo,
    'io.modelcontextprotocol/clientCapabilities': {},
  };
}

function abortError() {
  return new DOMException('The operation was aborted', 'AbortError');
}

function checkAbort(signal) {
  if (signal?.aborted) throw signal.reason ?? abortError();
}

function structuredError(value, context) {
  const raw = value?.error ?? value;
  const message = raw?.message ?? raw?.diagnostic ?? String(raw ?? 'MCPGit operation failed');
  const error = new McpGitError(message, {
    code: raw?.code ?? raw?.kind ?? 'mcpgit_error',
    skillId: context?.skillId ?? null,
    operation: context?.operation ?? null,
    details: raw,
  });
  return error;
}

function unwrap(value, context) {
  if (value?.error) throw structuredError(value, context);
  if (value?.outcome === 'error' || value?.outcome === 'failed') {
    throw structuredError(value, context);
  }
  return value?.result ?? value;
}

function skillFrom(value) {
  return value?.skill ?? value?.result?.skill ?? null;
}

function normalizeViews(views) {
  if (!views || typeof views !== 'object' || Array.isArray(views)) {
    throw new TypeError('at() requires a repo -> exact committed view map');
  }
  const out = {};
  for (const [repo, view] of Object.entries(views)) {
    if (view?.kind !== 'committed' || !view.revision) {
      throw new TypeError('at() requires an exact committed revision for ' + repo);
    }
    out[String(repo)] = Object.freeze({
      ...view,
      kind: 'committed',
      revision: String(view.revision),
    });
  }
  return Object.freeze(out);
}

function normalizeBinaryRef(ref) {
  if (!ref || typeof ref !== 'object') throw new TypeError('binary.get() requires a reference object');
  if (!ref.repo || !ref.sha256) throw new TypeError('binary.get() requires repo and sha256');
  const request = {
    repo: String(ref.repo),
    sha256: String(ref.sha256).toLowerCase(),
  };
  for (const field of ['member_path', 'git_ref', 'revision']) {
    if (ref[field] !== undefined && ref[field] !== null) request[field] = String(ref[field]);
  }
  return request;
}

function stableKey(value) {
  if (Array.isArray(value)) return '[' + value.map(stableKey).join(',') + ']';
  if (value && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + stableKey(value[key])).join(',') + '}';
  }
  return JSON.stringify(value);
}

function forbidAuthorization(init) {
  const headers = new Headers(init?.headers);
  if (headers.has('authorization')) {
    throw new TypeError('mcpgit-runtime does not construct or forward Authorization headers');
  }
  return headers;
}

function parseMcpEnvelope(text) {
  try {
    return JSON.parse(text);
  } catch {
    const data = text
      .split(/\r?\n/)
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trimStart())
      .join('\n');
    if (!data) throw new Error('MCP response was neither JSON nor SSE');
    return JSON.parse(data);
  }
}

function toolPayload(envelope) {
  if (envelope?.error) {
    throw new McpGitError(envelope.error.message ?? 'MCP JSON-RPC error', {
      code: String(envelope.error.code ?? 'mcp_jsonrpc_error'),
      details: envelope.error,
    });
  }
  const result = envelope?.result;
  if (result?.structuredContent !== undefined) return result.structuredContent;
  const text = result?.content?.[0]?.text;
  if (typeof text === 'string') {
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }
  return result;
}

export class McpGitError extends Error {
  constructor(message, { code = 'mcpgit_error', skillId = null, operation = null, details = null } = {}) {
    super(message);
    this.name = 'McpGitError';
    this.code = code;
    this.skillId = skillId;
    this.operation = operation;
    this.details = details;
  }
}

export class McpGitHttpTransport {
  constructor({
    endpoint = '/mcp',
    fetch: fetchImpl = globalThis.fetch?.bind(globalThis),
    baseUrl = globalThis.location?.href ?? 'http://localhost/',
    clientInfo = { name: 'mcpgit-runtime', version: '0.1.1' },
  } = {}) {
    if (typeof fetchImpl !== 'function') throw new TypeError('fetch must be a function');
    this.endpoint = new URL(endpoint, baseUrl).href;
    this.fetch = fetchImpl;
    this.clientInfo = Object.freeze({ ...clientInfo });
    this._nextId = 1;
  }

  async callTool(name, arguments_ = {}, { signal } = {}) {
    checkAbort(signal);
    const id = this._nextId++;
    const body = {
      jsonrpc: '2.0',
      id,
      method: 'tools/call',
      params: {
        name,
        arguments: arguments_,
        _meta: modernMcpMeta(this.clientInfo),
      },
    };
    const response = await this.fetch(this.endpoint, {
      method: 'POST',
      credentials: 'same-origin',
      signal,
      headers: {
        Accept: MCP_ACCEPT,
        'Content-Type': 'application/json',
        'MCP-Protocol-Version': MCP_PROTOCOL_VERSION,
        'Mcp-Method': 'tools/call',
        'Mcp-Name': name,
      },
      body: JSON.stringify(body),
    });
    const text = await response.text();
    let envelope;
    try {
      envelope = parseMcpEnvelope(text);
    } catch (error) {
      throw new McpGitError('Failed to decode MCP response', {
        code: 'mcp_decode_error',
        details: { status: response.status, body: text, cause: String(error) },
      });
    }
    if (!response.ok && !envelope?.error) {
      throw new McpGitError('MCP HTTP request failed', {
        code: 'mcp_http_error',
        details: { status: response.status, envelope },
      });
    }
    return toolPayload(envelope);
  }
}

export class McpGitClient {
  constructor({
    callTool,
    endpoint,
    readBinary,
    fetch: fetchImpl = globalThis.fetch?.bind(globalThis),
    baseUrl = globalThis.location?.href ?? 'http://localhost/',
    clientInfo,
    emit = null,
  } = {}) {
    if (callTool !== undefined && typeof callTool !== 'function') {
      throw new TypeError('callTool must be a function when provided');
    }
    if (readBinary !== undefined && typeof readBinary !== 'function') {
      throw new TypeError('readBinary must be a function when provided');
    }
    if (fetchImpl !== undefined && typeof fetchImpl !== 'function') {
      throw new TypeError('fetch must be a function when provided');
    }
    if (!callTool && !fetchImpl && !readBinary) {
      throw new TypeError('at least one MCPGit transport capability is required');
    }

    this.transport = null;
    if (!callTool && endpoint !== undefined) {
      this.transport = new McpGitHttpTransport({
        endpoint,
        fetch: fetchImpl,
        baseUrl,
        ...(clientInfo ? { clientInfo } : {}),
      });
      callTool = this.transport.callTool.bind(this.transport);
    }

    this._callTool = callTool ?? null;
    this._readBinary = readBinary ?? null;
    this._fetch = fetchImpl ?? null;
    this._baseUrl = String(baseUrl);
    this._emit = typeof emit === 'function' ? emit : null;
    this._contracts = new Map();
    this._binaryCache = new Map();

    this.skills = Object.freeze({
      list: options => this._tool('skill_list', {}, options),
      get: (skillId, operation, options) => this._tool('skill_get', {
        skill_id: skillId,
        ...(operation ? { operation } : {}),
      }, options),
      invalidate: (skillId = null, operation = null) => this.invalidateSkills(skillId, operation),
    });

    this.table = Object.freeze({
      query: (request, options) => this.call('table.query', 'table_query', request, options),
      rowsGet: (request, options) => this.call('table.query', 'table_rows_get', request, options),
      relationQuery: (request, options) => this.call('table.query', 'table_relation_query', request, options),
    });

    this.binary = Object.freeze({
      get: (ref, options) => this._binaryGet(ref, options),
      clearCache: () => this._binaryCache.clear(),
    });

    this.hosted = Object.freeze({
      request: (path, init) => this.request(path, init),
    });
  }

  get baseUrl() {
    return this._baseUrl;
  }

  async _tool(name, args, { signal } = {}) {
    if (!this._callTool) throw new McpGitError('MCP tool transport is unavailable', { code: 'transport_unavailable' });
    checkAbort(signal);
    const started = performance.now?.() ?? Date.now();
    this._emit?.('operation', { phase: 'start', tool: name });
    try {
      const value = await this._callTool(name, args, { signal });
      checkAbort(signal);
      const result = unwrap(value, { operation: name });
      this._emit?.('operation', {
        phase: 'success',
        tool: name,
        durationMs: (performance.now?.() ?? Date.now()) - started,
      });
      return result;
    } catch (error) {
      this._emit?.('error', { tool: name, error });
      throw error;
    }
  }

  async _contract(skillId, operation, options) {
    const key = skillId + ':' + operation;
    let pending = this._contracts.get(key);
    if (!pending) {
      pending = this.skills.get(skillId, operation, options).then(value => {
        const skill = skillFrom(value) ?? value;
        const version = skill?.summary?.skill_version ?? skill?.skill_version;
        const contract = (skill?.operations ?? []).find(item => item?.name === operation);
        const lane = contract?.access_lane;
        if (!version) throw new McpGitError('Skill version is unavailable', {
          code: 'invalid_skill_contract', skillId, operation, details: skill,
        });
        if (!RUN_TOOL[lane]) throw new McpGitError('Operation access lane is unavailable', {
          code: 'invalid_skill_contract', skillId, operation, details: contract,
        });
        return Object.freeze({ skillId, operation, version, lane, runTool: RUN_TOOL[lane] });
      }).catch(error => {
        if (this._contracts.get(key) === pending) this._contracts.delete(key);
        throw error;
      });
      this._contracts.set(key, pending);
    }
    return pending;
  }

  invalidateSkills(skillId = null, operation = null) {
    if (!skillId) {
      this._contracts.clear();
      return;
    }
    if (operation) {
      this._contracts.delete(skillId + ':' + operation);
      return;
    }
    for (const key of this._contracts.keys()) {
      if (key.startsWith(skillId + ':')) this._contracts.delete(key);
    }
  }

  async call(skillId, operation, args = {}, options = {}) {
    const contract = await this._contract(String(skillId), String(operation), options);
    return this._tool(contract.runTool, {
      skill_id: contract.skillId,
      skill_version: contract.version,
      operation: contract.operation,
      arguments: args,
    }, options);
  }

  at(views) {
    return new McpGitView(this, normalizeViews(views));
  }

  async _binaryGet(ref, options = {}) {
    const request = normalizeBinaryRef(ref);
    const key = stableKey(request);
    if (!this._binaryCache.has(key)) {
      const pending = Promise.resolve().then(() => {
        checkAbort(options.signal);
        if (this._readBinary) return this._readBinary(request, options);
        return this.call('binary', 'binary_get', request, options);
      }).catch(error => {
        if (this._binaryCache.get(key) === pending) this._binaryCache.delete(key);
        throw error;
      });
      this._binaryCache.set(key, pending);
    }
    return this._binaryCache.get(key);
  }

  async request(path, init = {}) {
    if (!this._fetch) throw new McpGitError('Hosted fetch transport is unavailable', { code: 'transport_unavailable' });
    checkAbort(init.signal);
    const headers = forbidAuthorization(init);
    const url = new URL(path, this._baseUrl);
    const response = await this._fetch(url, {
      ...init,
      headers,
      credentials: init.credentials ?? 'same-origin',
    });
    return response;
  }
}

export class McpGitView {
  constructor(client, views) {
    this.client = client;
    this.views = views;
    this.table = Object.freeze({
      query: (request, options) => {
        const view = this._viewFor(request.repo);
        return client.table.query({ ...request, view }, options);
      },
      rowsGet: (request, options) => {
        const view = this._viewFor(request.repo);
        return client.table.rowsGet({ ...request, view }, options);
      },
      relationQuery: (request, options) => client.table.relationQuery({
        ...request,
        bindings: (request.bindings ?? []).map(binding => ({
          ...binding,
          revision: this._viewFor(binding.repo).revision,
        })),
      }, options),
    });
    this.binary = client.binary;
    Object.freeze(this);
  }

  _viewFor(repo) {
    const view = this.views[repo];
    if (!view) throw new McpGitError('No exact revision is bound for repo ' + repo, { code: 'view_unbound' });
    return view;
  }

  call(skillId, operation, args, options) {
    return this.client.call(skillId, operation, args, options);
  }

  request(path, init) {
    return this.client.request(path, init);
  }
}


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

