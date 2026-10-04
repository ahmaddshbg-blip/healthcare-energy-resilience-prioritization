# Staging Checkpoints

## Purpose

The staging checkpoint is the private, traceable output of source-preserving
extraction. It isolates verified source parsing from later geography and
analytical work. It is not a county evidence table and contains no reconciled
identifier, criterion, score, portfolio membership, or county status.

`configs/staging_checkpoint.schema.json` defines the manifest. Generated
Parquet tables and manifests belong under the private data root and are ignored
by Git. `configs/staging_build.schema.json` separately defines the complete
frozen-build evidence envelope.

## File adapters

`src/healthcare_resilience/source_adapters.py` provides contract-driven readers
for CSV and XLSX tables. The adapters validate the contracted filename,
container, encoding, byte-order mark, CSV line ending, ordered header hash,
row width, row count, and workbook sheet set before feeding source mappings to
the staging extractor. Source rows are consumed as iterators and only required
staging columns are retained in memory; complete physical row width is still
validated. The adapters do not filter, sort, deduplicate, aggregate, trim, or
replace source values.

The adapters are library functions. They do not replace frozen snapshot hash
verification or the complete structural profile. The frozen-build command
performs those checks before invoking the adapters.

## Checkpoint layout

The atomic writer produces a checkpoint inside this content-addressed private
build structure:

```text
<data-root>/checkpoints/<snapshot-id>/source_preserving_staging/<build-id>/
  staging_build_manifest.json
  checkpoint/
    staging_checkpoint_manifest.json
    tables/
      stg_<source-content>.parquet
```

The target directory must not already exist. Files are first written to a
sibling temporary directory. The writer validates the manifest, rereads each
Parquet table, compares its canonical content hash, and verifies every artifact
size and SHA-256. Only then is the complete checkpoint directory published by
an atomic rename. The enclosing build is also created under a sibling temporary
path and published only after independent verification. A failed write removes
temporary output and cannot overwrite an accepted build.

## Manifest lineage

The manifest records:

- source snapshot identity;
- source, source-table, and staging-table contract SHA-256 values;
- exact staging-table order and private relative paths;
- row and column counts;
- ordered output columns, parser types, and null policies;
- observed ordered DuckDB/Parquet physical types;
- separate logical and physical schema hashes plus a combined schema hash;
- a canonical typed-row SHA-256 for each table; and
- the local Parquet byte count and file SHA-256.

Timestamps and absolute machine paths are excluded, so identical inputs in the
same locked environment produce the same manifest. Decimal scale is normalized
for canonical hashing: numerically equal values such as `11`, `11.0`, and
`11.00` have one semantic identity without conversion to binary floating point.

Before writing, every value is checked against its logical type and null
policy. After writing, the independent verifier opens each Parquet artifact and
recomputes ordered physical schema, row count, consecutive source-row lineage,
canonical typed content, byte count, and file hash. Manifest assertions are not
accepted as evidence for themselves.

The Parquet file hash is exact evidence for a local artifact, but it is not
promised to remain identical across library builds or operating systems. The
canonical typed-row hash is the cross-environment comparison target. This
staging manifest does not impersonate the build manifest.

## Frozen-build orchestration

`scripts/build_staging_checkpoint.py` is the only real frozen-staging entry
point. It fails unless the public repository is committed and clean, records
the commit plus the exact lock hash and runtime dependency versions, verifies
the source snapshot before and after extraction, validates all eight source
tables, writes all six staging tables, independently verifies the complete
checkpoint, and publishes a terminal `COMPLETE` build manifest last.

The build identity is derived from the snapshot, three contract hashes, clean
commit, dependency lock, Python and platform identity, and direct dependency
versions. Existing content-addressed output is never overwritten. A successful
staging build proves typed source-preserving conversion only; it does not prove
geography comparability or produce an analytical decision.

## Current evidence

Tests use invented LF-terminated CSV and XLSX inputs. They cover both
adapter families, retained-column streaming from wide rows, source order, blank
and repeated values, strict logical types and nullability, header and line-
ending drift, unexpected workbook sheets, row-count drift, logical and physical
schema identities, independent Parquet content verification, deterministic
manifests, atomic failure cleanup, overwrite refusal, dirty repositories,
mid-build source mutation, commit mutation, and artifact or manifest tampering.

After the readiness review and explicit authorization, the command ran exactly
once against the accepted snapshot at code commit
`177f6d372ed6c200dc94137fb8050e10abc1bded`. The resulting private build has
identity
`238da712ad4a9d08b602e89ae8eaa2446871de1e6d84f2dc162ac8a69c5f3b0d`.
Independent verification reopened all six Parquet artifacts and confirmed
112,370 rows, 1,654,006 artifact bytes, exact eight-file build membership,
logical and physical schemas, consecutive source-row lineage, canonical typed
content, and local file hashes. Snapshot verification remained 15 of 15 with
zero failures, and all eight source-table structures remained valid.

The build and checkpoint manifests are private because they describe generated
artifacts under the private data root. Their public evidence fingerprints are:

- build-manifest file SHA-256:
  `88a9f1ccdfed0cc56993afa7e054c7d81fbe49261dc5a49655a1fc74d3c1b6d6`;
  and
- checkpoint-manifest file SHA-256:
  `e2f7818b159120eb0a81cf16f6db66ec574f9a6a7d1f914efcf91688ce89c43f`.

No private path or source value is published. One separately authorized
geography attempt later failed closed on the contracted
`DIRECT_REFERENCE` count for `stg_hhs_empower_history_county`; no geography
checkpoint was published. County evidence and all analytical calculations
remain unimplemented.
