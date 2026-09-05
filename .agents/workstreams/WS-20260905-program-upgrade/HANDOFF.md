# Fresh install and long-lived Program-only upgrades

State: complete / ready for serialized integration.

The user prioritizes first installation and subsequent application-only updates.
Keep Base/Tools and data/config/credentials stable. A strict Program-only request
must fail if the selected cold layers are incompatible or trustworthy installed
evidence is absent. A full first install records an exact image-bound baseline.
Do not grow an unbounded parent chain across repeated Program updates.

Use ordinary local scripts and Git; no Actions or hwlinux performance resources.
The retained ddtry instance is the authorized real WSL test target. Preserve its
committed sentinel, volume, identity, credential and existing network exposure.
Read current remote state before integration; a source push does not move any
runtime release pointer. Container rollback does not imply data-format rollback.

Local validation passes 85 tests. scripts/install_state.py now supplies strict
pointer/manifest selection, private image-bound receipts and full/exact/program
planning. The public installer downloads only Program in the compatible path,
uses one fixed parent and streamed Docker build context, performs authenticated
MCP acceptance before recording success, and retains old containers on failure.
CLI upgrade now delegates to the public root with preserved installation paths;
backup exits 2. New smoke preflight rejects existing resources without cleanup.
Default first-install bind is loopback; existing exposure is retained.
Two former static string checks were updated to the new selector/helper paths;
the actual pointer, archive, runtime and auth tests are not relaxed.

Next validate ddtry baseline adoption, warm replay without cold archives, a
controlled Program replacement/negative recovery, and a fresh isolated install.
No actual cross-version compatibility evidence is claimed yet. Keep all current
published binary tags, channels and the hwlinux optimization work unchanged.

Real WSL baseline adoption passed without recreating ddtry. Online exact replay
passed in 11.961 seconds; an offline replay with every local layer archive moved
aside passed in 6.667 seconds without download/unpack. All original identity,
credential, configuration, binding and committed-sentinel checks passed.
The original archives were restored. These are single-run observations, not
performance benchmarks or cross-version qualification. Transaction cleanup now
uses a candidate nonce/exact old ID and retains private failed-attempt evidence;
the next exact-code qualification must retain this distinction.

The ec9c49e controller passed actual Docker Program rejection/restoration, two
successive Program-only replacements and a return to the original public image.
Both successive images had eight RootFS layers and the deliberately removed
Program file did not survive. These were controlled archive changes using the
existing valid native binaries, not a new compiled release or schema migration.
The latest local 86-test gate adds refusal of unreplayable custom process/env/
resource/security overrides, preserves disabled build capability, validates the
existing credential before stopping its writer, and bounds network health probes.
Final-source fresh-install and repeated qualification remain required before merge.

Final 6dfe986 replay refused the unchanged ddtry before mutation because Docker
reported null image User/WorkingDir versus empty container strings. The narrow
default-string normalization now accepts only this equivalence, with regression
coverage; custom users, directories, process argv and resource overrides remain
rejected. All original ddtry identity/data/credential/sentinel checks stayed true.

Final implementation 32e0507588a512d9166fb4d4afe7339ca9a0f5c6 passes 86
local public-repository tests and ten real WSL cases. Exact warm replay passes
without unpack/download; a broken Program restores the exact previous container;
two successive Program-only archive replacements keep one fixed foundation and
eight image layers, remove an obsolete Program file, then return to the original
public image. Wrong manifest pin, missing baseline, changed cold layer and missing
credential fail before changing the retained writer. Fresh install from a new
download directory uses loopback binding, random private credentials, automatic
read-only MCP acceptance and a valid installation receipt. Explicit post-install
write/readback and doctor pass. The host already had Docker image cache.

Exact script hashes and cases are in docs/evidence/program-upgrade-wsl-20260905.json.
All nine pre-existing other container IDs remain unchanged. No runtime release
or pointer, private Rust source, authorization policy, or hwlinux resource changed.
These Program fixtures change package contents, not compiled product versions;
real cross-version/data-format migration and rollback remain unqualified.
After integration, re-download public main and exercise mcpgitctl upgrade/check.
