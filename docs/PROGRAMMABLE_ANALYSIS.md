# Programmable analysis

This guide describes the programmable analysis interfaces shipped with Service
Client SDK 2.5.0. The runtime selected by [offline-latest.json](../offline-latest.json)
and the independently selected [client-sdk.json](../client-sdk.json) remain
the installation authorities. An already installed instance may be older than
those pointers. Check its live metadata and operation contracts before use.

## Choose the interface and contract

| Surface | Version | What it identifies |
| --- | --- | --- |
| Rust Service SDK and Client crates | 2.5.0 | Application-to-Service request/result types and transport client |
| Rust Guest SDK / Core execution ABI | 2.4.0 | The generated Guest facade and exact Host/Guest execution contract |
| Public programmable-query WIT | 1.7.0 | Portable Guest interfaces shared by Rust and WAsmC |
| Root-Lib | 1.8.0 | The product-owned contract bundle and its artifact closure |

These versions belong to different surfaces. Installing the Service Client SDK
does not install or activate a Guest package, configure a compiler, or upgrade
a server. A Guest contract version is not a WAsmC language release version.
The official WAsmC language release pin remains **v0.0.4**; this release does
not change that pin. Use the exact WIT, ABI, SDK and provider digests admitted
by the instance's build contract. Do not relabel an older artifact to match a
new version; the experimental typed-result contract requires matching builds.

## Discover an existing read-only activation through MCP

Follow the [MCP Agent quick start](MCP_AGENT_QUICKSTART.md) to select the
intended instance and caller context. Use its live `skill_list`, then
`skill_get` for the advertised `executable.build` Skill's
`executable_analyze` operation. Retain the returned Skill version, input
schema, access lane, availability and required context. The operation is
progressively disclosed through the Kernel runners, not an additional stable
top-level MCP tool. If the instance does not advertise it, do not guess a
replacement operation or compiler endpoint.

Obtain an already active analysis activation and its exact committed revision
and Row version through the instance's advertised lifecycle read contract.
Invocation accepts these fences:

```json
{
  "activation_id": "<exact active activation UUID>",
  "activation_revision": "<exact committed revision>",
  "activation_row_version": 7,
  "projection": "metadata"
}
```

The Row version above is illustrative; use the version you actually read.
Execute through the read runner specified by `skill_get`. Repository,
artifact, compiler, credentials, organization and caller authority remain
Host-owned and are not invocation parameters. Activations approving Table
mutation are rejected before execution. Invocation does not author a package,
build source, approve or activate a build, or publish an HTTP route. Follow
the instance's separately advertised lifecycle contracts for those actions.

## Rust Service clients and result projection

Service Client SDK 2.5.0 exposes
`McpGitClient::invoke_executable_analysis(InvokeExecutableAnalysisRequest)`
over Service method `executable.analysis.invoke`. The request has the same
three activation fences plus `ExecutableAnalysisProjection`. Before calling,
check that the connected Service advertises the method and
`executable-analysis-invoke.v1` capability; the server still checks current
caller authority. See [Client integration](CLIENT_INTEGRATION.md) for SDK
installation. Choose package versions from the formal SDK pointer, not from
this guide.

Omitting `projection` selects `metadata`. The response contains the scalar
value, relation column count, row count and output-byte count, exact activation
and artifact identity, and execution counters. `json_projection` is absent
as a value (`null`); metadata mode does not return the relation's cell values.

Set `projection` to `json` only when the caller needs the bounded canonical
`mcpgit.analysis-relation.v1` presentation. The result's `json_projection`
contains a JSON string. Column and row order are retained; null, integers,
finite reals and text use JSON values, while a Blob uses
`{"$blob_hex":"..."}`. Non-finite reals and oversized projections fail closed.
The JSON projection adds serialization work and is not the default result.

Inside an analysis Guest, `relation.finish()` transfers the already-metered,
Host-owned typed Relation into the invocation result. It does not serialize
rows or copy Blob payloads through Guest memory. Rust uses
`Relation::finish()` and `output::finish_analysis(...)`; WAsmC uses the matching
WIT analysis profile. Use the exact profile supplied by the build contract.
Scalar-only output remains a separate profile.

## Agent IR and optimization scope

Agent IR is the Host's internal relational execution machinery. Selected
existing Search/SQL/Relation operations can benefit from Host planning and
execution improvements. There is no new public Guest `agent_plan` function,
WIT import or direct MCP plan tool in this release. Guest authors continue
to use the admitted Search/SQL/Relation interfaces; Rust and WAsmC share the
same Host semantics and capability boundaries.

Transparent Search-to-Count rewriting is deferred. Search admits the selected
rows and their bytes before returning a handle, even when a Guest only counts
or drops the result. A count-only shortcut must preserve row/byte limits,
cumulative budgets, ordering, errors and lifetime semantics before it can
replace that path. This release does not promise an additional
lazy Count speedup or a new Count authoring API.
