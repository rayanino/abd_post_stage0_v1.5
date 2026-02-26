# Taxonomy Registry

This folder contains **canonical** taxonomy YAML files for each science and version.

- The authoritative index is `taxonomy_registry.yaml`.
- Baseline passage packages may include local taxonomy snapshots for reproducibility.

## Snapshot policy

- `ABD/taxonomy/**` = canonical taxonomy sources.
- `.../passageX_*/balagha_v0_Y.yaml` = snapshot copy used during that baseline's validation.
- Snapshots MUST be byte-identical to the canonical file for that `taxonomy_version`.

The validator enforces snapshot identity when both are present.
