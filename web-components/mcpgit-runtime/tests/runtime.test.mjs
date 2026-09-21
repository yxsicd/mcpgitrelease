import test from 'node:test';
import assert from 'node:assert/strict';
import { McpGitClient, McpGitError, McpGitRuntimeElement } from '../src/index.js';

function kernelTransport(log, { denied = null } = {}) {
  const lanes = { read_op: 'read', write_op: 'write', publish_op: 'publish', table_query: 'read', table_rows_get: 'read', table_relation_query: 'read', binary_get: 'read' };
  return async (name, args) => {
    log.push({ name, args });
    if (name === 'skill_list') return { skills: [{ skill_id: 'demo' }] };
    if (name === 'skill_get') return { skill: { summary: { skill_version: '2.2.0' }, operations: [{ name: args.operation, access_lane: lanes[args.operation] ?? 'read' }] } };
    if (denied && args.operation === denied) return { error: { code: 'permission_denied', message: 'denied' } };
    if (args.operation === 'table_rows_get') return { result: { revision: args.arguments.view.revision, rows: [{ key: 'k', row: { value: 1 } }] } };
    if (args.operation === 'table_query') return { result: { revision: args.arguments.view.revision, rows: [] } };
    if (args.operation === 'table_relation_query') return { result: { bindings: args.arguments.bindings, rows: [] } };
    if (args.operation === 'binary_get') return { result: { content_base64: 'AQID', object: { sha256: args.arguments.sha256 } } };
    return { result: { laneTool: name, operation: args.operation, arguments: args.arguments } };
  };
}

test('dynamic call discovers operation lane and routes read/write/publish', async () => {
  const log = [];
  const client = new McpGitClient({ callTool: kernelTransport(log), fetch: undefined });
  const read = await client.call('demo', 'read_op', { a: 1 });
  const write = await client.call('demo', 'write_op', { b: 2 });
  const publish = await client.call('demo', 'publish_op', { c: 3 });
  await client.call('demo', 'read_op', { a: 4 });
  assert.equal(read.laneTool, 'skill_run_read');
  assert.equal(write.laneTool, 'skill_run_write');
  assert.equal(publish.laneTool, 'skill_run_publish');
  assert.equal(log.filter(x => x.name === 'skill_get' && x.args.operation === 'read_op').length, 1);
  assert.equal((await client.skills.list()).skills[0].skill_id, 'demo');
});

test('permission errors stay operation errors instead of hiding capabilities', async () => {
  const client = new McpGitClient({ callTool: kernelTransport([], { denied: 'read_op' }), fetch: undefined });
  await assert.rejects(() => client.call('demo', 'read_op', {}), error => error instanceof McpGitError && error.code === 'permission_denied');
  assert.equal(typeof client.call, 'function');
});

test('exact TableGit views snapshot revisions and relation bindings', async () => {
  const client = new McpGitClient({ callTool: kernelTransport([]), fetch: undefined });
  const view = { kind: 'committed', revision: 'R1' };
  const exact = client.at({ tablegit: view });
  view.revision = 'R2';
  const rows = await exact.table.rowsGet({ repo: 'tablegit', path: 'data/tables/facts', keys: ['k'] });
  assert.equal(rows.revision, 'R1');
  const relation = await exact.table.relationQuery({ bindings: [{ alias: 'facts', repo: 'tablegit', path: 'data/tables/facts' }], agent_plan: { schema: 'mcpgit.agent-relation-ir.v1', steps: [] } });
  assert.equal(relation.bindings[0].revision, 'R1');
  assert.throws(() => exact.table.query({ repo: 'other', path: 'data/tables/x' }), /No exact revision is bound/);
});

test('Binary identity is normalized, cached, and supports direct byte readers', async () => {
  const kernelLog = [];
  const kernelClient = new McpGitClient({ callTool: kernelTransport(kernelLog), fetch: undefined });
  const first = await kernelClient.binary.get({ repo: 'binarygit', sha256: 'A'.repeat(64), media_type: 'image/png' });
  const second = await kernelClient.binary.get({ repo: 'binarygit', sha256: 'a'.repeat(64), media_type: 'image/jpeg' });
  assert.deepEqual(second, first);
  const binaryRuns = kernelLog.filter(x => x.name === 'skill_run_read' && x.args.operation === 'binary_get');
  assert.equal(binaryRuns.length, 1);
  assert.deepEqual(binaryRuns[0].args.arguments, { repo: 'binarygit', sha256: 'a'.repeat(64) });
  const directCalls = [];
  const directClient = new McpGitClient({ readBinary: async request => { directCalls.push(request); return { bytes: new Uint8Array([9,8,7]) }; }, fetch: undefined });
  assert.equal(typeof directClient.table.query, 'function');
  await assert.rejects(
    () => directClient.table.query({ repo: 'tablegit', path: 'data/tables/facts' }),
    error => error instanceof McpGitError && error.code === 'transport_unavailable',
  );
  const result = await directClient.binary.get({ repo: 'binarygit', sha256: 'B'.repeat(64), member_path: 'asset.bin', media_type: 'application/octet-stream' });
  assert.deepEqual([...result.bytes], [9,8,7]);
  assert.deepEqual(directCalls[0], { repo: 'binarygit', sha256: 'b'.repeat(64), member_path: 'asset.bin' });
});

test('Hosted request uses same-origin credentials and refuses Authorization construction', async () => {
  const calls = [];
  const client = new McpGitClient({ readBinary: async () => ({ bytes: new Uint8Array() }), baseUrl: 'https://example.test/app/', fetch: async (url, init) => { calls.push({ url: String(url), init }); return new Response('pong', { status: 200 }); } });
  const response = await client.request('/__mcpgit/ping');
  assert.equal(await response.text(), 'pong');
  assert.equal(calls[0].url, 'https://example.test/__mcpgit/ping');
  assert.equal(calls[0].init.credentials, 'same-origin');
  await assert.rejects(() => client.request('/x', { headers: { Authorization: 'secret' } }), /does not construct or forward Authorization/);
});

test('headless runtime shares one client without requiring DOM UI', async () => {
  const runtime = new McpGitRuntimeElement();
  const client = runtime.connect({ callTool: kernelTransport([]), fetch: undefined });
  assert.equal(runtime.client, client);
  assert.equal(await runtime.ready, client);
  assert.equal((await runtime.call('demo', 'read_op', { x: 1 })).operation, 'read_op');
  runtime.disconnect();
  assert.equal(runtime.client, null);
  assert.throws(() => runtime.requireClient(), /not connected/);
});
