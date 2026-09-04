# MCPGit

This public repository is the install and release authority for MCPGit.

Linux Program binaries are compiled only by the target architecture's native
Linux Cargo/rustc toolchain. The amd64 and arm64 release jobs run on matching
native GitHub runners and call MCPGit's `build-linux-program-native.sh`.
Docker/BuildKit is not a Program compiler; it remains a Base/Tools/runtime
assembly mechanism only.

## Install the latest MCPGit

For a normal Linux amd64/arm64 installation, this is the only command you need:

```sh
curl -fsSL https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/install.sh | sh
```

The root installer is deliberately versionless. It follows
`offline-latest.json`, detects the host architecture, verifies the selected
immutable Release and layer checksums, preserves the instance data volume on
upgrade, starts MCPGit, and installs `mcpgitctl`. GitHub's UI "Latest" marker
is not release authority.

At the start of each online run, `install.sh` resolves the current public
`main` Git SHA once through the GitHub API. The deployment wrapper, backend,
helpers, Dockerfile, and `offline-latest.json` used by that run are then fetched
from that exact immutable Git revision. This prevents regional Raw/CDN cache
lag from mixing files from different `main` revisions in one installation.
Existing cached helper scripts and the runtime Dockerfile are refreshed from
that same snapshot on every online run; only checksum-matching immutable
release layers are reused from cache.

Runtime assembly is also content-bound. A cached Base tag is accepted only
when its Docker image ID exactly matches the selected release manifest, and the
assembled runtime uses a source-bound image tag and is re-probed against the
manifest and in-image executable hashes before activation.
The exact installer snapshot's `Dockerfile.offline-runtime` SHA-256 is recorded
on the assembled image and participates in cache admission too, so a newer
assembly contract cannot silently reuse an older image built from the same
MCPGit binary Release. The runtime image exposes an HTTP `/healthz` Docker
HEALTHCHECK in addition to the installer's external acceptance probe.

Instance replacement is transactional at the container boundary. For an
existing instance, the installer refuses a different `/data` volume, preserves
the current container under a fixed stopped rollback name, starts and health-
checks the candidate, and automatically restores the previous container when
candidate start or health fails. Only one bounded rollback container is kept.
For a brand-new instance, an already occupied host port is rejected before a
new data volume is created.
An existing instance config with a different organization identity is also a
hard blocker; the installer never rewrites it into a different identity.
Candidates run with Docker restart disabled during the health gate; the normal
`unless-stopped` restart policy is enabled only after acceptance. A crashing
candidate therefore fails fast instead of looping until the full health
timeout while the previous container is waiting for rollback.

Re-running the installer against an already healthy exact-current instance is
a verification-only no-op when the runtime image ID, data volume, config mount,
optional netrc mount, and host port all match. The container is not recreated,
so checking for the latest release does not create avoidable service downtime.

Re-running the same one-line command always re-reads `offline-latest.json`.
The default `$HOME/.mcpgit/bundle` is only a checksum-verified download cache,
not a release pin, so a promoted product release is picked up automatically.
Use an explicit existing `--bundle DIR` only when intentionally installing a
pinned/offline bundle.

The default release chain is:

```text
reviewed MCPGit source SHA
  -> immutable linux-amd64 + linux-arm64 Releases
  -> production gates
  -> offline-latest.json
  -> install.sh
```

Publishing binaries does not automatically make them the default. Promotion
changes only `offline-latest.json`; rollback selects the previous complete
dual-architecture pair and never rebuilds or mixes layers.

### Direct installer and offline bundle

For a normal single-node installation, use the product installer instead of
the release-control scripts below:

```sh
curl -fsSL \
  https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/deploy/mcpgit-install.sh \
  | sh
```

The installer verifies the selected immutable offline Release, creates or
reuses the instance data volume, initializes the instance, starts MCPGit, and
installs `mcpgitctl` in `${HOME}/.local/bin` by default. After installation:

```sh
~/.local/bin/mcpgitctl status
~/.local/bin/mcpgitctl doctor
```

Re-running the installer for the same instance preserves its data volume and
organization identity. To prepare a self-contained bundle for an offline
machine:

```sh
curl -fsSL \
  https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/deploy/mcpgit-install.sh \
  | sh -s -- --download-only --bundle ./mcpgit-offline

# copy ./mcpgit-offline to the offline machine, then:
./mcpgit-install.sh --bundle . --instance mcpgit
```

The current `offline-latest.json` product pointer publishes both supported
Linux architectures: `linux-amd64` and `linux-arm64`. The installer detects
the host architecture and selects only the matching immutable release; other
architectures fail closed before installation.

## Agent quick start

An Agent must first classify the task. Do not mix these three paths:

