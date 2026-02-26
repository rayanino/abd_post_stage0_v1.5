# Passage 1 — Deep QA Report (no-regret baseline)

This report is a **derived audit note** for quick human review.
Authoritative validation status is the `validation` block inside `passage1_metadata.json`.

## Validation (from metadata)
- Baseline: `v0.3.13`
- Validator: `validate_gold.py` v0.3.12
- Result: PASS
- Warnings: 0
- Errors: 0
- Decisions log: included (`passage1_decisions.jsonl`, 21 excerpt_decision records)

## Structural invariants (spot checks)
- Excerpts: 21
- Exclusions: 26
- Atoms: 95 (matn 59, footnote 36)

### Leaf enforcement
- Excerpt nodes missing `leaf: true`: 0

### Heading dual-state
- Heading atoms appearing in core/context: 0

### Layer purity
- Cross-layer atom contamination: 0

### Cross-science labeling
- Excerpts with `cross_science_context=true`: 5
- Sciences involved: sarf

## Cross-passage relations
External excerpt targets referenced in relations:
- (none)

## Traceability completeness
- Every excerpt has labeled-block `boundary_reasoning` (GROUPING/BOUNDARY/ROLES/PLACEMENT/CHECKLIST/ALTS).
- Every excerpt has exactly one placement decision record (PLACE.P1–P8).

## Reproducibility
- `baseline_manifest.json` contains sha256+sizes for baseline files and a baseline_sha256 anchor.
- CP6 also records tool and key-file hashes in `checkpoint_outputs/cp6_tool_fingerprint.json`.
