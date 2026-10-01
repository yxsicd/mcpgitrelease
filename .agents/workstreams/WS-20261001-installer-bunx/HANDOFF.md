# Public installer Tools alias compatibility

The fresh immutable candidate install rejected `tools/bin/bunx` while archive
hash verification passed. Public extraction lagged the canonical product helper.
Only the reviewed relative alias to the same-archive regular Bun is admitted;
all other link/traversal/member rules remain unchanged. Eight regression tests
cover the positive path and rejected alias names/targets, missing/non-regular Bun,
hardlinks, duplicates, Program-root aliases and existing destinations.

Focused extraction tests pass8/8; complete `scripts/validate.sh` exits0 with
120 Python tests and10 runtime component tests. The public helper is byte-identical
to the canonical product helper. Next: push the ordinary installer checkpoint,
then retry fresh public installation under a new disposable instance identity.
Keep the first failed downloaded bundle/log as evidence; do not alter published
candidate assets or claim live Program/channel activation.