```text
Need to query or change an existing MCPGit instance as an Agent?
  -> Mode 0: MCP Agent interface at /mcp

Need Rust code to call the lower-level Service of an existing server?
  -> Mode 1: Client SDK integration

Need your own brand-new MCPGit instance, then Rust code against it?
  -> Mode 2: deploy a new instance, then use Mode 1
```

The progressive MCP path is in
[`docs/MCP_AGENT_QUICKSTART.md`](docs/MCP_AGENT_QUICKSTART.md). It starts from
the eight-tool Agent Kernel and discloses only the selected Skill operation.
The complete Service/deployment runbook (download, offline installation, async
client guidance, and bounded verification checks) is in
[`docs/CLIENT_INTEGRATION.md`](docs/CLIENT_INTEGRATION.md).

### Mode 0 Agent side: use the MCP interface of an existing instance

Connect an MCP client to `https://<host>/mcp` (or the instance's advertised
`mcp_url`). Start with `service_metadata` and `skill_list`; defer
`person_status` until the chosen operation or authorization requires caller
identity.
Select one operation, load only that operation with `skill_get`, then use its
declared read, write, or publish runner. Do not call compiled operation names as
top-level tools and do not infer instance-dependent availability.

### Mode 2 instance side: deploy or upgrade an MCPGit instance

For a normal new instance or upgrade, use the root `install.sh` path and its
`offline-latest.json` selection. Do not use a `mcpgit-client-sdk-*` Release to
deploy a server.

The older `dev`/`main`/`prod` channel-v2 path remains for specialized fleet
compatibility only; it is not the normal product install path.

Before changing a running instance, the Agent must record and preserve:

- the exact target host and instance name;
- the existing `/data` volume or bind path;
- the runtime configuration and secret mounts;
- the attached Docker network and public route;
- the current container identity and rollback name.

Never change the deployment host or Docker daemon without explicit user
approval. Never delete the existing data volume. Never interpret an SDK Release
as a runtime channel.

Download the selected runtime channel:

~~~sh
curl -fsSL \
  https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/deploy/mcpgit-fetch.sh \
  | bash -s -- prod ./mcpgit-bundle
~~~

Use `dev` or `main` instead of `prod` only when the requested target channel is
explicit. Configure the downloaded runtime environment first:

~~~sh
cp ./mcpgit-bundle/deploy/mcpgit-runtime.env.example \
  ./mcpgit-bundle/mcpgit-runtime.env

# Edit only the required repository, organization, route, and secret locations.
~~~

Run the bundled read-only preflight and inspect its JSON before activation:

~~~sh
./mcpgit-bundle/deploy/mcpgit-preflight.sh \
  --bundle ./mcpgit-bundle \
  --instance mcpgit \
  --runtime-env ./mcpgit-bundle/mcpgit-runtime.env \
  --netrc /absolute/path/to/netrc \
  > mcpgit-preflight.json
~~~

Do not continue when it exits `2` or when `.blockers` is non-empty. The full
Agent procedure is in `docs/AGENT_DEPLOYMENT_RUNBOOK.md`.

Initialize the pinned toolchain volume, then deploy on the same approved host
with the same arguments:

~~~sh
./mcpgit-bundle/deploy/mcpgit-toolchain-init.sh

./mcpgit-bundle/deploy/mcpgit-deploy.sh \
  --bundle ./mcpgit-bundle \
  --instance mcpgit \
  --runtime-env ./mcpgit-bundle/mcpgit-runtime.env \
  --netrc /absolute/path/to/netrc
~~~

Deployment is complete only when all of the following are true:

1. the new container is healthy and restart count is zero;
2. the exact original data source remains attached;
3. MCP/HTTP initialization and Service metadata reads succeed;
4. the expected public route resolves;
5. the previous container remains available for rollback until acceptance.

### Mode 1 client side: integrate a Rust client with an existing MCPGit instance

Use the Client SDK Release. Do not run deployment scripts and do not modify the
server container. The machine-readable authority for the recommended SDK is:

```text
https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/client-sdk.json
```

Read the tag, package versions, asset URLs, sizes, and SHA-256 digests from that
pointer at integration time. Do not copy a tag, version, or digest from prose.
Download the `offline_registry_bundle` URL and verify its exact `sha256` before
extracting it.

Configure the client repository and add the dependency:

~~~sh
tar -xzf <offline_registry_bundle-file>
cd <client-sdk.json-tag>
./configure-project.sh /absolute/path/to/client-repository
~~~

```toml
[dependencies]
mcpgit-service-client = { version = "=<packages.mcpgit-service-client>", registry = "mcpgit-sdk" }
```

Then compile the client project:

