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
---

# mcpgitrelease Maintainer Skills

This tree is for Agents changing source, tests, release machinery, or public contracts.
It is not part of the public consumer Skill registry.

## Routing

- When changing web-components/pptx-presentation/**, read
  ./skills/pptx-presentation-maintainer/SKILL.md before editing runtime behavior
  or extending its public contract.
- Consumer-facing usage remains authoritative in
  ../web-components/pptx-presentation/SKILL.md.

## Separation rule

Public Skills answer how to use a released capability.
Maintainer Skills answer why the capability boundary exists, what may enter it,
and how to change/release it safely.

Do not copy maintainer rationale into the public consumer contract unless it is
required for correct use.
