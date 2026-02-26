<!-- GENERATED FILE — DO NOT EDIT. -->
<!-- renderer=v0.3.7 -->
<!-- inputs: bd6b805038c055e8 excerpts=passage1_excerpts_v02.jsonl:6cf61c853e48 atoms=passage1_matn_atoms_v02.jsonl:dc233edbd29f atoms=passage1_fn_atoms_v02.jsonl:30caeb9e543c -->

# شروط فصاحة المفرد إجمالا: ملخص القول (ص ٢٥؛ matn 000051–000052)

- excerpt_id: `jawahir:exc:000021`

## Metadata
- book_id: `jawahir`
- source_layer: `matn`
- excerpt_kind: `teaching`
- taxonomy_version: `balagha_v0_2`
- taxonomy_node_id: `shuroot_fasahat_alfard__overview`
- taxonomy_path: مقدمات > الفصاحة > فصاحة المفرد > شروط فصاحة المفرد إجمالا
- excerpt_title_reason: الاسم مأخوذ من عنوان العقدة (آخر عنصر في taxonomy_path) مع إضافة وسم وظيفي عند الحاجة (تعداد/ملخص/حاشية/تطبيق/جواب). وأُلحق به قيد مصدري ثابت لضمان تمييز الإخوة داخل العقدة الواحدة: (مدى الصفحات من page_hint عبر ذرات المقتطف؛ source_layer؛ مدى/قائمة أرقام atom_id في core_atoms).
- case_types: D5_parent_level_content, B1_clean_boundary
- cross_science_context: `false`
- content_anomalies:
  - type: `summary_mismatch`
    details: The author's summary (ملخص القول) does not align with the earlier enumeration of conditions: it adds الابتذال and الضعف, and omits الكراهة في السمع which is nevertheless treated as an independent عيب earlier in the passage. Preserve the mismatch as source sovereignty.
    synthesis_instruction: Do not infer new taxonomy leaves solely from summary-only mentions here; treat this as an author-level inconsistency and align synthesis primarily with the detailed treatments and the earlier enumeration.
    evidence_atom_ids: jawahir:matn:000012, jawahir:matn:000013, jawahir:matn:000014, jawahir:matn:000015, jawahir:matn:000048, jawahir:matn:000049, jawahir:matn:000050, jawahir:matn:000051, jawahir:matn:000052
    evidence_excerpt_ids: jawahir:exc:000003, jawahir:exc:000021
- heading_path:
  - `jawahir:matn:000001`: مقدمة
  - `jawahir:matn:000002`: في معرفة الفصاحة والبلاغة
  - `jawahir:matn:000003`: الفصاحة
  - `jawahir:matn:000011`: فصاحة الكلمة

## Relations
- `split_continued_from` → `jawahir:exc:000003`

## Source spans
- canonical: `passage1_matn_canonical.txt`
- spans:
  - core[3757..3935]

## Boundary reasoning (canonical JSONL field)
```
GROUPING: Single-topic excerpt grouped per taxonomy leaf `shuroot_fasahat_alfard__overview`. Cases=D5_parent_level_content, B1_clean_boundary.
BOUNDARY: Atoms 051-052 are the author's ملخص القول summarizing فصاحة الكلمة conditions after the detailed عيب treatments. This is a recap of the overview enumeration (exc:000003), placed at the same __overview leaf. IMPORTANT: atom 051 diverges from the enumeration in exc:000003. The ملخص lists: تنافر الحروف، الغرابة، مخالفة القياس، الابتذال، الضعف — introducing الابتذال and الضعف (absent from the enumeration) and omitting الكراهة في السمع (which IS treated as an independent عيب in atoms 048-050). This is an author inconsistency preserved per content sovereignty; do NOT auto-create taxonomy nodes from summary-only mentions. Synthesis LLM must be aware that the summary and the enumeration do not perfectly align.
ROLES: Roles are authoritative as encoded in `core_atoms` and `context_atoms` (validator enforces: evidence is core; no evidence in context).
PLACEMENT: taxonomy_node_id=`shuroot_fasahat_alfard__overview`; taxonomy_path=مقدمات > الفصاحة > فصاحة المفرد > شروط فصاحة المفرد إجمالا. Leaf must be true in the referenced taxonomy YAML.
CHECKLIST: Placement checklist PLACE.P1–P8 recorded in passage decisions log (one record per excerpt).
ALTS: (legacy) Alternatives not recorded; if a future reviewer disagrees, propose a taxonomy_change or boundary split and re-validate.
```

## Core atoms
- `jawahir:matn:000051`  (type=bonded_cluster, role=author_prose)
  وملخَّص القول ـ أن فصاحة الكلمة تكون بسلامتها من تنافر الحروف ومن الغرابة. ومن مخالفة القياس. ومن الابتذال. والضعف.
- `jawahir:matn:000052`  (type=prose_sentence, role=author_prose)
  فاذا لصق بالكلمة عيب من هذه العيوب السابقة وجب نبذها واطراحها.

## Context atoms
(none)
