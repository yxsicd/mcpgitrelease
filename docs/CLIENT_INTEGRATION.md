# MCPGit Client Integration (two modes)

This is the Agent-facing integration runbook. Classify the task before doing
anything else:

```text
I already have an MCPGit instance   -> Mode 1: Client SDK connects to it
I need my own brand-new instance     -> Mode 2: deploy an instance, then Mode 1
```

Both modes depend only on immutable bytes published in this repository's
GitHub Releases. Download and installation are independent: you may download
everything first and install offline later. The two `mcpgit-service-*` crates
are not published to crates.io; they always come from the SDK Release in this
repository.

## Machine-readable authority

```text
https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/client-sdk.json
```

`client-sdk.json` is the atomic pointer to the recommended
`mcpgit-client-sdk-git-<source-sha>` Release. Read the tag, asset URLs, byte
counts, and SHA-256 digests from it. Never treat README text or GitHub
"Latest" as authority.

## Mode 1: connect to an existing instance

1. Download the recommended SDK Release assets and verify every SHA-256
   against `client-sdk.json`:

   ```sh
   sdk_tag=$(python3 -c "import json;print(json.load(open('client-sdk.json'))['tag'])")
   bundle="$sdk_tag.tar.gz"
   curl -fLO "https://github.com/yxsicd/mcpgitrelease/releases/download/$sdk_tag/$bundle"
   curl -fLO "https://github.com/yxsicd/mcpgitrelease/releases/download/$sdk_tag/mcpgit-service-sdk-2.0.0.crate"
   curl -fLO "https://github.com/yxsicd/mcpgitrelease/releases/download/$sdk_tag/mcpgit-service-client-2.0.0.crate"
   shasum -a 256 "$bundle" mcpgit-service-sdk-2.0.0.crate mcpgit-service-client-2.0.0.crate
   ```

   Compare the printed digests with the `sha256` values in `client-sdk.json`.

2. Configure the client repository with the offline registry bundle:

   ```sh
   tar -xzf "$bundle"
   cd "$sdk_tag"
   ./configure-project.sh /absolute/path/to/client-repository
   ```

3. Declare the dependencies. Async clients must take the runtime crate from
   the same `mcpgit-sdk` registry; a crates.io tokio creates a second,
   independent tokio crate instance and the SDK reactor fails with
   `there is no reactor running`.

   ```toml
   [dependencies]
   mcpgit-service-client = { version = "=2.0.0", registry = "mcpgit-sdk" }
   tokio = { version = "1", features = ["macros", "rt-multi-thread"], registry = "mcpgit-sdk" }
   ```

4. Build and connect:

   ```sh
   cd /absolute/path/to/client-repository
   cargo build --offline
   cargo run --example onboarding -- ws://<host>:8001/__mcpgit/service-ws
   ```

   Use `wss://` for TLS or a routed public host. Supply `Authorization` only
   when the instance requires it. The URL Host selects the configured default
   organization; a non-default organization uses the canonical
   `<service>-o<short-hash>` first label. Never invent or forward
   `x-mcpgit-person-id` as identity.

5. Integration is complete when the client prints `mcpgit.service.v2`
   metadata, lists repositories, and reads one file.

## Mode 2: create a brand-new instance, then connect

1. Create a fresh named data volume that will be this instance's exclusive
   `/data`:

   ```sh
   docker volume create mcpgit-<instance>-data
   ```

2. Deploy a new instance from the public runtime channel. The deployment kit
   accepts a new instance name and data source; it never reuses another
   instance's SystemConfig or volume:

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

   A new instance needs its own runtime env naming its repositories,
   organization/route, and SystemConfig. When a specific source revision is
   required instead of a channel, use the source-bound
   `mcpgit-git-<sha>` offline Release in this repository (manifest plus
   Base/Tools/Program layers) and assemble the runtime image locally; never
   mix layers from different manifests.

3. Wait until the container is `healthy` with restart count zero, then run
   Mode 1 against its Service endpoint:

   ```text
   ws://<host>:8001/__mcpgit/service-ws
   ```

4. Keep the new data volume for the instance lifetime. Upgrades and rollbacks
   must never delete it.

## Bounded verification checks

For Mode 1, verify in this order:

1. Cargo resolves `mcpgit-service-client 2.0.0` and `mcpgit-service-sdk
   2.0.0` from the `mcpgit-sdk` registry;
2. the client compiles with `--offline` after local registry setup;
3. the client connects to the intended Service WebSocket endpoint and reads
   `service.metadata`;
4. authenticated instances derive Person identity from credentials rather
   than a caller-supplied Person ID;
5. structured and bulk channels use the same endpoint authority and
   credential.

For Mode 2, additionally verify:

1. the new data volume is fresh and exclusively attached;
2. the new container is healthy with restart count zero;
3. repository discovery on the new instance returns its own repositories;
4. the instance's SystemConfig identity is distinct from every other
   instance.

## Known constraints

- The shipped SDK Release carries the complete transitive closure so
  `--offline` builds need no crates.io access. Async clients must declare
  tokio from the `mcpgit-sdk` registry as shown above.
- An index-only SDK distribution (publish only the two-crate registry index
  and resolve transitive dependencies from crates.io) is designed and
  prototyped but not yet shipped; the published Release still requires the
  full offline bundle.
- Downloading or configuring the SDK never installs, upgrades, restarts,
  promotes, or rolls back an MCPGit instance. Runtime channels and the SDK
  Release are independent control planes.
