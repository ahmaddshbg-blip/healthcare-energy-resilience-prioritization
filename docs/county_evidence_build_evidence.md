# County Evidence Build Evidence

## Authorized Attempt

On 2026-10-09, the user authorized exactly one controlled frozen county-
evidence build against the accepted private staging and geography checkpoints.
The authorized code commit was
`31751f6d478a41373c5f601de6ffb6581bbd3abe`.

## Outcome

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

## Current Decision Boundary

Synthetic readiness is restored for exactly one new controlled frozen county-
evidence build. A new explicit user authorization is required. Any future
authorized attempt must independently verify its manifest and Parquet artifact
and stop before criteria, scores, portfolio construction, or county status.
