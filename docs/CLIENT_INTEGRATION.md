# MCPGit Client Onboarding (two modes)

This document is the authoritative integration runbook for a new Rust client.
The public mirror in `yxsicd/mcpgitrelease/docs/CLIENT_INTEGRATION.md` is the
Agent-facing copy; keep both in sync when this contract changes.

An Agent must first classify the task:

```text
I already have an MCPGit instance -> Mode 1: Client SDK connects to it
I need my own brand-new instance  -> Mode 2: deploy instance, then Mode 1
```

Both modes depend only on immutable bytes published to GitHub
(`yxsicd/mcpgitrelease`). Download and installation are independent: download
first, install offline later. The SDK is not published to crates.io; the two
`mcpgit-service-*` crates always come from the GitHub SDK Release.

## Shared: recommended SDK pointer

```sh
curl -fsSL https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/client-sdk.json
```

`client-sdk.json` is the atomic authority for the recommended
`mcpgit-client-sdk-git-<source-sha>` Release. Read the tag, asset URLs, byte
counts, and SHA-256 digests from it; never trust README text or GitHub
"Latest".

Download the recommended Release assets (two `.crate` files and the offline
registry bundle) and verify every SHA-256 against the pointer before use.

## Mode 1: connect to an existing instance

1. Configure the client repository with the SDK bundle:

   ```sh
   tar -xzf mcpgit-client-sdk-git-<source-sha>.tar.gz
   cd mcpgit-client-sdk-git-<source-sha>
   ./configure-project.sh /absolute/path/to/client-repository
   ```

2. Declare the dependency (and, in bundle mode, the runtime crate too):

   ```toml
   [dependencies]
   mcpgit-service-client = { version = "=2.0.0", registry = "mcpgit-sdk" }
   # Required for async clients in offline-bundle mode: the runtime crate must
   # come from the same registry, otherwise cargo compiles two independent
   # tokio instances and the SDK reactor rejects the client runtime.
   tokio = { version = "1", features = ["macros", "rt-multi-thread"], registry = "mcpgit-sdk" }
   ```

3. Connect and verify:

   ```sh
   cargo build --offline
   cargo run --example onboarding -- ws://<host>:8001/__mcpgit/service-ws
   ```

   Use `wss://` for TLS/routed hosts. Supply `Authorization` only when the
   instance requires it. The URL Host selects the configured default
   organization; a non-default organization uses the canonical
   `<service>-o<short-hash>` first label.

4. Integration is complete when the example prints `mcpgit.service.v2`
   metadata, lists repositories, and reads one file.

## Mode 2: create a brand-new instance, then connect

1. Create a fresh named data volume and record it as the instance's exclusive
   `/data` source:

   ```sh
   docker volume create mcpgit-<instance>-data
   ```

2. Deploy the instance with the public runtime channel (or the exact
   source-bound `mcpgit-git-<sha>` offline Release when a specific source is
   required):

   ```sh
   curl -fsSL \
     https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/deploy/mcpgit-fetch.sh \
     | bash -s -- main ./mcpgit-bundle
   ./mcpgit-bundle/deploy/mcpgit-toolchain-init.sh
   ./mcpgit-bundle/deploy/mcpgit-deploy.sh \
     --bundle ./mcpgit-bundle \
     --instance mcpgit-<instance> \
     --data-source mcpgit-<instance>-data \
     --runtime-env ./mcpgit-bundle/mcpgit-runtime.env \
     --netrc /absolute/path/to/netrc
   ```

   A new instance requires a runtime env that names its own repositories,
   organization/route, and SystemConfig. Never reuse another instance's
   SystemConfig volume or identity.

3. Wait until the new container is `healthy` with restart count zero, then run
   Mode 1 against its Service endpoint.

4. Keep the new data volume for the instance lifetime. Do not delete it as
   part of upgrades or rollbacks.

## Mode 2 offline (fetch on A, install on B)

Deployment is split into fetch and install so an online machine (A) downloads
everything once and an offline machine (B) installs without any network
access. The bundle is self-contained: manifest, three release layers, the
standard seven-repository instance templates (secrets-free), the manifest
parser, the built-in auth bootstrap script, and the offline runtime
Dockerfile. Templates ship as plain directories (no `.git`); the installer
initializes each as a fresh Git repository in the data volume, and remotes
are configured later by the operator (offline-first, GitHub optional).

