---
id: maintainer:pptx-presentation
name: pptx-presentation-maintainer
kind: maintainer-skill
description: "CodeAgent-first architecture, capability-admission, validation, and release rules for maintaining pptx-presentation."
disclosure: on_demand
lifecycle: active
authority: source:mcpgitrelease
metadata:
  consumer-skill: ../../../web-components/pptx-presentation/SKILL.md
  source: ../../../web-components/pptx-presentation/src/index.js
  release-indexer: ../../../scripts/index_skills.py
---

# pptx-presentation Maintainer Skill

Read this Skill when changing the runtime implementation or deciding whether a
new behavior belongs in the public component. Do not use it as the consumer API
contract; that authority is web-components/pptx-presentation/SKILL.md plus the
released manifest.

## Runtime charter

pptx-presentation is a thin Presentation Runtime for CodeAgent. It is not a
presentation DSL, template DSL, workflow framework, or configurable application
shell.

The runtime exists to make browser/renderer mechanics reliable while preserving
the ability of increasingly capable CodeAgents to express presentation policy
with ordinary JavaScript.

Long-term invariant: as CodeAgent capability increases, the runtime should
remain a stable floor, not become a ceiling.

## Mechanism versus policy

Runtime mechanism may include:

- projection execution and PPTX byte lifecycle;
- renderer open/render/resize/cleanup mechanics;
- load sequencing, cancellation and stale-result protection;
- browser fullscreen compatibility and resource cleanup;
- small imperative navigation/state primitives;
- reusable cross-instance coordination that cannot be expressed safely by
  independent instances;
- observable lifecycle/error events needed for host composition.

Application policy normally belongs in deck.js, host code, or other ordinary
JavaScript:

- visual layout and theme decisions;
- toolbar composition and placement;
- keyboard mappings and navigation policy;
- click/focus policy;
- autoplay/workflow behavior;
- presentation-specific state machines;
- business facts, provenance, joins, and templates.

Do not move policy into the runtime merely because it is convenient to expose
as a component option.

## Capability admission gate

Before adding a public method, event, attribute, state field, or implicit
behavior, answer these questions in order:

1. Can capable host/deck JavaScript express this clearly and reliably?
   If yes, keep it in ordinary code by default.
2. Does it cross a browser, renderer, binary/resource, cancellation, or
   cross-instance boundary that consumers would otherwise reimplement
   incorrectly?
   If yes, a runtime primitive may be justified.
3. Do multiple independent consumers need the same stable interoperability
   contract?
   If yes, prefer a small imperative primitive or event.
4. Would fixing this behavior reduce the solution space of a stronger future
   CodeAgent?
   If yes, keep the mechanism open or move the decision back to host code.

No new public surface is admitted solely because an option is easy to add.

## Interface preference

When a capability is justified, prefer the least constraining representation:

ordinary JavaScript > imperative primitive > observable event > declarative
attribute > configuration DSL.

This is a preference order, not a ban on attributes. Attributes are appropriate
for small declarative bootstrap state when they do not constrain composition.
Configuration growth is not a substitute for a programmable host API.

## Consumer / projection / maintainer authority

Keep the three roles separate:

- Consumer Skill: web-components/pptx-presentation/SKILL.md documents the
  released API and how an external CodeAgent uses it.
- Projection Developer Skill: the source workspace, currently YXSGIT/Works
  pptx-source-preview-poc/SKILL.md, owns deck/fact-binding development and
  decides whether a problem is projection-side or a demonstrated runtime gap.
- Maintainer Skill: this file owns architecture invariants, admission rules,
  change procedure, and release discipline.

Dynamic task state, current candidates, blockers, PR numbers, and evidence do
not belong here. They belong in the task/handoff authority.

## Change procedure

1. Read the current public Consumer Skill and stable manifest.
2. Classify the requested change as projection, host policy, runtime mechanism,
   or release/governance work.
3. If ordinary JavaScript is sufficient, do not enlarge the public runtime
   contract.
4. For a runtime primitive, implement the smallest composable mechanism and
   avoid embedding application policy.
5. Add focused regression tests for the primitive and its negative boundaries.
6. Run real browser behavioral E2E for browser-facing semantics; HTTP success,
   module import, build success, or Promise resolution alone are not acceptance.
7. Only after behavior is accepted, update the public manifest and Consumer
   Skill together.
8. Run the public Skill coverage gate and repository test suite.
9. Publish through the immutable artifact/registry/tag/channel path and record
   integrity evidence.

## Public-contract discipline

- Source implementation may lead stable while a candidate is under test.
- Stable manifests and Consumer Skills describe released behavior, not
  unaccepted candidates.
- Every released public method/event/attribute/state field must be visible to
  the Consumer Skill coverage gate.
- Maintainer-only concepts must not be added to the public Skill index.
- Convenience helpers should remain private until repeated evidence proves a
  reusable runtime gap.

## Review checklist

Reject or redesign a change when any of these are true:

- it creates a mini-language for behavior ordinary JavaScript already expresses;
- it adds parameters mainly to avoid letting CodeAgent write code;
- it hard-codes one deck/application's policy into the generic runtime;
- it makes a default impossible to override through composition;
- it claims browser correctness without behavioral/visual evidence;
- it updates a machine contract without the public Consumer Skill;
- it records transient task state as a permanent architecture rule.

Prefer subtraction over expansion when an existing runtime option has become
redundant with a clean primitive plus normal host code.
