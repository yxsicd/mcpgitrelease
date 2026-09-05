# Public new-user qualification

State: complete / merged. Validated implementation:
`db080407a59ec137c884028c49740c903ccaa830`.

A real fresh installation reaches Docker health and the eight-tool MCP kernel.
The generated random systemadmin credential authenticates through HTTP Basic,
but is rejected when copied into MCP basic_username/basic_verify parameters.
Those parameters are a separate entrance-profile mechanism. Also, repo_list
requires mcp.read, which the fresh administrator does not implicitly hold;
scoped rootskills repo_status/read/write are allowed by the existing grant.
Do not grant blanket business access or use shared profile secrets to hide this.

The public guide and installer success output now distinguish those mechanisms.
scripts/agent_onboarding_probe.py uses only the standard library, defaults to
read-only and requires --write-probe for one unique scoped rootskills sentinel.
It verifies the expected organization UUID, generated HTTP login, eight tools,
scoped read, offline WAsmC discovery and optional committed readback. Denied
access stays denied: no profile secrets, additional grants or private source
are needed. Local validation passes 68 tests, including eight loopback probe
tests. The exact candidate script passed read-only, explicit-write and wrong
identity cases against the newly installed WSL instance.

docs/evidence/new-user-wsl-20260905.json records seven real public-installer
scenarios: fresh install, online/offline no-op replay, wrong-volume, occupied
port, wrong-organization rejection and reconstruction after container loss.
The original data volume, identity, configuration, generated credential and
committed MCP sentinel survive. All four layer hashes and three Program
binary hashes match the selected immutable amd64 release. Existing container
IDs remain unchanged. The WSL host needed no Node or gh. The test instance is
retained; no data-volume deletion or cross-version migration was tested.

Named-instance CLI instructions now retain --instance explicitly. Documentation
also warns that a chosen host port is not a loopback-only Docker binding.
Public CI is manual-only so integrating these public docs does not dispatch
Actions. Release pointers, runtime image assembly and access grants are unchanged.
Do not claim this raw-HTTP probe proves SDK conformance or WAsmC compilation.

Source-bound evidence is retained in integration-evidence.json. The exact fetched
workstream is integrated with the public guide and locally validated probe.
The final merge tree must pass scripts/validate.sh before this state is committed.
Fetch the updated public main installer/probe on the same WSL instance next;
that post-integration public replay remains unclaimed at this checkpoint.
