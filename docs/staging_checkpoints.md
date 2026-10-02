# Staging Checkpoints

## Purpose

The staging checkpoint is the private, traceable output of source-preserving
extraction. It isolates verified source parsing from later geography and
analytical work. It is not a county evidence table and contains no reconciled
identifier, criterion, score, portfolio membership, or county status.

`configs/staging_checkpoint.schema.json` defines the manifest. Generated
Parquet tables and manifests belong under the private data root and are ignored
by Git.

## File adapters

`src/healthcare_resilience/source_adapters.py` provides contract-driven readers
for CSV and XLSX tables. The adapters validate the contracted filename,
container, encoding, byte-order mark, CSV line ending, ordered header hash,
row width, row count, and workbook sheet set before feeding source mappings to
the staging extractor. They do not filter, sort, deduplicate, aggregate, trim,
or replace source values.

The adapters are library functions, not a real-data command. They do not
replace frozen snapshot hash verification or the complete structural profile.
A future private execution command must complete those checks before invoking
the adapters.

## Checkpoint layout

The atomic writer produces this private structure:

```text
<checkpoint-directory>/
  staging_checkpoint_manifest.json
  tables/
    stg_<source-content>.parquet
```

The target directory must not already exist. Files are first written to a
sibling temporary directory. The writer validates the manifest, rereads each
Parquet table, compares its canonical content hash, and verifies every artifact
size and SHA-256. Only then is the complete directory published by an atomic
rename. A failed write removes the temporary directory and cannot overwrite an
accepted checkpoint.

## Manifest lineage

The manifest records:

- source snapshot identity;
- source, source-table, and staging-table contract SHA-256 values;
- exact staging-table order and private relative paths;
- row and column counts;
- ordered output columns, parser types, and null policies;
- a schema SHA-256 for each table;
- a canonical typed-row SHA-256 for each table; and
- the local Parquet byte count and file SHA-256.

Timestamps and absolute machine paths are excluded, so identical inputs in the
same locked environment produce the same manifest. Decimal scale is normalized
for canonical hashing: numerically equal values such as `11`, `11.0`, and
`11.00` have one semantic identity without conversion to binary floating point.

The Parquet file hash is exact evidence for a local artifact, but it is not
promised to remain identical across library builds or operating systems. The
canonical typed-row hash is the cross-environment comparison target. This
staging manifest also does not impersonate the future build manifest; commit
and environment identities still have to be added by reviewed orchestration
before real extraction.

## Current evidence

Tests use invented LF-terminated CSV and XLSX inputs only. They cover both
adapter families, source order, blank and repeated values, header and line-
ending drift, unexpected workbook sheets, row-count drift, deterministic
manifests, Parquet read-back, atomic failure cleanup, overwrite refusal, and
artifact or manifest tampering.

No accepted private source file has been opened by this implementation
increment and no private checkpoint has been produced. A real staging run
requires a separate review.
