<!-- GENERATED FILE — DO NOT EDIT. -->
<!-- renderer=v0.3.7 -->
<!-- inputs: bd6b805038c055e8 excerpts=passage1_excerpts_v02.jsonl:6cf61c853e48 atoms=passage1_matn_atoms_v02.jsonl:dc233edbd29f atoms=passage1_fn_atoms_v02.jsonl:30caeb9e543c -->

# عيوب المفرد: مخالفة القياس (ص ٢٠–٢٤؛ matn 000041–000047)

- excerpt_id: `jawahir:exc:000006`

## Metadata
- book_id: `jawahir`
- source_layer: `matn`
- excerpt_kind: `teaching`
- taxonomy_version: `balagha_v0_2`
- taxonomy_node_id: `3uyub_alfard_mukhalafat_qiyas`
- taxonomy_path: مقدمات > الفصاحة > فصاحة المفرد > عيوب المفرد: مخالفة القياس
- excerpt_title_reason: الاسم مأخوذ من عنوان العقدة (آخر عنصر في taxonomy_path) مع إضافة وسم وظيفي عند الحاجة (تعداد/ملخص/حاشية/تطبيق/جواب). وأُلحق به قيد مصدري ثابت لضمان تمييز الإخوة داخل العقدة الواحدة: (مدى الصفحات من page_hint عبر ذرات المقتطف؛ source_layer؛ مدى/قائمة أرقام atom_id في core_atoms).
- case_types: A1_pure_definition, A4_shahid_with_commentary, B6_definition_with_exception, C4_embedded_verse_evidence, D4_cross_science, B1_clean_boundary
- cross_science_context: `true`
- related_science: `sarf`
- rhetorical_treatment_of_cross_science: `false`
- heading_path:
  - `jawahir:matn:000001`: مقدمة
  - `jawahir:matn:000002`: في معرفة الفصاحة والبلاغة
  - `jawahir:matn:000003`: الفصاحة
  - `jawahir:matn:000011`: فصاحة الكلمة

## Relations
- `has_overview` → `jawahir:exc:000003`

## Source spans
- canonical: `passage1_matn_canonical.txt`
- spans:
  - context[813..865]
  - core[2860..3523]

## Boundary reasoning (canonical JSONL field)
```
GROUPING: Single-topic excerpt grouped per taxonomy leaf `3uyub_alfard_mukhalafat_qiyas`. Cases=A1_pure_definition, A4_shahid_with_commentary, B6_definition_with_exception, C4_embedded_verse_evidence, D4_cross_science, B1_clean_boundary.
BOUNDARY: Atom 041 opens with 'واما مخالفة القياس' — clear topic marker. Atoms 042-045: two verse examples (الأجلل + إثنين) demonstrating morphological deviance. Atoms 046-047: exception rule (ما ثبت استعماله لدى العرب) with counter-examples (المشرق/المغرب, استحوذ/استنوق). Ends before atom 048 'واما الكراهة في السمع'. Cross-science: the examples require صرف knowledge (إدغام, قطع همزة, تصحيح الواو) but are used بلاغيا to define the عيب.
ROLES: Roles are authoritative as encoded in `core_atoms` and `context_atoms` (validator enforces: evidence is core; no evidence in context).
PLACEMENT: taxonomy_node_id=`3uyub_alfard_mukhalafat_qiyas`; taxonomy_path=مقدمات > الفصاحة > فصاحة المفرد > عيوب المفرد: مخالفة القياس. Leaf must be true in the referenced taxonomy YAML.
CHECKLIST: Placement checklist PLACE.P1–P8 recorded in passage decisions log (one record per excerpt).
ALTS: (legacy) Alternatives not recorded; if a future reviewer disagrees, propose a taxonomy_change or boundary split and re-validate.
```

## Core atoms
- `jawahir:matn:000041`  (type=prose_sentence, role=author_prose)
  واما (مخالفة القياس) فهو كون الكلمة شاذَّة غير جارية على القانون الصرفي المستنبط من كلام العرب؛ بأن تكون على خلاف ما ثبت فيها عن العرف العربي الصحيح
- `jawahir:matn:000042`  (type=prose_sentence, role=author_prose)
  مثل (الأجلل) في قول أبي النجم:
- `jawahir:matn:000043`  (type=verse_evidence, role=evidence)
  ألحمد لله العلي الأجلل الواحد الفرد القديم الأوَّل
- `jawahir:matn:000044`  (type=bonded_cluster, role=author_prose)
  فإن القياس (الأجل) بالادغام، ولا مسوّغ لفكّه وكقطع همزة وصل «اثنين» في قول جميل:
- `jawahir:matn:000045`  (type=verse_evidence, role=evidence)
  ألا لا أرى إثنين أحسن شيمةً على حدثان الدَّهر منَّى ومن جمل
- `jawahir:matn:000046`  (type=prose_sentence, role=author_prose)
  ويستثنى من ذلك ما ثبت استعماله لدى العرب مخالفاً للقياس ولكنه فصيح.
- `jawahir:matn:000047`  (type=bonded_cluster, role=author_prose)
  لهذا لم يخرج عن الفصاحة لفظتا (المشرق والمغرب) بكسر الراء، والقياس فتحها فيهما، وكذا لفظتا (المُدهُن والمنخُل) والقياس فيهما مِفْعَل بكسر الميم وفتح العين ـ وكذا نحو قولهم (عَوِر) والقياس عارَ: لتحرك الواو وانفتاح ما قبلها.

## Context atoms
- `jawahir:matn:000014`  (type=list_item, role=classification_frame)
  3. خلوصها من مخالفة القياس الصرفي، حتى لا تكون شاذة.