~~~sh
cd /absolute/path/to/client-repository
cargo check --offline
~~~

Integration is complete only when:

1. Cargo resolves the exact Client and SDK versions declared by the same
   `client-sdk.json` pointer from `mcpgit-sdk`;
2. the client compiles with `--offline` after local registry setup;
3. the client connects to the intended MCPGit Service WebSocket endpoint;
4. authenticated instances derive Person identity from credentials rather than
   accepting a caller-supplied Person ID;
5. structured and bulk channels use the same endpoint authority and credential.

For a typical standalone instance the Service URL is:

```text
ws://<host>:8001/__mcpgit/service-ws
```

For TLS or a routed public host, use `wss://` and the deployed public hostname.
Supply `Authorization` only when required by that instance. Do not invent or
forward `x-mcpgit-person-id` as identity.

## Advanced: legacy channel-v2

These branches remain for existing fleet workflows. New standalone installs
should use `install.sh` and `offline-latest.json`.

- dev: https://raw.githubusercontent.com/yxsicd/mcpgitrelease/dev/channel.json
- main: https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/channel.json
- prod: https://raw.githubusercontent.com/yxsicd/mcpgitrelease/prod/channel.json

Each channel is a small, atomic pointer to three immutable GitHub Releases:

    channel -> binary release (hot)
            -> devbase release (cold)
            -> deployment release (small, architecture-independent)

The matching strict offline installer manifests are:

- install-linux-amd64.env
- install-linux-arm64.env

They contain only whitelisted key/value fields, filenames, image identity, and
SHA-256 checksums. The target host does not need jq or Python.

## Rust Client SDK

The Rust Client SDK is an independent immutable Release family. It is not
selected by `dev`, `main`, or `prod`, and downloading or configuring it never
installs, upgrades, restarts, promotes, or rolls back an MCPGit instance.

`client-sdk.json` is the atomic recommendation pointer and is updated only after
the immutable GitHub Release assets and manifest have been cross-checked. Its
`tag`, `packages`, and `assets` fields are authoritative; README examples are
never a version pointer. The release contains the source-bound manifest, the
two standard Cargo package archives, and the complete offline local Cargo
registry bundle.

The offline bundle contains the two MCPGit packages plus the exact transitive
dependency closure recorded by its manifest. Every archive is bound by SHA-256.
GitHub is only the immutable download location: the SDK is not
published to crates.io and does not use GitHub Packages as a live Cargo
registry.

Download the asset whose role is `offline_registry_bundle` from its pointer URL
and verify its exact size and SHA-256 before extraction.

Configure a Rust client repository:

~~~sh
tar -xzf <offline_registry_bundle-file>
cd <client-sdk.json-tag>
./configure-project.sh /absolute/path/to/client-repository
~~~

Then use an ordinary exact Cargo version dependency:

~~~toml
[dependencies]
mcpgit-service-client = { version = "=<pointer package version>", registry = "mcpgit-sdk" }
~~~

The configuration script verifies every bundled crate, installs a
project-local `file://` Cargo registry in `.mcpgit-sdk`, and writes the named
`mcpgit-sdk` registry entry to `.cargo/config.toml`. After the first local
registry initialization, the client repository builds without network access:

~~~sh
cargo build --offline
~~~

Older SDK releases remain immutable audit records. New integrations must use
the release selected by the pointer.

## Publishing

### Default product release

1. Select one reviewed full MCPGit source SHA.
2. Publish both immutable offline Releases for `linux-amd64` and `linux-arm64`.
3. Complete the required production gates for those exact bytes.
4. Run `promote-offline-latest` with that source SHA. It independently reads
   both GitHub Release manifests, verifies source/architecture identity and
   manifest digests, and atomically commits the new `offline-latest.json`.
5. Run a fresh installation through the root `install.sh` path.

Never promote by moving GitHub's UI Latest marker, retagging, rebuilding, or
embedding a version in `install.sh`.

### Legacy channel-v2 publishing

1. Run publish-devbase only when Python or base-system tools change. Node and
   Bun are composed through a separate versioned toolchain volume.
2. Run publish-binary for an MCPGit source revision and packaging revision.
3. Run publish-deployment whenever deployment or configuration defaults change.
4. Run set-dev-channel with the three immutable tags.
5. Validate dev, then run promote-channel with target main.
6. Validate main, then promote to prod.

Promotion copies the exact binary, devbase, and deployment objects. It never rebuilds or
re-uploads them.

The workflow files are:

- publish-binary.yml
- publish-devbase.yml
- publish-deployment.yml
- set-dev-channel.yml
- promote-channel.yml
- gc-releases.yml
- set-client-sdk.yml
- publish-client-sdk.yml
- validate-client-sdk.yml