```sh
# Machine A (online): download and verify one immutable bundle
./deploy/novice-fetch.sh <release-tag> ./bundle
# copy ./bundle to machine B (USB/SCP), then:

# Machine B (offline): assemble the runtime image, provision SystemConfig
# (repositories + built-in systemadmin/guest/builder persons), start the
# instance, and wait for health
./deploy/novice-install.sh --bundle ./bundle --instance mcpgit-demo \
  --port 8001
```

The same installer adapts to updates: when the instance container and data
volume already exist it runs in update mode, preserving the volume and
SystemConfig, rebuilding only the offline runtime image (Docker layer cache
means only the changed program layer is re-copied when the program version
changed), replacing the container, and waiting for health. In the common case
only the `mcpgit` program layer changed between releases, so a re-fetch is
incremental (unchanged layers are cached by SHA-256) and the update is a
fast image rebuild plus container swap.

The seven template repositories (`works`, `rootskills`, `mcpgitsystem`,
`safegit`, `systemconfig`, `tablegit`, `binarygit`) live in
`deploy/instance-templates` and carry only READMEs plus standard skeleton
files (works validation entry, rootskills skillsgit layout, mcpgitsystem
docs/release policy). `rootskills` ships the standard governance skill
(`mst-context-reset-checkpoint`, commit implies push with continuity trailers)
and `.agents/git-policy.yaml` so agents get the skillsgit v2 contract
out of the box. `safegit` is initialized by SafeGit at first start; SystemConfig
tables are provisioned by the installer.

### One-command install (copy-paste, defaults work as-is)

```sh
curl -fsSL https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/deploy/novice-install.sh | sh -s --
```

This resolves the latest offline release via
`offline-latest.json`, downloads the four layers (SHA-256 verified, cached
across runs), assembles the runtime image, starts `mcpgit` on port 8001,
initializes SafeGit in novice mode, and prints a real connection:
`http://127.0.0.1:8001`, login `systemadmin`/`change-me`, and the SkillsTable
`table.initialize` hint.

Everything can be customized with environment variables set before the
command; defaults work without any of them:

| Variable | Default | Change |
| --- | --- | --- |
| `MCPGIT_INSTANCE` | `mcpgit` | 建议改：每个环境唯一，如 `mcpgit-demo` |
| `MCPGIT_PORT` | `8001` | 可改：端口冲突时 |
| `MCPGIT_DATA_VOLUME` | `<instance>_data` | 建议改：正式环境独立命名 |
| `MCPGIT_ZONE` | `blue` | 可改：blue/green |
| `MCPGIT_NETRC` | (none) | 可改：配 GitHub 后启用远端同步 |
| `MCPGIT_BUNDLE_DIR` | `$HOME/.mcpgit/bundle` | 可改：缓存目录 |
| `MCPGIT_RELEASE_TAG` | (latest) | 建议改：仅在回滚/固定版本时 |
| `MCPGIT_ORG_ID` | (auto UUID) | 可改：显式指定不可变组织 id |

Instance identity: the immutable **organization id** is a UUID generated on
first install and stored in the data volume (`/.mcpgit-org-id`); it is bound
to SystemConfig rows, persons/grants, and SafeGit. The instance **name**
(`MCPGIT_INSTANCE`) is only a container/volume/display label and can be
renamed later without identity drift: reinstall the same data volume under a
new name, and the org id stays the same. To recover an identity, reuse the
same `--data-volume` (or set `MCPGIT_ORG_ID` explicitly).

Example pinning a version and a unique instance:

```sh
MCPGIT_INSTANCE=mcpgit-demo MCPGIT_RELEASE_TAG=mcpgit-git-<sha> \
  curl -fsSL https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/deploy/novice-install.sh | sh -s --
```

After install, connect with the SDK (Mode 1) or run
`deploy/novice-fetch.sh`/`deploy/novice-install.sh` on a separate offline
machine for the fetch-on-A/install-on-B flow.

SafeGit initializes in novice mode on first start: a random recovery password,
a default Shamir 3-of-5 bundle, and an Agent Key are persisted (0600) next to
the safegit repository, and the installer prints the paths plus the
`docker cp` command for backing up the shares file externally. First login is
`systemadmin` / `change-me`; change it after login. The instance stays
health-first: remote repo sync uses the netrc when `--netrc` is supplied and
is simply inactive otherwise.

