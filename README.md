# MCPGit Release Channels

This public repository is the release and deployment control plane for MCPGit.
It deliberately separates the hot MCPGit binary from the cold development base
image.

## Stable channels

- dev: https://raw.githubusercontent.com/yxsicd/mcpgitrelease/dev/channel.json
- main: https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/channel.json
- prod: https://raw.githubusercontent.com/yxsicd/mcpgitrelease/prod/channel.json

Each channel is a small, atomic pointer to two immutable GitHub Releases:

    channel -> binary release (hot)
            -> devbase release (cold)

The matching strict offline installer manifests are:

- install-linux-amd64.env
- install-linux-arm64.env

They contain only whitelisted key/value fields, filenames, image identity, and
SHA-256 checksums. The target host does not need jq or Python.

## Publishing

1. Run publish-devbase only when Node, Bun, Python, or system tools change.
2. Run publish-binary for an MCPGit source revision.
3. Run set-dev-channel with the two immutable tags.
4. Validate dev, then run promote-channel with target main.
5. Validate main, then promote to prod.

Promotion copies the exact binary and devbase objects. It never rebuilds or
re-uploads them.

The workflow files are:

- publish-binary.yml
- publish-devbase.yml
- set-dev-channel.yml
- promote-channel.yml
- gc-releases.yml

Actions build artifacts are retained for one day and are only staging files.
GitHub Release assets are the public distribution source.

## Offline deployment

Prepare one directory containing the three files for the target architecture:

    install-linux-amd64.env
    mcpgit-linux-amd64.tar.gz
    mcpgit-devbase-linux-amd64.docker.tar.zst

For arm64, replace amd64 with arm64. Copy the deploy directory from this
repository or extract mcpgit-deploy.tar.gz from the binary Release.

Install or upgrade:

~~~sh
./deploy/mcpgit-deploy.sh \
  --bundle /path/to/downloaded/files \
  --instance mcpgit \
  --config /path/to/mcpgit.toml
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
explicitly pinned tags. It retains the newest 35 binary releases and newest 5
devbase releases. Unreferenced releases also receive a 14-day grace period.

The scheduled GC workflow only produces a plan. Deletion requires a manual run
with execute enabled. Unknown tag families are never deleted.

## Local validation

~~~sh
scripts/validate.sh
~~~
