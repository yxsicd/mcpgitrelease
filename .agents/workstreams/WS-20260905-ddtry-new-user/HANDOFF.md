# Public new-user qualification

State: started / not-ready.

A real fresh installation reaches Docker health and the eight-tool MCP kernel.
The generated random systemadmin credential authenticates through HTTP Basic,
but is rejected when copied into MCP basic_username/basic_verify parameters.
Those parameters are a separate entrance-profile mechanism. Also, repo_list
requires mcp.read, which the fresh administrator does not implicitly hold;
scoped rootskills repo_status/read/write are allowed by the existing grant.
Do not grant blanket business access or use shared profile secrets to hide this.

Implement accurate onboarding guidance and a standard-library public probe.
Default to read-only; a sentinel write must require a separate explicit flag.
No credentials or host paths belong in public reports. Preserve binary assets,
runtime policy and pointers. Validate locally and disable the public CI push
trigger before integration so publishing this fix does not run Actions.
