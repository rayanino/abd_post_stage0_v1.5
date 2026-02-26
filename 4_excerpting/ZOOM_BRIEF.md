# Stage 4: Excerpting — Zoom-In Brief

## Mandate

This is the **most complex stage** in the pipeline and has the richest body of precision rules. Like Stage 3, the spec was written before the gold baselines matured and contains major schema drift. Additionally, the spec defines relation types and an excerpt schema that diverge significantly from the proven data model. The zoom-in must fix the drift, reconcile the multi-topic excerpt handling (which is the hardest problem in the pipeline), and design the LLM automation layer.

## Pre-Identified Issues — Schema Drift (Critical)

### Excerpt record drift

| Spec says | Actual schema/gold data says | Status |
|-----------|------------------------------|--------|
| `excerpt_id`: `EXC_001` | `excerpt_id`: `jawahir:exc:000001` | **Wrong format** |
| `title` | `excerpt_title` + `excerpt_title_reason` | **Wrong field name, missing companion** |
| `type` (teaching/exercise) | `excerpt_kind` (teaching/exercise/apparatus) | **Wrong field name** |
| `atoms[].role`: `core`/`context` | `core_atoms[]` and `context_atoms[]` as separate arrays | **Wrong structure** |
| `atoms[].context_justification` | Context atom has `role` field (classification_frame, preceding_setup, etc.) | **Wrong mechanism** |
| `placed_at`: `"balagha/maani/khabar/..."` | `taxonomy_node_id`: `"ta3rif_alfasaha_lugha"` + `taxonomy_path` + `taxonomy_version` | **Wrong field name and format** |
| `science_classification` (per-excerpt) | Science is determined by which taxonomy tree the excerpt is placed in, not a separate field | **Wrong model** |
| `science_classification_reasoning` | Does not exist in schema | **Nonexistent field** |
| `science_classification_confidence` | Does not exist in schema | **Nonexistent field** |
| No `boundary_reasoning` | `boundary_reasoning` (required, detailed) | **Missing** |
| No `case_types` | `case_types` (required array of case labels) | **Missing** |
| No `source_spans` | `source_spans` (required traceability) | **Missing** |
| No `heading_path` | `heading_path` (required) | **Missing** |
| No `status` | `status` (gold/gold_migrated/superseded) | **Missing** |
| No `split_discussion` | `split_discussion` object | **Missing** |
| No `exercise_role`/`primary_test_node`/`tests_nodes` | Exercise structure fields | **Missing** |

### Relation types drift

| Spec says (§4.2) | Actual glossary/gold data says |
|-------------------|-------------------------------|
| `prerequisite` | Does not exist |
| `builds_on` | Does not exist |
| `contrasts` | Does not exist |
| `exemplifies` | Does not exist |
| `cross_reference` | Does not exist |

Actual relation types: `footnote_supports`, `footnote_explains`, `footnote_citation_only`, `footnote_source`, `has_overview`, `shared_shahid`, `exercise_tests`, `belongs_to_exercise_set`, `answers_exercise_item`, `split_continues_in`, `split_continued_from`, `interwoven_sibling`, `cross_layer`.

**The spec's relation types are entirely fabricated.** The real types are defined in the glossary §7 and enforced by the schema.

### CP structure drift

The spec defines CP3 (Initial Excerpting), CP4 (Relations), CP5 (Validation), CP6 (Packaging). The extraction protocol defines: CP3 = canonical text construction (not excerpting!), CP4 = excerpting + relations + exclusions (combined), CP5 = taxonomy + validation, CP6 = packaging. These are different breakdowns.

## Pre-Identified Issues — Other

1. **§3 (Multi-Topic Excerpt Problem) is well-written but needs schema anchoring.** The category A/B/C framework and dependency test are good — they match Binding Decisions §8. But the spec uses generic language without citing the actual schema fields (`boundary_reasoning`, `case_types`, `SUPPORTIVE_DEPENDENCIES:` block, `interwoven_group_id`).

2. **§3.6 (Science classification per excerpt) is wrong.** The spec proposes a per-excerpt `science_classification` field with reasoning and confidence. This doesn't exist in the schema. In the actual data model, science is implicit from taxonomy placement — an excerpt placed in the بلاغة tree is a بلاغة excerpt. Cross-science routing is handled by placing the excerpt in the other science's tree.

3. **Exclusion records are not mentioned.** The spec focuses entirely on excerpts but doesn't discuss exclusions (atoms explicitly excluded from excerpting). Exclusions are a major part of the output — they account for headings, apparatus, devotional content, etc. The spec must address them.

4. **Exercise structure is barely mentioned.** The gold data has rich exercise structure (set/item/answer with inter-linked relations). The spec's §3 framework doesn't address how exercises are handled. The glossary §8 and Binding Decisions have the rules, but the spec should operationalize them.

5. **Content anomalies and excerpt titles are missing.** These are required fields in schema v0.3.3 with specific construction rules (Binding Decisions §4.2, §4.3). The spec doesn't mention them.

## What to Read

- `4_excerpting/EXCERPTING_SPEC.md` (primary — read very critically)
- `4_excerpting/edge_cases.md`
- `schemas/gold_standard_schema_v0.3.3.json` — search for `"excerpt"` and `"exclusion"` record types. **This is the truth.**
- `gold_baselines/jawahir_al_balagha/passage1_v0.3.14/passage1_excerpts_v02.jsonl` — read 3–5 excerpt records AND 2–3 exclusion records
- `precision/project_glossary.md` §4 (Excerpts), §7 (Relations), §8 (Exercise Structure), §9 (Exclusions)
- `precision/00_BINDING_DECISIONS_v0.3.16.md` §4 (self-containment, titles, anomalies), §7 (granularity), §8 (topic scope guard — the most complex section), §9 (split discussions), §10 (core duplication)
- `precision/checklists_v0.4.md` — EXC.*, PLACE.*, REL.* checklist items
- `precision/extraction_protocol_v2.4.md` §3–§6 (CPs 3–6)

## Expected Deliverables

- Rewritten `EXCERPTING_SPEC.md` with correct schema fields, relation types, and CP structure
- Exclusion handling section added
- Exercise structure section added
- Excerpt title and content anomaly construction rules integrated
- Science classification model corrected (implicit from taxonomy placement, not a separate field)
- LLM prompt skeleton for excerpting
- Honest assessment of automation complexity and context window requirements
