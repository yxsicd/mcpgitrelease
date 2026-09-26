# First installation and long-lived Program-only updates

Use the public root installer for first installation. It resolves one immutable
installer snapshot and verifies the selected pointer's exact manifest SHA-256,
source and native target before using any asset filename. A new instance gets
Base, Tools, Program, repository templates and a unique administrator credential.
New installations bind the selected port to 127.0.0.1 by default. The explicit
`MCPGIT_BIND_ADDRESS=0.0.0.0` environment setting opts into all IPv4 interfaces;
`127.0.0.1` explicitly selects loopback. Existing
instances retain their current host binding when that setting is absent.

After successful Docker health, authenticated MCP discovery/scoped read and
actual program-byte checks, the installer writes a private receipt under
`$HOME/.mcpgit/install-state/<instance>.json`. `MCPGIT_STATE_DIR` can relocate it.
It contains credential file references, never credential values. Keep it with
the instance's host configuration; it is not a data backup or signed attestation.
The installed receipt also preserves an explicitly disabled executable-build
repository. A routine upgrade must not enable capabilities by applying defaults.
This simple facade refuses custom process, environment, resource and security
overrides it cannot faithfully reproduce; those remain with their deployment owner.

## Upgrade commands

```sh
mcpgitctl --instance ddtry upgrade --check
mcpgitctl --instance ddtry upgrade
```

The first command checks the selected candidate without activation. The second
uses the root installer with `--program-only`, retaining the recorded port,
data volume, config directory, credential directory and tool installation path.
No GitHub Actions, Node installation or private source checkout is required.

## Continuous online Program updates

After the first verified installation, enable the host-side updater once:

```sh
mcpgitctl --instance ddtry auto-upgrade enable
```

From then on, publishing and promoting a new immutable Program in this GitHub
repository is the only routine release action. The host checks
`offline-latest.json` every 15 minutes, selects its native architecture, and
delegates preflight, byte verification, transactional container replacement,
health acceptance, and rollback to the same installer used by an attended
upgrade. It does not mount the Docker socket into MCPGit or modify `/data`.

The controller defers activation while one-minute host load exceeds 1.5 per
CPU or the MCPGit container exceeds 75 percent CPU. A continuously busy
instance is updated after a bounded six-hour deferral so security and
correctness releases do not remain stale indefinitely. These thresholds and
the interval can be changed when enabling the updater, for example:

```sh
mcpgitctl --instance ddtry auto-upgrade enable \
  --interval 300 --max-defer 7200 --max-container-cpu 85
```

Linux installs use a systemd timer (system scope for root, user scope
otherwise); macOS installs use a LaunchAgent. Each attempt and final exact
source/manifest identity is recorded under
`$MCPGIT_STATE_DIR/auto-upgrade` (default `~/.mcpgit/auto-upgrade`). The update
is fail-closed if the pointer, architecture selection, preflight, activation,
or exact post-upgrade source readback differs.

The equivalent explicit installer option is `--program-only`. For an existing
older installation without a receipt, first run the ordinary installer once
with the same instance name, paths and port. It fully checks the cached release
and records the baseline without recreating an already exact healthy container.

The plan is one of:

* `full`: no trusted baseline, explicit `--rebuild`, or changed cold layers.
* `exact`: same manifest, immutable image and verified binary facts; no runtime
  layer download or archive unpack. Authenticated MCP acceptance still runs.
* `program`: the exact Base/Tools and assembly contract are unchanged; download
  and unpack only Program. Templates do not reinitialize an existing volume.

Strict `--program-only` fails rather than turning into `full`. A cold-layer or
assembly change needs an explicit normal/full installation decision. Missing or
altered image evidence is not a reason to trust labels. Reusing a directory
requires the per-bundle lock, and changing an instance requires its instance lock.
Inspect a lock left by a killed process; do not automatically delete it.

## Bounded image ancestry and rollback

Program updates build from one fixed verified foundation image recorded by the
first complete installation, never from the previous Program update. The old
Program directory is removed before the new complete Program is copied. Thus
old files cannot survive when a new Program archive removes them. The original
foundation may retain the first Program's bytes in lower immutable layers; this
is a fixed cost, not a growing chain. Do not prune the foundation while using it.
Ordinary Docker image/rollback retention is separate and is not automatically GC'd.

The old container stays stopped during replacement; on candidate startup,
MCP/auth or byte-check failure, restore it with the original volume. No second
running writer is allowed. Recovery objects from older transactions are retained,
not deleted by prefix. Unrecognized mounts, networks or routing labels require
their deployment owner instead of being silently discarded by this facade.

This is container rollback, not reversal of already committed data or schema
migrations. Qualify a genuinely new runtime across versions before promotion.
This installer does not auto-migrate data formats. Abrupt host loss or SIGKILL
still requires inspecting retained containers, locks and private state before
restarting an interrupted installation.

## Offline and explicit versions

An explicit complete `--bundle` remains an operator-selected offline input.
Normal online mode always refreshes the pinned selection. An explicit online
`MCPGIT_RELEASE_TAG` additionally requires `MCPGIT_EXPECTED_MANIFEST_SHA256`;
this is an intentional guard against treating a mutable tag alone as authority.
After a successful baseline, a Program-only offline bundle need contain only
the selected manifest, Program archive, and the same installer/helper contract.
It is not a fresh-install or disaster-recovery bundle.

`mcpgitctl backup` is not implemented and now exits nonzero. It never reports
that a backup exists. The disposable new-user smoke refuses pre-existing paths,
containers and volumes, including when `--keep` is supplied. Use the non-destructive
Agent onboarding probe to inspect a retained instance instead.

## Qualification evidence

The exact controller revision and ten real WSL acceptance cases are recorded in
`docs/evidence/program-upgrade-wsl-20260905.json`: fresh install, no-op, Program
replacement/recovery, obsolete-file removal, constant image ancestry and refused
incompatible/unauthorized inputs. Valid Program fixture binaries were unchanged;
this evidence does not approve a newly compiled runtime or a data-format migration.
