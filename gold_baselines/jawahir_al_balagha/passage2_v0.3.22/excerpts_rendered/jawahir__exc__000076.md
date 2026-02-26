<!-- GENERATED FILE — DO NOT EDIT. -->
<!-- renderer=v0.3.7 -->
<!-- inputs: 2d37079676aabc0d excerpts=passage2_excerpts_v02.jsonl:6d4ccb35b7a0 atoms=passage2_matn_atoms_v02.jsonl:9abe4467c5c1 atoms=passage2_fn_atoms_v02.jsonl:fb1c94d22e90 -->

# jawahir:exc:000076 — جواب — (9) بوقات مزامير - والقياس في جمعه أبواق.

- excerpt_id: `jawahir:exc:000076`

## Metadata
- book_id: `jawahir`
- source_layer: `footnote`
- excerpt_kind: `exercise`
- taxonomy_version: `balagha_v0_3`
- taxonomy_node_id: `tatbiq_fasahat_alfard`
- taxonomy_path: مقدمات > الفصاحة > فصاحة المفرد > تطبيقات فصاحة المفرد
- excerpt_title_reason: Auto-generated v1: '<excerpt_id> — <kind_label> — <first 10 tokens of first core atom>' (whitespace-normalized) for deterministic uniqueness under taxonomy_node_id.
- exercise_role: `answer`
- tests_nodes: 3uyub_alfard_mukhalafat_qiyas
- primary_test_node: `3uyub_alfard_mukhalafat_qiyas`
- case_types: B1_clean_boundary, C1_scholarly_footnote, C2_exercise_section, D1_clean_single_node, D4_cross_science
- cross_science_context: `true`
- related_science: `sarf`
- rhetorical_treatment_of_cross_science: `false`

## Relations
- `answers_exercise_item` → `jawahir:exc:000026`
- `belongs_to_exercise_set` → `jawahir:exc:000013`

## Source spans
- canonical: `passage2_fn_canonical.txt`
- spans:
  - core[1542..1583]

## Boundary reasoning (canonical JSONL field)
```
GROUPING: Answer footnote excerpt (exercise_role=answer) for exercise item jawahir:exc:000026; kept as the smallest self-contained scholarly judgment unit in the footnote layer.
BOUNDARY: Starts at core atom jawahir:fn:000050 and ends at jawahir:fn:000050. Boundary aligns with the smallest self-contained unit for this answer in the footnote layer.
ROLES: All core atoms are role=exercise_answer_content (author's judgment/explanation that constitutes the answer).
PLACEMENT: Per PLACE.X3, exercise items/answers are placed at leaf node 'tatbiq_fasahat_alfard' (taxonomy_version balagha_v0_3); the specific defects tested are encoded in tests_nodes.
RELATIONS: answers_exercise_item → jawahir:exc:000026; belongs_to_exercise_set → jawahir:exc:000013.
TESTS: tests_nodes=['3uyub_alfard_mukhalafat_qiyas']; primary_test_node=3uyub_alfard_mukhalafat_qiyas.
CHECKLIST: EXC.B1, EXC.B6, EXC.L1, EXC.C5, EXC.R3
ALTS: Alternative: keep as generic footnote teaching under the defect leaf with footnote_explains. Rejected because this footnote is functioning as an exercise answer key; per PLACE.X3 we encode it as exercise_role=answer at the tatbiq_ leaf, with defects captured in tests_nodes.
```

## Core atoms
- `jawahir:fn:000050`  (type=prose_sentence, role=exercise_answer_content)
  (9) بوقات مزامير - والقياس في جمعه أبواق.

## Context atoms
(none)
