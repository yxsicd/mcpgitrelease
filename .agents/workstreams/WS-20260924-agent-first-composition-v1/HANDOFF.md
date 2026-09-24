# Agent-first Web Component composition

Task: `WS-20260924-agent-first-composition-v1`

## Objective

Make the already released `mcpgit-runtime` and `pptx-presentation` easy for
an Agent to discover and compose from the public release authority without
adding a new runtime API or publishing a new component version.

## Source

- target: `origin/main@906c41b18a11eb16c30b0875663e71ca3bdcf46b`
- branch: `work/WS-20260924-agent-first-composition-v1`
- worktree:
  `/Users/youxianshi/code/.worktrees/mcpgitrelease-agent-first-composition-v1`

## Change

- added `web-components/AGENT_COMPOSITION.md` as the single public composition
  recipe for stable discovery, verified loading, shared runtime connection,
  opaque `presentation.context`, dynamic Skill calls, exact views and failure
  recovery;
- root, registry and both child Consumer Skills now expose the same composition
  pointer through public metadata;
- maintainer router now covers both component maintainer Skills;
- generated `metadata/skills.json` carries the composition pointers;
- contract tests bind discovery, stable registry/catalog/manifest consistency,
  composition calls, no hard-coded current version tags and authority
  boundaries.

## Validation

- `python3 scripts/index_skills.py --check`: PASS; 4 public Skills, 3
  maintainer Skills, 2 Web Components;
- focused Agent composition contract: PASS 4/4;
- `scripts/validate.sh`: PASS;
- runtime Node contract tests: PASS 10/10;
- release Python suite: PASS 107/107;
- `git diff --check`: PASS;
- validation log SHA-256:
  `320dc15394cee0857fbdd00957c7a65520538364c1eec02dcd2a7468d211912a`.

## Boundaries

- `pptx-presentation` remains stable at its existing released artifact;
- `mcpgit-runtime` remains stable at its existing released artifact;
- no manifest, immutable artifact, stable channel or registry release changed;
- no MCPGit Program/image/instance release;
- normal consumers continue to follow `stable`; exact versions remain evidence
  and rollback pins, not application policy.

## Integration

Serialized integration target remained exact at
`906c41b18a11eb16c30b0875663e71ca3bdcf46b`. The fetched source
`8302aa343dba7a31e8bca52b418a138d6f914b7f` merged without conflicts.

The exact pre-evidence merge tree
`8c2c615628df7cb39f1bcbaf4c3e822de09b48e9` passed composition 4/4,
runtime Node 10/10 and Python release 107/107. Integration evidence is retained
in `integration-evidence.json`. The final evidence-bearing tree must pass the
same repository gate before the merge commit is pushed.
