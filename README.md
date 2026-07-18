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

## Publishing

1. Run publish-devbase only when Node, Bun, Python, or system tools change.
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
and extracts the deployment kit. To inspect before execution instead:

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
descriptor. Docker data volumes are never deleted by the deployment script.

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

## Retention

retention.json protects every Release referenced by dev, main, or prod, plus
explicitly pinned tags. It retains the newest 35 binary releases, newest 5
devbase releases, and newest 20 small deployment releases. Unreferenced releases
also receive a 14-day grace period.

The scheduled GC workflow only produces a plan. Deletion requires a manual run
with execute enabled. Unknown tag families are never deleted.

## Local validation

~~~sh
scripts/validate.sh
~~~
