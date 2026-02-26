<!-- GENERATED FILE — DO NOT EDIT. -->
<!-- renderer=v0.3.7 -->
<!-- inputs: bd6b805038c055e8 excerpts=passage1_excerpts_v02.jsonl:6cf61c853e48 atoms=passage1_matn_atoms_v02.jsonl:dc233edbd29f atoms=passage1_fn_atoms_v02.jsonl:30caeb9e543c -->

# عيوب المفرد: تنافر الحروف (ص ٢٠–٢١؛ matn 000016–000021)

- excerpt_id: `jawahir:exc:000004`

## Metadata
- book_id: `jawahir`
- source_layer: `matn`
- excerpt_kind: `teaching`
- taxonomy_version: `balagha_v0_2`
- taxonomy_node_id: `3uyub_alfard_tanafur`
- taxonomy_path: مقدمات > الفصاحة > فصاحة المفرد > عيوب المفرد: تنافر الحروف
- excerpt_title_reason: الاسم مأخوذ من عنوان العقدة (آخر عنصر في taxonomy_path) مع إضافة وسم وظيفي عند الحاجة (تعداد/ملخص/حاشية/تطبيق/جواب). وأُلحق به قيد مصدري ثابت لضمان تمييز الإخوة داخل العقدة الواحدة: (مدى الصفحات من page_hint عبر ذرات المقتطف؛ source_layer؛ مدى/قائمة أرقام atom_id في core_atoms).
- case_types: A1_pure_definition, A2_division_classification, C4_embedded_verse_evidence, B1_clean_boundary
- cross_science_context: `false`
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
  - context[654..766]
  - core[897..1446]

## Boundary reasoning (canonical JSONL field)
```
GROUPING: Single-topic excerpt grouped per taxonomy leaf `3uyub_alfard_tanafur`. Cases=A1_pure_definition, A2_division_classification, C4_embedded_verse_evidence, B1_clean_boundary.
BOUNDARY: Atom 016 opens with 'أما تنافر الحروف' — clear topic marker. Atoms 017-020 present two degrees (شديد/خفيف) with verse evidence. Atom 021 states the epistemological principle (الذوق السليم). Ends before atom 022 'واما غرابة الاستعمال' which transitions to the next عيب. Context: atom 012 provides the classification frame (condition 1 from the overview list).
ROLES: Roles are authoritative as encoded in `core_atoms` and `context_atoms` (validator enforces: evidence is core; no evidence in context).
PLACEMENT: taxonomy_node_id=`3uyub_alfard_tanafur`; taxonomy_path=مقدمات > الفصاحة > فصاحة المفرد > عيوب المفرد: تنافر الحروف. Leaf must be true in the referenced taxonomy YAML.
CHECKLIST: Placement checklist PLACE.P1–P8 recorded in passage decisions log (one record per excerpt).
ALTS: (legacy) Alternatives not recorded; if a future reviewer disagrees, propose a taxonomy_change or boundary split and re-validate.
```

## Core atoms
- `jawahir:matn:000016`  (type=bonded_cluster, role=author_prose)
  أما «تنافر الحروف» ؛ فهو وصف في الكلمة يوجب ثقلها على السمع. وصعوبة أدائها باللسان: بسبب كون حروف الكلمة متقاربة المخارج ـ وهو نوعان:
- `jawahir:matn:000017`  (type=bonded_cluster, role=author_prose)
  1. شديد في الثقل ـ كالظش (للموضع الخشن) ونحو: همخع «لنبت ترعاه الإبل» من قول أعرابي:
- `jawahir:matn:000018`  (type=verse_evidence, role=evidence)
  تركت ناقتي ترعى الهمخع
- `jawahir:matn:000019`  (type=bonded_cluster, role=author_prose)
  2. وخفيف في الثقل ـ كالنقنقة «لصوت الضفادع» والنقاخ «للماء العذب الصافي» ونحو: مستشزرات «بمعنى مرتفعات» من قول امرئ القيس يصف شعر ابنة عمه:
- `jawahir:matn:000020`  (type=verse_evidence, role=evidence)
  غدائره مستشزراتٌ إلى العلا تضل العقاص في مُثنَّى ومرسل
- `jawahir:matn:000021`  (type=bonded_cluster, role=author_prose)
  ولا ضابط لمعرفة الثقل والصعوبة سوى الذوق السليم، والحس الصادق الناجمين عن النظر في كلام البلغاء وممارسة أساليبهم

## Context atoms
- `jawahir:matn:000012`  (type=list_item, role=classification_frame)
  1. خلوصها من تنافر الحروف: لتكون رقيقة عذبة. تخف على اللسان، ولا تثقل على السمع، فلفظ «أسد» أخف من لفظ «فدوكس» .
