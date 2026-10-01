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
The public pushed extractor subsequently passed real fresh candidate installation,
health/doctor/standard registry/credentials/init/tools-list; the fixture container
and data were cleaned through the exact identity fence. The first failed bundle
remains evidence. No published candidate assets were altered.

Follow-up parity review found the public bootstrap also omitted canonical shared
`mcpadmin` provisioning. The mirrored helper preserves existing UUIDs, separate
connect/control/business grants, Basic ceilings and revoked-authority rejection.
Six focused bootstrap tests pass, including zero-write replay and disabled/changed
grant negatives. Complete public gate exits0:125 Python tests and10 component
tests. Both public bootstrap and extractor now exactly match canonical source.
Public snapshot `0b9a1012b09f72b22759cae5210ae40a44f1f522` passed a second
real fresh candidate install. Four Hosted profiles default to mcpadmin;
chooser includes mcpadmin/builder, selection and readback pass, cross-origin
and unknown-Person POST are403, anonymous config is401. This is loopback
HTTP acceptance with an actual Hosted Host, not a full browser visual gate.

Reviewed native source `2c3e42c837b1467f039696d6302373d80d8540a9` passed
local Full and assigned native hwlinux Full, both native production builds,
immutable dual-architecture publication/readback and all six ordered pinned
stages with health and official SDK gates. DEV pointer advances to that exact
pair. MAIN now copies the exact reviewed DEV pair; PROD remains unchanged.
