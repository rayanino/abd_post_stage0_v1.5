<!-- GENERATED FILE — DO NOT EDIT. -->
<!-- renderer=v0.3.7 -->
<!-- inputs: bd6b805038c055e8 excerpts=passage1_excerpts_v02.jsonl:6cf61c853e48 atoms=passage1_matn_atoms_v02.jsonl:dc233edbd29f atoms=passage1_fn_atoms_v02.jsonl:30caeb9e543c -->

# تطبيق 5: غرابة استعمال «اصطراع» (ص ٢٥؛ matn 000059)

- excerpt_id: `jawahir:exc:000018`

## Metadata
- book_id: `jawahir`
- source_layer: `matn`
- excerpt_kind: `exercise`
- taxonomy_version: `balagha_v0_2`
- taxonomy_node_id: `tatbiq_fasahat_alfard`
- taxonomy_path: مقدمات > الفصاحة > فصاحة المفرد > تطبيقات فصاحة المفرد
- excerpt_title_reason: الاسم مأخوذ من عنوان العقدة (آخر عنصر في taxonomy_path) مع إضافة وسم وظيفي عند الحاجة (تعداد/ملخص/حاشية/تطبيق/جواب). وأُلحق به قيد مصدري ثابت لضمان تمييز الإخوة داخل العقدة الواحدة: (مدى الصفحات من page_hint عبر ذرات المقتطف؛ source_layer؛ مدى/قائمة أرقام atom_id في core_atoms).
- exercise_role: `item`
- tests_nodes: 3uyub_alfard_gharaba
- primary_test_node: `3uyub_alfard_gharaba`
- case_types: C2_exercise_section, C4_embedded_verse_evidence
- cross_science_context: `false`
- heading_path:
  - `jawahir:matn:000001`: مقدمة
  - `jawahir:matn:000002`: في معرفة الفصاحة والبلاغة
  - `jawahir:matn:000003`: الفصاحة
  - `jawahir:matn:000011`: فصاحة الكلمة
  - `jawahir:matn:000053`: تطبيق

## Relations
- `exercise_tests` → `jawahir:exc:000005`
- `belongs_to_exercise_set` → `jawahir:exc:000013`

## Source spans
- canonical: `passage1_matn_canonical.txt`
- spans:
  - core[4404..4450]

## Boundary reasoning (canonical JSONL field)
```
GROUPING: Single-topic excerpt grouped per taxonomy leaf `tatbiq_fasahat_alfard`. Cases=C2_exercise_section, C4_embedded_verse_evidence.
BOUNDARY: Atom 059 contains 'أمنّا أن تصرّع عن سماح وللآمال في يدك اصطراع' — the word اصطراع is used in a far-fetched metaphorical sense (= تنافس وتغالب). The footnote explicitly calls this usage بعيد. Tests غرابة in the semantic-ambiguity sub-type (like مسرّج).
ROLES: Roles are authoritative as encoded in `core_atoms` and `context_atoms` (validator enforces: evidence is core; no evidence in context).
PLACEMENT: taxonomy_node_id=`tatbiq_fasahat_alfard`; taxonomy_path=مقدمات > الفصاحة > فصاحة المفرد > تطبيقات فصاحة المفرد. Leaf must be true in the referenced taxonomy YAML.
CHECKLIST: Placement checklist PLACE.P1–P8 recorded in passage decisions log (one record per excerpt).
ALTS: (legacy) Alternatives not recorded; if a future reviewer disagrees, propose a taxonomy_change or boundary split and re-validate.
```

## Core atoms
- `jawahir:matn:000059`  (type=verse_evidence, role=exercise_content)
  أمنَّا أن تصرّع عن سماحٍ وللآمال في يدك اصطراع

## Context atoms
(none)
