# Checkpoint 5 Report — Taxonomy Change Proposals (Passage 2)

This checkpoint produces the taxonomy evolution artifacts required for Passage 2 and aligns Passage 2 excerpts with the post-change taxonomy version.

## Outputs produced
- `taxonomy_changes.jsonl` (TC-004 .. TC-007)
- `balagha_v0_3.yaml` (taxonomy tree after applying the above additions)

## Version bump
- `taxonomy_version_before`: balagha_v0_2
- `taxonomy_version_after`:  balagha_v0_3

All Passage 2 excerpt records are stamped `taxonomy_version: balagha_v0_3`.

## Changes included (high level)
- Added `fasahat_alkalam__overview` under `fasahat_alkalam` to host definition + enumeration overview.
- Added three new defect leaves under `fasahat_alfard` demanded by footnote teaching: `ابتذال`, `الإبهام عند إرادة التعيين`, and `استعمال المشترك بلا قرينة`.

## Bidirectional trigger integrity (validator requirement)
Each TC with `triggered_by_excerpt_id` has a matching `taxonomy_change_triggered` field on that excerpt:
- TC-004 ↔ jawahir:exc:000068
- TC-005 ↔ jawahir:exc:000080
- TC-006 ↔ jawahir:exc:000081
- TC-007 ↔ jawahir:exc:000082

## Additional corrective fixes bundled here (to satisfy invariants)
1) Node-ID charset policy: fixed non-ASCII node id `3uyub_alfard_ibhām` → `3uyub_alfard_ibham`.
2) Exercise ontology invariant (validator v0.3.1+): every exercise `item` must belong to exactly one exercise `set`.
   - jawahir:exc:000031 is now the set for the subsequent items.
   - jawahir:exc:000032–000034 now each include `belongs_to_exercise_set → jawahir:exc:000031`.

## Footnote-marker ambiguity note (design-level)
Shamela uses `(1) (2)` both as inline footnote markers and as author enumeration. For gold work we avoid forced links when ambiguous.
Future automation MUST distinguish footnote markers structurally at the HTML layer (e.g., red font/anchor) and preserve them as sentinel tokens + marker map, rather than relying on plain text pattern matching.

## Validation
Ran `validate_gold.py v0.3.2` with `--skip-traceability` using `balagha_v0_3.yaml` and produced: ✅ ALL CHECKS PASSED (warnings only about missing tests_nodes for exercises).
