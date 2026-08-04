# Agent deployment runbook

This is the execution and safety contract for an Agent deploying or upgrading
an MCPGit runtime. Rust Client integration is a separate task and must not run
these deployment commands.

## 1. Freeze target identity

Before changing anything, record:

- user-approved hostname and Docker context;
- exact instance and Compose project names;
- current container ID, binary label, state, health, and restart count;
- `/data`, `/config/mcpgit.toml`, and `/root/.netrc` mount sources;
- attached Docker network and public hostname;
- managed or legacy rollback candidates.

Never move deployment to another host or Docker daemon without explicit user
approval. Never delete or replace the existing data source merely because it
cannot be inferred.

## 2. Download immutable channel assets

```sh
curl -fsSL \
  https://raw.githubusercontent.com/yxsicd/mcpgitrelease/main/deploy/mcpgit-fetch.sh \
  | bash -s -- prod ./mcpgit-bundle
```

Replace `prod` only when the user explicitly selected `dev` or `main`.

## 3. Produce a read-only preflight receipt

Prepare the runtime environment, then inspect without changing Docker or
deployment state:

```sh
cp ./mcpgit-bundle/deploy/mcpgit-runtime.env.example \
  ./mcpgit-bundle/mcpgit-runtime.env

./mcpgit-bundle/deploy/mcpgit-preflight.sh \
  --bundle ./mcpgit-bundle \
  --instance mcpgit \
  --runtime-env ./mcpgit-bundle/mcpgit-runtime.env \
  --netrc /absolute/path/to/netrc \
  > mcpgit-preflight.json
```

Exit `0` means no blockers. Exit `2` means JSON was produced but deployment
must stop. Exit `1` means invocation or manifest syntax was invalid.

An Agent must inspect at least:

```text
.host.hostname
.host.docker_context
.target.instance
.bundle.channel
.bundle.binary_revision
.current.data_source
.proposed.data_source
.proposed.network
.rollback
.blockers
.warnings
```

Surface any target host, data source, network, route, configuration, or identity
mount change to the user before activation.

## 4. Activate on the approved target only

Initialize the immutable toolchain volume once, then repeat the same arguments
that were preflighted:

```sh
./mcpgit-bundle/deploy/mcpgit-toolchain-init.sh

./mcpgit-bundle/deploy/mcpgit-deploy.sh \
  --bundle ./mcpgit-bundle \
  --instance mcpgit \
  --runtime-env ./mcpgit-bundle/mcpgit-runtime.env \
  --netrc /absolute/path/to/netrc
```

If preflight used an explicit `--data-source`, `--network`, `--project-name`,
`--compose-project`, `--install-root`, or Traefik option, activation must repeat
it exactly.

## 5. Acceptance evidence

Activation is accepted only after recording:

1. exact new container ID and source/binary label;
2. state `running`, health `healthy`, restart count `0`;
3. exact `/data` source equals the approved preflight value;
4. config, netrc, network, and public route match the plan;
5. `GET /__mcpgit/sites` succeeds;
6. MCP initialize and Service metadata/read succeed through the intended route;
7. previous managed release or legacy container remains recoverable.

## 6. Rollback

Use the same instance and project identity:

```sh
./mcpgit-bundle/deploy/mcpgit-deploy.sh \
  --instance mcpgit \
  --rollback
```

Rollback is complete only after health, data source, network, configuration, and
public route are rechecked. If activation and automatic rollback both fail,
preserve all containers, volumes, releases, and state files while diagnosing.

## 7. Publication families

| Family | Authority | Purpose |
|---|---|---|
| Runtime channel | `dev/main/prod` `channel.json` | Deploy or upgrade servers |
| Direct runtime Release | `mcpgit-git-<sha>` | Source-bound runtime evidence and controlled direct install |
| Client SDK | `client-sdk.json` | Integrate Rust code with an existing server |

Never use a Client SDK tag as a server runtime. Never infer a runtime channel
from GitHub's “Latest” marker.
