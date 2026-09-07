# Binary release deployment smoke

Source-ready on `work/ws-20260907-service-interface-smoke` from release-repo
main `02006cc238570677b70b226a398cc1a820dd93aa`.

The workflow triggers manually or when `offline-latest.json` changes on main.
It runs no Cargo build. It installs the promoted package with the existing
new-Agent smoke, keeps the disposable instance long enough to begin at public
`SKILL.md`, verifies HTTP/MCP/Website Skills and exact source identity, uploads
sanitized JSON evidence, then removes the exact named container, volume,
bundle, credentials and instance config on every outcome.

Local validation passed 95 release-repository tests. The client-only probe
also passed against an actual MCPGit process with three surfaces, eight Kernel
tools, six protocols, and zero business mutations. A hosted run must wait for
an `offline-latest.json` release that contains the new Website interface.
