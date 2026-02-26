<!-- GENERATED FILE — DO NOT EDIT. -->
<!-- renderer=v0.3.7 -->
<!-- inputs: bd6b805038c055e8 excerpts=passage1_excerpts_v02.jsonl:6cf61c853e48 atoms=passage1_matn_atoms_v02.jsonl:dc233edbd29f atoms=passage1_fn_atoms_v02.jsonl:30caeb9e543c -->

# جواب تطبيق 3: تعيين التنافر والغرابة (ص ٢٥؛ footnote 000029+000032)

- excerpt_id: `jawahir:exc:000019`

## Metadata
- book_id: `jawahir`
- source_layer: `footnote`
- excerpt_kind: `exercise`
- taxonomy_version: `balagha_v0_2`
- taxonomy_node_id: `tatbiq_fasahat_alfard`
- taxonomy_path: مقدمات > الفصاحة > فصاحة المفرد > تطبيقات فصاحة المفرد
- excerpt_title_reason: الاسم مأخوذ من عنوان العقدة (آخر عنصر في taxonomy_path) مع إضافة وسم وظيفي عند الحاجة (تعداد/ملخص/حاشية/تطبيق/جواب). وأُلحق به قيد مصدري ثابت لضمان تمييز الإخوة داخل العقدة الواحدة: (مدى الصفحات من page_hint عبر ذرات المقتطف؛ source_layer؛ مدى/قائمة أرقام atom_id في core_atoms).
- exercise_role: `answer`
- tests_nodes: 3uyub_alfard_tanafur, 3uyub_alfard_gharaba
- primary_test_node: `3uyub_alfard_tanafur`
- case_types: C2_exercise_section, C1_scholarly_footnote
- cross_science_context: `false`

## Relations
- `answers_exercise_item` → `jawahir:exc:000016`
- `belongs_to_exercise_set` → `jawahir:exc:000013`

## Source spans
- canonical: `passage1_fn_canonical.txt`
- spans:
  - core[4340..4402]
  - core[4434..4493]

## Boundary reasoning (canonical JSONL field)
```
GROUPING: Single-topic excerpt grouped per taxonomy leaf `tatbiq_fasahat_alfard`. Cases=C2_exercise_section, C1_scholarly_footnote.
BOUNDARY: Footnote atoms fn:029 and fn:032 contain explicit scholarly judgments identifying the عيوب in exercise item jawahir:exc:000016. fn:029 identifies جعجعة as تنافر الحروف; fn:032 concludes الفدوكس/الاسفنط/الخنشليل are وحشية غير مألوفة. Atoms fn:030-031 (pure glosses) excluded between them, making this non-contiguous.
ROLES: Roles are authoritative as encoded in `core_atoms` and `context_atoms` (validator enforces: evidence is core; no evidence in context).
PLACEMENT: taxonomy_node_id=`tatbiq_fasahat_alfard`; taxonomy_path=مقدمات > الفصاحة > فصاحة المفرد > تطبيقات فصاحة المفرد. Leaf must be true in the referenced taxonomy YAML.
CHECKLIST: Placement checklist PLACE.P1–P8 recorded in passage decisions log (one record per excerpt).
ALTS: (legacy) Alternatives not recorded; if a future reviewer disagrees, propose a taxonomy_change or boundary split and re-validate.
```

## Core atoms
- `jawahir:fn:000029`  (type=prose_sentence, role=exercise_answer_content)
  جعجعة غير فصيحة لتنافر حروفها، وهو مثل يضرب لمن يقول ولا يفعل.
- `jawahir:fn:000032`  (type=prose_sentence, role=exercise_answer_content)
  الفدوكس الأسد، فكل من هذه الألفاظ الثلاثة وحشية غير مألوفة.

## Context atoms
(none)
