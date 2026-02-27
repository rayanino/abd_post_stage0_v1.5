# Taxonomy Registry

This folder contains **canonical** taxonomy YAML files for each science and version. Each YAML defines a folder structure for one science: the root key is the science name (= root folder), branches become subfolders, and `_leaf: true` nodes become the endpoint folders where excerpt files are placed.

- The authoritative index is `taxonomy_registry.yaml`.
- Baseline passage packages may include local taxonomy snapshots for reproducibility.

**The taxonomy is alive.** Trees evolve as books reveal finer topic distinctions. Evolution is LLM-driven with human approval. See `5_taxonomy/TAXONOMY_SPEC.md` for the full evolution model.

**Current trees (v1.0 — all 4 sciences):**

| Science | File | Leaves | Branches | Notes |
|---------|------|-------:|----------|-------|
| إملاء | `imlaa/imlaa_v1_0.yaml` | 105 | 30 | Expanded from 44-leaf v0.1 |
| صرف | `sarf/sarf_v1_0.yaml` | 226 | 63 | New |
| نحو | `nahw/nahw_v1_0.yaml` | 226 | 56 | New |
| بلاغة | `balagha/balagha_v1_0.yaml` | 335 | 90 | Expanded from 143-leaf v0.4 |
| **Total** | | **892** | **239** | |

**Historical trees (retained for gold baseline reproducibility):**
- `imlaa_v0.1.yaml` — إملاء (44 leaves), used during early extraction testing
- `balagha/balagha_v0_2.yaml` through `balagha_v0_4.yaml` — earlier بلاغة versions from gold baselines

## Snapshot policy

- `ABD/taxonomy/**` = canonical taxonomy sources.
- `.../passageX_*/balagha_v0_Y.yaml` = snapshot copy used during that baseline's validation.
- Snapshots MUST be byte-identical to the canonical file for that `taxonomy_version`.

The validator enforces snapshot identity when both are present.
