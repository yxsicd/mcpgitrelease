# MCPGit Release Channels

This public repository publishes MCPGit Linux binaries independently from the
slower-moving development base image.

The three channel manifests have fixed public URLs:

- dev: https://raw.githubusercontent.com/yxsicd/mcpgitrelease/dev/channel.json
- main: https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/channel.json
- prod: https://raw.githubusercontent.com/yxsicd/mcpgitrelease/prod/channel.json

Each manifest points to an immutable GitHub Release and includes the source
revision, architecture-specific asset URLs, sizes, and SHA-256 checksums.
Consumers download one small manifest, select linux/amd64 or linux/arm64,
verify the checksum, and atomically replace only the MCPGit binary.

## Promotion model

An MCPGit source revision is built once and published as an immutable release.
Promotion changes only the target branch's channel.json:

    immutable release <- dev <- main <- prod

main must reuse a release already selected by dev; prod must reuse a release
already selected by main. Promotion never rebuilds or re-uploads the binary.

The development base image is a separate cold artifact with its own lifecycle.
It is not embedded in the MCPGit binary archives and is not rebuilt during a
normal channel promotion.

## Download example

~~~sh
channel_url=https://raw.githubusercontent.com/yxsicd/mcpgitrelease/prod/channel.json
arch=amd64
asset_url=$(curl -fsSL "$channel_url" | jq -r --arg arch "$arch" '.artifacts[] | select(.arch == $arch) | .url')
expected=$(curl -fsSL "$channel_url" | jq -r --arg arch "$arch" '.artifacts[] | select(.arch == $arch) | .sha256')
curl -fL "$asset_url" -o mcpgit.tar.gz
printf '%s  %s\n' "$expected" mcpgit.tar.gz | sha256sum -c -
~~~
