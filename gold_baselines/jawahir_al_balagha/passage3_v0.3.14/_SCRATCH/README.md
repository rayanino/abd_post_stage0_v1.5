# _SCRATCH (NON-CANONICAL)

This folder is **not part of the gold baseline contract**.

Purpose:
- Preserve transient working artifacts (e.g., backup files created during patching) that might help audit history,
  **without polluting the baseline root** where future builders expect only contract-relevant artifacts.

Rules:
- Nothing under `_SCRATCH/` is consumed by `ABD/tools/validate_gold.py` or the CP1→CP6 pipeline.
- Do **not** reference `_SCRATCH/` content as authoritative in any spec-by-example reasoning.
- Canonical persisted artifacts remain the structured outputs at baseline root:
  - `*_atoms_*.jsonl`, `*_excerpts_*.jsonl`, `taxonomy_changes.jsonl`, `*_metadata.json`, `baseline_manifest.json`, taxonomy YAML.

## Snapshots
`_SCRATCH/snapshots/` contains **historical** passage-local copies of older governance/protocol docs.
They are preserved for provenance only and MUST NOT be treated as authoritative.