Actions build artifacts are retained for one day and are only staging files.
GitHub Release assets are the public distribution source.

## Offline deployment

The recommended entrypoint does not require reading channel.json or copying
Release URLs:

~~~sh
curl -fsSL \
  https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/deploy/mcpgit-fetch.sh \
  | bash -s -- prod ./mcpgit-bundle
~~~

The bootstrap script detects amd64 or arm64, downloads the selected channel's
strict installer manifest and all three assets, verifies every SHA-256 checksum,
and extracts the deployment kit. Reusing the same target directory makes this a
hot update: unchanged devbase and deployment assets are accepted from the
verified cache, so only a changed MCPGit binary is transferred. To inspect
before execution instead:

~~~sh
curl -fsSLO https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/deploy/mcpgit-fetch.sh
less mcpgit-fetch.sh
bash mcpgit-fetch.sh prod ./mcpgit-bundle
~~~

Prepare one directory containing the channel manifest and the two
architecture-specific assets:

    install-linux-amd64.env
    mcpgit-linux-amd64.tar.gz
    mcpgit-devbase-linux-amd64.docker.tar.zst

For arm64, replace amd64 with arm64. Extract mcpgit-deploy.tar.gz from the
deployment Release into the same directory. The kit includes a fixed full-feature
mcpgit.toml and mcpgit-runtime.env.example. Copy the latter to
mcpgit-runtime.env and configure the remote Git backend, organization, and
bootstrap repository names.

The bundled full-feature repository baseline is `works`, `tablegit`,
`binarygit`, `rootskills`, `mcpgitsystem`, and `safegit`. SafeGit root
material is never included in a Release asset; provide it only through the
mode-0600 runtime environment or the target's secret manager.

Provision the immutable per-host toolchain once before install or upgrade:

~~~sh
./deploy/mcpgit-toolchain-init.sh
~~~

The script selects the host architecture, pulls Node 22.23.1 and Bun 1.3.14 by
architecture-specific OCI digest, copies only their runtime trees into the
`mcpgit-toolchain-node22.23.1-bun1.3.14` external volume, and verifies the
volume through a read-only mount. MCPGit instances share that volume as
`/opt/mcpgit-toolchain:ro`; a future toolchain update creates a differently
named volume rather than mutating this one.

Install or upgrade:

~~~sh
./deploy/mcpgit-deploy.sh \
  --bundle /path/to/downloaded/files \
  --instance mcpgit \
  --runtime-env /path/to/mcpgit-runtime.env \
  --netrc /path/to/netrc
~~~

If a container named mcpgit already exists, the script automatically preserves:

- the existing /data named volume or bind directory;
- the /config/mcpgit.toml bind;
- the /root/.netrc bind;
- the first attached Docker network;
- MCPGIT_* and RUST_LOG environment values;
- Traefik enablement and the public host when discoverable.

The legacy container is stopped and retained under a timestamped rollback name.
The new container starts without a published host port. It must pass a real MCP
initialize health check before the migration is accepted. On failure the legacy
container is restored automatically.

Explicit rollback:

~~~sh
./deploy/mcpgit-deploy.sh --instance mcpgit --rollback
~~~

Managed upgrades keep both the previous binary link and previous base-image
descriptor. Once a devbase archive has been verified and loaded, its exact local
image ID is recorded; later binary-only upgrades reuse that identity without
loading the cold archive. Docker data volumes are never deleted by the
deployment script.

Useful overrides:

~~~sh
./deploy/mcpgit-deploy.sh \
  --bundle ./bundle \
  --instance prodmcpgit \
  --install-root /srv/mcpgit/prod \
  --data-source prodmcpgit_data \
  --network armnet \
  --traefik-host prodmcpgit.example.com
~~~

If a historical deployment used a Compose project name that differs from the
container name, keep the container identity in --instance. Use --project-name
for a project with the standard mcpgitrelease- prefix (for example, lrigit uses
--project-name mcpgit), or --compose-project for an exact legacy project name
(for example, crcmcpgit). Use the same option for an explicit rollback. The two
project overrides are mutually exclusive.

## Retention

retention.json protects every Release referenced by dev, main, or prod, plus
explicitly pinned tags. It retains the newest 35 binary releases, newest 5
devbase releases, and newest 20 small deployment releases. Unreferenced releases
also receive a 14-day grace period.

Client SDK tags are separate from runtime channel retention and promotion. The
GC classifies them explicitly, protects the tag selected by `client-sdk.json`,
and retains the newest five SDK Releases in addition to the grace period.

The scheduled GC workflow only produces a plan. Deletion requires a manual run
with execute enabled. Unknown tag families are never deleted.

## Local validation

~~~sh
scripts/validate.sh
~~~
