<!-- GENERATED FILE — DO NOT EDIT. -->
<!-- renderer=v0.3.7 -->
<!-- inputs: bd6b805038c055e8 excerpts=passage1_excerpts_v02.jsonl:6cf61c853e48 atoms=passage1_matn_atoms_v02.jsonl:dc233edbd29f atoms=passage1_fn_atoms_v02.jsonl:30caeb9e543c -->

# عيوب المفرد: الكراهة في السمع (ص ٢٠–٢٤؛ matn 000048–000050)

- excerpt_id: `jawahir:exc:000007`

## Metadata
- book_id: `jawahir`
- source_layer: `matn`
- excerpt_kind: `teaching`
- taxonomy_version: `balagha_v0_2`
- taxonomy_node_id: `3uyub_alfard_karahat_sam3`
- taxonomy_path: مقدمات > الفصاحة > فصاحة المفرد > عيوب المفرد: الكراهة في السمع
- excerpt_title_reason: الاسم مأخوذ من عنوان العقدة (آخر عنصر في taxonomy_path) مع إضافة وسم وظيفي عند الحاجة (تعداد/ملخص/حاشية/تطبيق/جواب). وأُلحق به قيد مصدري ثابت لضمان تمييز الإخوة داخل العقدة الواحدة: (مدى الصفحات من page_hint عبر ذرات المقتطف؛ source_layer؛ مدى/قائمة أرقام atom_id في core_atoms).
- case_types: A1_pure_definition, C4_embedded_verse_evidence, D2_new_node_discovery, B1_clean_boundary
- cross_science_context: `false`
- heading_path:
  - `jawahir:matn:000001`: مقدمة
  - `jawahir:matn:000002`: في معرفة الفصاحة والبلاغة
  - `jawahir:matn:000003`: الفصاحة
  - `jawahir:matn:000011`: فصاحة الكلمة
- taxonomy_change_triggered: `TC-001`

## Relations
- `has_overview` → `jawahir:exc:000003`

## Source spans
- canonical: `passage1_matn_canonical.txt`
- spans:
  - context[866..896]
  - core[3524..3756]

## Boundary reasoning (canonical JSONL field)
```
GROUPING: Single-topic excerpt grouped per taxonomy leaf `3uyub_alfard_karahat_sam3`. Cases=A1_pure_definition, C4_embedded_verse_evidence, D2_new_node_discovery, B1_clean_boundary.
BOUNDARY: Atom 048 opens with 'واما الكراهة في السمع' — clear topic marker. Atoms 049-050: verse example (المتنبي, الجرشى). Ends before atom 051 which is a ملخص of ALL four conditions (assigned to the overview excerpt jawahir:exc:000003). New taxonomy node 3uyub_alfard_karahat_sam3 created because الهاشمي treats كراهة السمع as independent from تنافر: تنافر is about pronunciation difficulty, كراهة is about aesthetic repugnance even for phonetically easy words.
ROLES: Roles are authoritative as encoded in `core_atoms` and `context_atoms` (validator enforces: evidence is core; no evidence in context).
PLACEMENT: taxonomy_node_id=`3uyub_alfard_karahat_sam3`; taxonomy_path=مقدمات > الفصاحة > فصاحة المفرد > عيوب المفرد: الكراهة في السمع. Leaf must be true in the referenced taxonomy YAML.
CHECKLIST: Placement checklist PLACE.P1–P8 recorded in passage decisions log (one record per excerpt).
ALTS: (legacy) Alternatives not recorded; if a future reviewer disagrees, propose a taxonomy_change or boundary split and re-validate.
```

## Core atoms
- `jawahir:matn:000048`  (type=prose_sentence, role=author_prose)
  واما (الكراهة في السمع) فهو كون الكلمة وحشية، تأنفها الطباع وتمجها الاسماع، وتنبو عنه، كما ينبو عن سماع الأصوات المنكرة.
- `jawahir:matn:000049`  (type=prose_sentence, role=author_prose)
  (كالجرشى ـ للنفس) في قول أبي الطيب المتنبي يمدح سيف الدولة
- `jawahir:matn:000050`  (type=verse_evidence, role=evidence)
  مبارك الإسم أغرُّ اللقب … كريم الجرشَّى شريف النَّسب

## Context atoms
- `jawahir:matn:000015`  (type=list_item, role=classification_frame)
  4. خلوصها من الكراهة في السمع.
