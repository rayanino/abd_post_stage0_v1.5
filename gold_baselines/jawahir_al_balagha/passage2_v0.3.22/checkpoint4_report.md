# Checkpoint 4 Report — Passage 2 v0.3.1

## Outputs produced
- passage2_excerpts_v02.jsonl (excerpt + exclusion records)

## Counts
- Excerpts total: 65
  - Exercise excerpts: 46
  - Teaching excerpts: 19
- Exclusions total: 38
  - Matn heading_structural: 7
  - Footnote apparatus/duplicate: 31

## Validation
- All excerpt records validate against `gold_standard_schema_v0.3.1.json` excerpt_record definition.
- All exclusion records validate against `gold_standard_schema_v0.3.1.json` exclusion_record definition.
- All relations have resolved `target_excerpt_id` (no null targets).
- Headings are metadata-only: all heading atoms in this passage are excluded as `heading_structural` and referenced only via `heading_path`.

## Taxonomy evolution flags (proposals in next checkpoint)
- TC-004 (فصاحة الكلام: add `__overview` leaf + missing عيب leaves): jawahir:exc:000068, jawahir:exc:000083, jawahir:exc:000084
- TC-005 (فصاحة المفرد: add الابتذال / الإبهام / المشترك بلا قرينة): jawahir:exc:000080, jawahir:exc:000081, jawahir:exc:000082

## Critical ambiguity note: (1)(2) in matn vs true footnote markers
This gold set preserves authorial enumerations like (1)(2) inside matn atoms.

For automation, true footnote markers must be detected structurally in HTML (red/anchor), and should be represented as non-ambiguous sentinels (e.g., ⟦FN:p29:03⟧) rather than relying on plain-text '(1)' patterns. This is a required robustness rule for the future extractor.

## Conservative choices (accuracy-first)
- No `exercise_tests` relations were emitted for Passage 2 exercise items to avoid speculative mapping where the defect is not explicitly labeled in-source.
- Footnote teaching excerpts use `footnote_explains` / `footnote_supports` only where the linkage is reliable.
- Footnote numbering conflicts were treated as unstable metadata; duplicates were excluded with reason `duplicate_content` and notes.


## Checkpoint 5 note
Taxonomy version for Passage 2 is finalized as `balagha_v0_3` with node additions recorded in `taxonomy_changes.jsonl` (TC-004..TC-007).
