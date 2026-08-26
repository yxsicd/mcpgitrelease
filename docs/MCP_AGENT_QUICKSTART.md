# MCPGit MCP Agent quick start

Use this path when an Agent needs to work with an existing MCPGit instance.
MCP is the Agent-oriented, progressively disclosed interface over the same
Service authority; the Rust Service SDK and instance deployment are separate
paths.

## 1. Connect and discover

Connect a standard MCP client to the instance's advertised `mcp_url`, normally
`https://<host>/mcp`. Let the client perform MCP initialization. The public
surface contains only these eight stable Kernel tools:

```text
service_metadata  person_status  person_select  skill_list
skill_get         skill_run_read skill_run_write skill_run_publish
```

Do not treat operation names returned inside a Skill as additional top-level
tools. Do not cache a Skill registry across instances or releases.

Call `service_metadata` first to confirm the intended instance and advertised
capabilities. Identity fields may be absent: in that case report that the
service is reachable but the exact instance is not independently confirmed; if
strong instance identity matters, stop and obtain the expected identity from
the operator.

Defer `person_status` until the chosen operation's `required_context` or an
authorization error requires caller identity. If the task prompt specifies a
Person, select that exact existing identity. A read-only onboarding must not
create a Person merely because creation is the preferred action. Retain a
selected `person_id` and pass it as `caller_person_id` where required.

For raw HTTP diagnostics when no MCP client library is available, initialize a
legacy Streamable HTTP session and retain the response header:

```text
POST /mcp
Accept: application/json, text/event-stream
Content-Type: application/json

{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
  "protocolVersion":"2025-11-25","capabilities":{},
  "clientInfo":{"name":"diagnostic","version":"1"}}}
```

Send `notifications/initialized`, then later POST requests with the returned
`Mcp-Session-Id`. SSE consumers ignore empty heartbeat frames and decode the
JSON-RPC object from non-empty `data:` fields. Prefer a standard MCP client for
normal Agent use.

The first Kernel call uses the same POST headers plus the session id:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{
  "name":"skill_list","arguments":{}}}
```

For a successful tool call, prefer `result.structuredContent`; `result.content`
is the compatibility text representation. `skill_get` returns its contract
directly there; only a `skill_run_*` runner adds one stable envelope, with the
operation value under `result.structuredContent.result`.

## 2. Disclose one operation

Call `skill_list`. It returns short Skill summaries and operation names, not
every operation schema. Choose one Skill and one operation, then call:

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{
  "name":"skill_get","arguments":{
    "skill_id":"repo.read","operation":"repo_list"
  }
}}
```

If the repository id or path is unknown, first scope and run
`repo.read/repo_list` or `repo.read/list_files`; do not guess a template repo id
or assume `README.md` exists.

Retain the returned `skill_version`, strict `input_schema`, `access_lane`, and
recovery guidance. Request `include_output_schema: true` only with one exact
operation and only when code needs to compose the returned value.

For `instance_dependent` Skills, inspect `instance_state`. Run the declared
`availability_probe` when state is `configured`; stop that path when it is
`unconfigured` or `unavailable`. Never invent a Search index path, compiler
endpoint, route repository, repository id, field name, or revision.

## 3. Execute through the declared lane

Use exactly one runner selected by `access_lane`:

- `read` -> `skill_run_read`
- `write` -> `skill_run_write`
- `publish` -> `skill_run_publish`

The runner envelope is stable while `arguments` is the strict schema disclosed
for the selected operation:

```json
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{
  "name":"skill_run_read","arguments":{
    "skill_id":"repo.read",
    "skill_version":"<returned version>",
    "operation":"repo_list",
    "arguments":{}
  }
}}
```

Use the returned repository id to disclose and run `list_files`, then disclose
and run `read_file` with an exact returned path. Each runner value is at
`result.structuredContent.result`.

Refresh `skill_list` and `skill_get` after an unknown Skill, stale contract, or
unsupported operation. Do not move an operation to another runner to bypass a
rejection. For writes, retain exact revision and row-version fences; after an
uncertain publish outcome, read status before considering a retry.

## Large content, tables, and search

Use the `content` Skill for large values. Keep its returned content reference,
version, byte range, and continuation and perform bounded reads; do not load a
whole large field merely to search it.

Use `table.query` for exact TableGit rows, filters, ordering, and projections.
Use the `search` Skill only when its instance state and `search_overview` probe
succeed. Search produces candidates from an external derivative; inspect the
selected candidate or use an authoritative content reference for the full
value. Search never replaces TableGit as the source of truth.

## Authentication and errors

Pass MCP parameter Basic only when the user or trusted operator supplies both
values for this instance. Never derive credentials from metadata, defaults, or
prose. Repeat `basic_username` and `basic_verify` as top-level arguments on
every relevant tool call. They are not HTTP Authorization fields, are
revalidated each time, and must never be logged, returned, or persisted by the
Agent. Other deployed authentication modes remain transport configuration.

Tool failures include `structuredContent.error` with `code`, `message`,
`retryable`, `source`, and `action`. Follow `action`; retry only when
`retryable` is true and the operation's recovery rules still permit it.

## Modern sessionless HTTP

A client that advertises MCP `2026-07-28` may use sessionless discovery and
Kernel calls. Each request repeats the negotiated protocol version and client
metadata, sets `Mcp-Method`, sets `Mcp-Name` for `tools/call`, accepts both JSON
and event streams, and sends no `Mcp-Session-Id`. Use this only when
`server/discover` advertises the version; otherwise use the normal initialized
MCP session managed by the client library.

The smallest discovery body is a JSON-RPC `server/discover` request whose
`params._meta` supplies `io.modelcontextprotocol/protocolVersion`,
`io.modelcontextprotocol/clientInfo`, and
`io.modelcontextprotocol/clientCapabilities`. Set `Mcp-Method` to
`server/discover`. For a later `tools/call`, set it to `tools/call`, add
`Mcp-Name` with one of the eight Kernel names, and repeat the same `_meta`.
