# Taxonomy Registry

This folder contains **canonical** taxonomy YAML files for each science and version. Each YAML defines a folder structure for one science: the root key is the science name (= root folder), branches become subfolders, and `_leaf: true` nodes become the endpoint folders where excerpt files are placed.

- The authoritative index is `taxonomy_registry.yaml`.
- Baseline passage packages may include local taxonomy snapshots for reproducibility.

**The taxonomy is alive.** Trees evolve as books reveal finer topic distinctions. Evolution is LLM-driven with human approval. See `5_taxonomy/TAXONOMY_SPEC.md` for the full evolution model.

**Current trees:**
- `imlaa_v0.1.yaml` — إملاء (44 leaves), built from قواعد الإملاء
- `balagha/balagha_v0_4.yaml` — بلاغة (202 nodes, 143 leaves)
- صرف — not yet created
- نحو — not yet created

## Snapshot policy

- `ABD/taxonomy/**` = canonical taxonomy sources.
- `.../passageX_*/balagha_v0_Y.yaml` = snapshot copy used during that baseline's validation.
- Snapshots MUST be byte-identical to the canonical file for that `taxonomy_version`.

The validator enforces snapshot identity when both are present.
