# MCPGit Release Channels

This public repository is the release and deployment control plane for MCPGit.
It deliberately separates the hot MCPGit binary from the cold development base
image.

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

The current recommended release is:

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
GC must not infer that an SDK tag is a binary, devbase, or deployment object;
unknown tag families remain fail-safe and are never deleted automatically.

The scheduled GC workflow only produces a plan. Deletion requires a manual run
with execute enabled. Unknown tag families are never deleted.

## Local validation

~~~sh
scripts/validate.sh
~~~
