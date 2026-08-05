# MCPGit Release Channels

This public repository is the release and deployment control plane for MCPGit.
It deliberately separates the hot MCPGit binary from the cold development base
image.

## Agent quick start

An Agent must first classify the task. Do not mix these two paths:

```text
Need Rust code to call an existing MCPGit server?
  -> Mode 1: Client SDK integration

Need your own brand-new MCPGit instance, then Rust code against it?
  -> Mode 2: deploy a new instance, then use Mode 1
```

The complete two-mode runbook (download, offline installation, async client
guidance, and bounded verification checks) is in
[`docs/CLIENT_INTEGRATION.md`](docs/CLIENT_INTEGRATION.md).

### Mode 2 instance side: deploy or upgrade an MCPGit instance

Use the `dev`, `main`, or `prod` runtime channel. Do not use a
`mcpgit-client-sdk-*` Release to deploy a server.

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

The current pointer selects:

```text
mcpgit-client-sdk-git-8730092557649f2b4c6661d73424add50407cf38
```

Download and verify the SDK bundle:

~~~sh
sdk_tag=mcpgit-client-sdk-git-8730092557649f2b4c6661d73424add50407cf38
sdk_bundle="$sdk_tag.tar.gz"

curl -fLO \
  "https://github.com/yxsicd/mcpgitrelease/releases/download/$sdk_tag/$sdk_bundle"
printf '%s  %s\n' \
  4d4c8a5cc67fccd19d1864750463ba14a64e59def3d70bf2237761220992b450 \
  "$sdk_bundle" | shasum -a 256 -c -
~~~

Configure the client repository and add the dependency:

~~~sh
tar -xzf "$sdk_bundle"
cd "$sdk_tag"
./configure-project.sh /absolute/path/to/client-repository
~~~

```toml
[dependencies]
mcpgit-service-client = { version = "=2.0.0", registry = "mcpgit-sdk" }
```

Then compile the client project:

~~~sh
cd /absolute/path/to/client-repository
cargo check --offline
~~~

Integration is complete only when:

1. Cargo resolves `mcpgit-service-client 2.0.0` and
   `mcpgit-service-sdk 2.0.0` from `mcpgit-sdk`;
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

## Stable channels

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
the immutable GitHub Release assets and manifest have been cross-checked. The
current recommended release is:

```text
mcpgit-client-sdk-git-8730092557649f2b4c6661d73424add50407cf38
```

It contains exactly four assets:

- `mcpgit-client-sdk-release-v1.json` — source-bound asset manifest;
- `mcpgit-service-sdk-2.0.0.crate` — standard Cargo package archive;
- `mcpgit-service-client-2.0.0.crate` — standard Cargo package archive;
- `mcpgit-client-sdk-git-8730092557649f2b4c6661d73424add50407cf38.tar.gz`
  — complete offline local Cargo registry.

The offline bundle contains the two MCPGit packages plus the exact transitive
dependency closure, 129 `.crate` files in total. Every archive is bound by
SHA-256. GitHub is only the immutable download location: the SDK is not
published to crates.io and does not use GitHub Packages as a live Cargo
registry.

Download and verify the recommended bundle:

~~~sh
sdk_tag=mcpgit-client-sdk-git-8730092557649f2b4c6661d73424add50407cf38
sdk_bundle=mcpgit-client-sdk-git-8730092557649f2b4c6661d73424add50407cf38.tar.gz

curl -fLO \
  "https://github.com/yxsicd/mcpgitrelease/releases/download/$sdk_tag/$sdk_bundle"
shasum -a 256 "$sdk_bundle"
# expected: 4d4c8a5cc67fccd19d1864750463ba14a64e59def3d70bf2237761220992b450
~~~

Configure a Rust client repository:

~~~sh
tar -xzf "$sdk_bundle"
cd "$sdk_tag"
./configure-project.sh /absolute/path/to/client-repository
~~~

Then use an ordinary exact Cargo version dependency:

~~~toml
[dependencies]
mcpgit-service-client = { version = "=2.0.0", registry = "mcpgit-sdk" }
~~~

The configuration script verifies every bundled crate, installs a
project-local `file://` Cargo registry in `.mcpgit-sdk`, and writes the named
`mcpgit-sdk` registry entry to `.cargo/config.toml`. After the first local
registry initialization, the client repository builds without network access:

~~~sh
cargo build --offline
~~~

The earlier `mcpgit-client-sdk-git-dcde4121...` release is retained as an
immutable audit record. New integrations should use the recommended release
above.

## Publishing

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
