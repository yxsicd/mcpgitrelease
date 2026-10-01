---
id: maintainer:mcpgitrelease
name: mcpgitrelease-maintainer
kind: maintainer-registry
description: "Repository-local maintenance guidance intentionally excluded from the public consumer Skill index."
disclosure: on_demand
lifecycle: active
authority: source:mcpgitrelease
metadata:
  pptx-presentation: ./skills/pptx-presentation-maintainer/SKILL.md
  mcpgit-runtime: ./skills/mcpgit-runtime-maintainer/SKILL.md
---

# mcpgitrelease Maintainer Skills

This tree is for Agents changing source, tests, release machinery, or public contracts.
It is not part of the public consumer Skill registry.

## Routing

- When changing web-components/pptx-presentation/**, read
  ./skills/pptx-presentation-maintainer/SKILL.md before editing runtime behavior
  or extending its public contract.
- When changing web-components/mcpgit-runtime/**, read
  ./skills/mcpgit-runtime-maintainer/SKILL.md before editing runtime behavior
  or extending its public contract.
- Consumer-facing usage remains authoritative in
  ../web-components/pptx-presentation/SKILL.md,
  ../web-components/mcpgit-runtime/SKILL.md, and
  ../web-components/AGENT_COMPOSITION.md.

## Separation rule

Offline installer extraction must mirror the canonical source extractor. The only
admitted archive alias is `tools/bin/bunx -> bun`, and only with a regular
`tools/bin/bun` in the same archive. Other symlinks, hardlinks, duplicate members,
traversal, missing targets and pre-existing alias destinations remain denied.
Run `tests/test_offline_extract_links.py` plus `scripts/validate.sh` before
publication, then repeat a fresh public candidate install. An existing-instance
Program upgrade does not prove the public new-instance installer works.

Public built-in bootstrap also mirrors the canonical source shared `mcpadmin`
Person policy: separate connect/control/scoped business grants, no SafeGit grant,
no password/API key/SSO identity, preserve an explicitly provisioned UUID, and
reject disabled/ambiguous Persons or changed/revoked grants instead of restoring
authority silently. The valid Basic entrance remains the permission ceiling.

Public Skills answer how to use a released capability.
Maintainer Skills answer why the capability boundary exists, what may enter it,
and how to change/release it safely.

Do not copy maintainer rationale into the public consumer contract unless it is
required for correct use.