## Fast verification loop

`scripts/verify-client-onboarding.sh` is the bounded closed loop for both
modes:

```sh
# Mode 1 against an existing instance
scripts/verify-client-onboarding.sh --existing ws://127.0.0.1:18991/__mcpgit/service-ws

# Mode 2: create a throwaway instance, connect, then clean up
scripts/verify-client-onboarding.sh --new --image mcpgit-offline-runtime:git-e7e056d...
```

The script reuses locally assembled images (no re-download), seeds a fresh
throwaway volume, waits for health with a hard timeout, runs the same example
client, and removes the throwaway container and volume unless `--keep` is
given. Total time is bounded; first run pays one workspace client build, later
runs reuse the Cargo cache.

## Automated credential lifecycle (shell + curl only)

No client-host Python is required. Issuing, exporting, rotating, and revoking
a scoped managed key are plain HTTP calls:

```sh
# issue (response carries pv_<id>_<secret> once; store it in a 0600 secret file)
curl -fsS -X POST "$BASE/__mcpgit/auth/person-verifies" \
  -H "Authorization: Basic $AUTH" -H "Content-Type: application/json" \
  -d "{\"name\":\"client/default\",\"person_id\":\"$PERSON_ID\"}"

# recover the raw key later (authorized owner or mcp.admin)
curl -fsS -X POST "$BASE/__mcpgit/auth/person-verifies/$CREDENTIAL_ID/export" \
  -H "Authorization: Basic $AUTH"

# rotate (old key dies immediately; response returns the new key)
curl -fsS -X POST "$BASE/__mcpgit/auth/person-verifies/$CREDENTIAL_ID/rotate" \
  -H "Authorization: Basic $AUTH"

# revoke (key dies on the next call)
curl -fsS -X DELETE "$BASE/__mcpgit/auth/person-verifies/$CREDENTIAL_ID" \
  -H "Authorization: Basic $AUTH"
```

`$BASE` is the instance base URL, `$AUTH` is `systemadmin:password` (or the
`handle:pv_...` form) base64-encoded, and `$PERSON_ID` is the scoped client
Person's UUID. Person/membership/role/repository grant rows are provisioned in
the instance SystemConfig repository (the runtime image ships the Python used
by the bootstrap/provision scripts); the client host itself needs only curl,
cargo, and its secret store.

## Trust boundary (choose consciously)

```text
internal integration (client + MCPGit in one trusted system)
  -> MCPGit listens on the internal network only, never publishes a public
     port; client connects without credentials (anonymous or Guest)

public exposure
  -> route through the Gateway (mcpgitgw): the Gateway requires caller
     credentials; the node's own unauthenticated endpoint is never exposed

fallback if a node endpoint is accidentally exposed
  -> Guest-first: unauthenticated callers get only Guest read on granted
     repositories, never full anonymous access
```

`MCPGIT_MCP_ANONYMOUS=1` (or an auth-disabled instance) enables full
unauthenticated access and is intended only for trusted internal networks;
do not expose that endpoint publicly.

## Client key source convention

The key source is the client application's choice (environment variable,
secret store, or process injection). The SDK only receives an Authorization
string and performs no key management. Hard rules: never hardcode a key into
source code, never commit it to Git, never write it to logs. The examples
read `MCPGIT_CLIENT_KEY` by convention.

## Built-in Persons

Every bootstrapped instance provisions three built-in Persons:

```text
systemadmin  control plane + SafeGit (no business repository access by default)
guest        read-only on granted repositories (default for missing credentials)
builder      business read/write on the standard business repositories
             (works, tablegit, binarygit by default)
```

## Known constraints

- The shipped SDK Release carries the complete transitive closure (offline
  bundle). Async clients must route tokio (and any tokio-family direct
  dependency) through the `mcpgit-sdk` registry, as shown above; mixing the
  bundle registry with a crates.io tokio produces two tokio instances and a
  `no reactor running` panic.
- An index-only distribution (publish only the registry index for the two
  crates and resolve transitive dependencies from crates.io) is designed and
  prototyped but not yet shipped. The published index still requires the full
  closure, so the offline bundle remains the current distribution.
- If a future index-only release ships, its index entries must point
  transitive dependencies at the classic crates.io index URL
  (`https://github.com/rust-lang/crates.io-index`), not the sparse URL;
  cargo treats the two crates.io source flavors as distinct crates.
