# Geography Build Evidence

## Decision Boundary

On 2026-10-04, exactly one controlled frozen geography build was authorized
against the accepted private staging checkpoint. The build completed and its
output manifest and six Parquet artifacts passed independent read-only
verification. This evidence covers geography checkpoint integrity only. It
does not create joined county evidence, analytical criteria, scores,
portfolios, or county statuses.

## Frozen Input Identity

- Source snapshot ID:
  `cc1489ab008db4d5d1b2eddf798b51218e2324e97e88ab9c7d3853927bb54dbb`
- Staging build identity:
  `238da712ad4a9d08b602e89ae8eaa2446871de1e6d84f2dc162ac8a69c5f3b0d`
- Staging build manifest file SHA-256:
  `88a9f1ccdfed0cc56993afa7e054c7d81fbe49261dc5a49655a1fc74d3c1b6d6`
- Staging checkpoint manifest canonical SHA-256:
  `676727dfa8a91e5ab1225a8a01eb7b2f1df04465fd57ac714dd6ac54efc3b203`
- Staging checkpoint manifest file SHA-256:
  `e2f7818b159120eb0a81cf16f6db66ec574f9a6a7d1f914efcf91688ce89c43f`

The post-build staging-input verification reproduced these identities. The
historical HHS table remained source-preserved in staging and produced no
geography map.

## Geography Checkpoint

- Checkpoint identity:
  `2ccef71e269fd9ccb8218ac316161076db67cc7de7303085b777de45bb10ad0a`
- Geography manifest canonical SHA-256:
  `2bdc296c2567ea4f471b2baff0675aa33cf848b387dc4c36ead9a1133847bc10`
- Geography manifest file SHA-256:
  `8724266f2bbc8010cdabdec3bd8ef7bd6b52721d9c031b20b3e0927da84eabf5`
- Status: `VALID`
- Build-time geography contract SHA-256 recorded by the checkpoint:
  `6f815c44fc4f74351d78dfc69a7b42d2fae397776efe5864f9d7fac8ec562e1e`
- Current public geography contract SHA-256 after a documentation-only
  specification-review update:
  `5f61e313523aec2a0d13848f1e01c97a64b1cf048d403d32592a8cfce69a287c`
- Artifact count: `6`
- Total row count: `112286`

| Artifact | Kind | Rows | Artifact SHA-256 |
|---|---|---:|---|
| `county_reference` | County reference | 3,144 | `9021628d385698ec4f13ccffa349d3cfa31cc0429d1519e7c1a0ebf3cc09c489` |
| `map_stg_census_county_population_2025` | Source geography map | 3,195 | `c783de6b24f8d0d3b542e04a41b5d64108a74bf8c5d73aa9fad39eeb2054b6ce` |
| `map_stg_hhs_empower_county` | Source geography map | 3,233 | `8cb95467b79ae4fe37c172ae246180aceb4725b2998637a9e7a011386eb2e24e` |
| `map_stg_fema_nri_counties` | Source geography map | 3,232 | `e1c21a6a224e2d967b330bc7a357563fdc8790dcd5a6da470a08555a12ccbdd4` |
| `map_stg_hrsa_primary_care_hpsa` | Source geography map | 80,199 | `a0dd02cfb06c82acb39efb7856b657a31206aeb6792a50a0c514e09828baa8f4` |
| `map_stg_hrsa_health_center_sites` | Source geography map | 19,283 | `f9c05587000228883c4b2e1f0d8deadf24f8054649c31d6f72deefe71c1a2f7a` |

The verifier reproduced the stored manifest, exact file membership, file byte
counts, artifact hashes, logical and physical schemas, canonical row hashes,
row counts, source-row lineage, mapping counts, checkpoint semantics, and the
absence of symbolic links or unexpected files.

## Stopping Point

The checkpoint is verified for its stated geography scope. No source measure
was joined across tables, no HPSA or site record was aggregated, and no
criterion, score, portfolio, or county status was calculated. Any analytical
step requires a separate decision and must begin from this verified private
checkpoint without modifying it.
