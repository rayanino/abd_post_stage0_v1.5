<!-- GENERATED FILE — DO NOT EDIT. -->
<!-- renderer=v0.3.7 -->
<!-- inputs: bd6b805038c055e8 excerpts=passage1_excerpts_v02.jsonl:6cf61c853e48 atoms=passage1_matn_atoms_v02.jsonl:dc233edbd29f atoms=passage1_fn_atoms_v02.jsonl:30caeb9e543c -->

# تطبيق 1: غرابة ألفاظ «شكر/ثبر/تطلها/تصهلها» (ص ٢٥؛ matn 000055)

- excerpt_id: `jawahir:exc:000014`

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
- case_types: C2_exercise_section, A4_shahid_with_commentary
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
  - core[3980..4069]

## Boundary reasoning (canonical JSONL field)
```
GROUPING: Single-topic excerpt grouped per taxonomy leaf `tatbiq_fasahat_alfard`. Cases=C2_exercise_section, A4_shahid_with_commentary.
BOUNDARY: Atom 055 quotes يحيى بن يعمر using archaic words (شكر=رضاع, ثبر=نكاح, تطلها=تبطل حقها, تصهلها=تعطيها القليل). These are وحشي words — unfamiliar to the average listener, requiring dictionary lookup. Tests the غرابة condition.
ROLES: Roles are authoritative as encoded in `core_atoms` and `context_atoms` (validator enforces: evidence is core; no evidence in context).
PLACEMENT: taxonomy_node_id=`tatbiq_fasahat_alfard`; taxonomy_path=مقدمات > الفصاحة > فصاحة المفرد > تطبيقات فصاحة المفرد. Leaf must be true in the referenced taxonomy YAML.
CHECKLIST: Placement checklist PLACE.P1–P8 recorded in passage decisions log (one record per excerpt).
ALTS: (legacy) Alternatives not recorded; if a future reviewer disagrees, propose a taxonomy_change or boundary split and re-validate.
```

## Core atoms
- `jawahir:matn:000055`  (type=bonded_cluster, role=exercise_content)
  قال يحيى بن يعمر: لرجل حاكمته امراته إليه «أئن سالتك ثمن شكرها وشبرك، اخذت تطلها وتضهلها.

## Context atoms
(none)
