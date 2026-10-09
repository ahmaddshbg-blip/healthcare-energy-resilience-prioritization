# County Evidence Build Evidence

## First Authorized Attempt

On 2026-10-09, the user authorized exactly one controlled frozen county-
evidence build against the accepted private staging and geography checkpoints.
The authorized code commit was
`31751f6d478a41373c5f601de6ffb6581bbd3abe`.

## First Outcome

**FAILED CLOSED BEFORE PRIVATE INPUT ACCESS.**

The production entrypoint stopped during its first repository-identity check.
Git rejected the worktree ownership because the subprocess did not carry the
command-scoped `safe.directory` used by the surrounding execution environment.
The failure occurred before staging or geography manifest verification, source
measure extraction, transformation, or checkpoint publication.

Post-failure inspection confirmed:

- the county-evidence output root did not exist;
- zero output items or temporary checkpoint directories existed;
- no manifest or Parquet artifact was published; and
- no criterion, score, portfolio, or county status was calculated.

The attempt consumed its authorization and was not rerun.

## Root Cause and Remediation

The shared Git helper invoked `git` without a repository-specific safety
override. The remediation adds
`-c safe.directory=<resolved-public-repository>` to each internal Git command.
This setting is process-local and does not modify global Git configuration.

The fix is recorded at commit
`85cdd0e4f3b7dbbc9f133133e3d98e82d302ecca`. Verification includes:

- a unit test proving the exact command-scoped Git arguments;
- 22 focused staging, checkpoint, and evidence-input tests;
- the full suite passing 145 tests;
- successful Python compilation and contract validation; and
- a live clean-worktree repository-identity capture returning the remediation
  commit on the Windows host.

## Second Authorized Attempt

After the Git remediation and a new explicit authorization, exactly one second
controlled build was started on 2026-10-09 at public commit
`7dd7d0a28e2121a1feeebb74847be34fa92ce962`.

**FAILED CLOSED DURING GEOGRAPHY MANIFEST VERIFICATION.** The accepted private
geography manifest records build-time geography-contract SHA-256
`6f815c44fc4f74351d78dfc69a7b42d2fae397776efe5864f9d7fac8ec562e1e`,
while the public geography contract then had SHA-256
`5f61e313523aec2a0d13848f1e01c97a64b1cf048d403d32592a8cfce69a287c`.
The verifier correctly refused to treat those identities as interchangeable.

Read-only diagnosis proved that the only byte and semantic difference was the
geography specification-review identity. The checkpoint was built with review
SHA-256
`8cb0c28375a71304316844c86298ad5dda5621cd5dce4272fcd9c4e35d667a62`;
the current contract records the later documentation-only review SHA-256
`a6dd22b06b0ec27761b85f12ad13b154317f99a0f7a518df46a3c02a6d910a9e`.
Replacing exactly that one 64-byte value in the current contract reproduces
the build-time contract hash. No mapping rule or reference-universe field
changed.

Post-failure inspection found no county-evidence output root, manifest,
Parquet file, or temporary checkpoint. The attempt consumed its authorization
and was not rerun.

## Contract-Lineage Remediation

The county-evidence contract now binds both the current public geography
contract and the historical contract recorded by the accepted checkpoint. The
verifier reconstructs the historical contract only by one declared exact-byte
substitution, validates its schema and semantics, and requires the resulting
hash to equal the manifest-bound identity. Any other current-contract change,
wrong review identity, or wrong historical hash fails closed.

The future county-evidence manifest also records both geography-contract
identities and the historical specification identity. This preserves an
auditable distinction between current public documentation and immutable
checkpoint provenance.

Public validation after the remediation reports valid contracts, successful
Python compilation, 35 focused contract and county-evidence tests, and all 149
repository tests passing.

## Current Decision Boundary

Both prior authorizations are consumed and neither produced county evidence.
After the lineage remediation passes the full public test suite and a live
read-only private-input verification, any new build still requires a new
explicit authorization. No criterion, score, portfolio, or county status may
be calculated.
