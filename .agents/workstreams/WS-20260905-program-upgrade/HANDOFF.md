# Fresh install and long-lived Program-only upgrades

State: implementation-complete / not-ready for integration; real WSL gates pending.

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
real replacement and fresh-install tests are still pending on that final code.
