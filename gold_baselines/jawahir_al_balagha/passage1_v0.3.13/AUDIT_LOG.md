# Passage 1 — Audit Log

This log tracks every version of this gold standard package: what changed, why, and the package fingerprint at each version. Future passages and AI agents must check this log to confirm they are working with the correct version and to understand the evolution of the data and schema.

---

## v0.2.1 — Initial Gold Standard

**Date:** 2025-02-15 (approximate)
**Schema:** gold_standard_schema_v0.2.1.json

First complete gold standard for Passage 1 (جواهر البلاغة, الفصاحة, pp. 19–25). Established the core architecture: 95 atoms, 18 excerpts, 29 exclusions, taxonomy balagha_v0_2 with 3 taxonomy changes.

Key decisions made:
- core_atoms as structured `[{atom_id, role}]` with role vocabulary (author_prose, evidence, exercise_content)
- Context = external orientation only (classification_frame, preceding_setup, etc.)
- Exercise structure: set → item → answer hierarchy with typed relations

---

## v0.3.0 — Structural Tightenings + Exercise Answers

**Date:** 2025-02-16 (approximate)
**Schema:** gold_standard_schema_v0.3.0.json

Added:
- `exercise_answer_content` core atom role for footnote answer keys
- `exercise_role=answer` for answer excerpts
- `answers_exercise_item` and `belongs_to_exercise_set` relation types
- `footnote_ref_status` (normal/orphan) with `orphan_note`
- `source_inconsistency` internal_tag type
- Validator: bidirectional taxonomy_change_triggered ↔ triggered_by_excerpt_id check

Excerpt count: 18 → 20 (2 exercise answer excerpts added: E19, E20)
Exclusion count: 29 → 26 (3 footnote atoms promoted from exclusion to answer excerpts)

---

## v0.3.1 — Comprehensive Documentation + Structural Fixes

**Date:** 2025-02-17
**Schema:** gold_standard_schema_v0.3.1.json
**Package fingerprint:** See `baseline_manifest.json` → `baseline_sha256` (the audit log is inside the package, so it cannot contain its own package hash without circularity)

### Documentation (non-breaking, additive):
- **Schema documentation:** Every field (80/80) and every definition (11/11) now has a description. Every enum value across all vocabularies is documented in-schema. Total: 26,097 characters of documentation added. Schema went from validation-only tool to self-documenting contract.
- **Project glossary:** `project_glossary.md` created — authoritative term definitions for the AI builder. Covers all 13 sections: pipeline, source material, atoms, excerpts, roles, taxonomy, relations, exercises, exclusions, gold standard process, key principles, conventions, terminology cross-reference.
- **Audit log:** This file (`AUDIT_LOG.md`) — version provenance tracking.

### Bug fixes:
- **Manifest self-reference:** Old policy text ("Only files listed...") contradicted the fact that baseline_manifest.json wasn't listed. Fixed: inventory_policy now explicitly documents the self-exclusion. fingerprint_algorithm.self_exclusion explains the circular-dependency avoidance.
- **Manifest version drift:** baseline_id and schema_version fields were stuck at v0.3.0 after schema bump. Fixed: both now read v0.3.1.
- **generate_report.py hardcoding:** 14 hardcoded `passage1_*` references and 1 `jawahir` literal removed. Script now fully driven by `--atoms`, `--excerpts`, `--metadata`, `--output` CLI args. Zero book-specific or passage-specific strings.
- **Report role alias:** Summary section printed `exercise_answer:` instead of the exact enum value `exercise_answer_content`. Fixed: role distribution now dynamically enumerates from data, printing exact schema enum values.
- **Filename version convention:** README now explains that `_v02` (record format version) and `v0.3.1` (schema version) are separate version axes.

### Scale hardening:
- **Taxonomy ID policy:** `id_policy` block added to `balagha_v0_2.yaml` with charset rules, 17 transliteration entries, 6 structure rules, and 5 worked examples. Prevents ID drift across annotators/models.

### README slimmed:
- Universal concept explanations moved to `project_glossary.md`. README now covers only passage-specific content: what text, what was discovered, how to validate, file inventory.

### Third-party review fixes (same session):
- **Taxonomy ID violations:** Two node IDs contained Arabic characters (`tawكيد_alkhabar`, `qasr_bittaقديم`), violating the id_policy. Fixed to `tawkid_alkhabar` and `qasr_bittaqdim`. All 191 node IDs now verified against charset policy.
- **Continuation metadata:** Added `continuation` block to `passage1_metadata.json` with machine-readable starting values for passage 2 (`next_matn_atom_seq: 60`, `next_fn_atom_seq: 37`, `next_excerpt_seq: 21`, `next_taxonomy_change_seq: 4`).
- **Glossary: data format section (§13):** Explains JSONL format, `record_type` discriminator, mixed-file parsing, and schema dispatch mechanism.
- **Glossary: multi-passage composition (§14):** Documents how passages relate within a book, continuation state, passage packaging, and cross-passage references.
- **Schema `$comment`:** Reformatted to properly separate v0.3.0 and v0.3.1 changes with "Changelog —" prefix.


---

## v0.3.2 — Spec Hardening + Validator Alignment (Historical Note)

**Date:** 2026-02-21
**Schema:** gold_standard_schema_v0.3.1.json (unchanged)

Changes:
- **Binding decisions evolved:** the v0.3.2 rules were rolled forward into **v0.3.3**. This baseline package ships `00_BINDING_DECISIONS_v0.3.3.md` only; older binding files are archived at repo-level.
- **Validator v0.3.3:** aligns validation with binding decisions v0.3.3:
  - controlled core-duplication exceptions (interwoven groups + shared_shahid evidence)
  - strict taxonomy leaf policy (`leaf:true` required for childless nodes)
  - relation target integrity (with `--allow-external-relations` for cross-passage targets)
  - split_discussion must mirror split_* relations
- **Split discussion authority enforced:** the two split excerpts in Passage 1 are now connected with explicit `split_continues_in` / `split_continued_from` relations to match the existing `split_discussion` mirror. (No atom/excerpt boundaries changed.)
- **Packaging/verification refresh:** `validation_report.txt`, `passage1_metadata.json` (adds `validation` block), and `baseline_manifest.json` were regenerated for consistency.

**Note:** Passage 1 still validates with `--skip-traceability` because it predates the formal decision-log traceability layer used from Passage 2 onward.

---

## v0.3.3 — Traceability Uniformity + Canonical JSONL + Derived Markdown Views

**Date:** 2026-02-21
**Schema:** gold_standard_schema_v0.3.1.json (unchanged)

Changes:
- **Gold uniformity (binding):** package now ships `00_BINDING_DECISIONS_v0.3.3.md` which locks:
  - JSONL is canonical; Markdown is derived and regeneratable.
  - active gold baselines must validate without `--skip-traceability`.
- **Traceability upgrade (Passage 1):** Passage 1 now validates in strict mode (no `--skip-traceability`).
  - `passage1_decisions.jsonl` added (one `excerpt_decision` per excerpt; PLACE.P1–P8).
  - `boundary_reasoning` converted to labeled blocks (GROUPING/BOUNDARY/ROLES/PLACEMENT/CHECKLIST/ALTS).
  - `atomization_notes` upgraded to structured sections (TYPE/BOUNDARY/CHECKLIST; bonded_cluster includes BOND).
  - `passage1_deep_qa_report.md` added as a no-regret verification summary.
- **Derived review views:** `excerpts_rendered/` added (generated deterministically from JSONL) + `tools/render_excerpts_md.py` included.
- **Packaging refresh:** `validation_report.txt`, `passage1_metadata.json` (`validation` block), and `baseline_manifest.json` regenerated to reflect the new file set.

---

## How to Read This Log

Each entry records:
- **What version** (schema + package)
- **What changed** (with categories: documentation, bug fixes, data changes, scale hardening)
- **Why** (the reasoning or finding that motivated the change)
- **Package SHA-256** when available (anchors findings to exact files)

When working with this package, always check that your `baseline_manifest.json` → `baseline_id` matches the latest entry here. If it doesn't, you may be working with stale files.

### Validator hardening (same session, third-party review round 2):
- **Layer-token map (Fix A):** Replaced 2 hardcoded if-statements (matn, footnote only) with `LAYER_TOKEN_MAP` dictionary covering all 5 source layers. Now catches mismatches for sharh, hashiya, tahqiq_3ilmi — previously these would have silently passed.
- **Taxonomy tree validation (Fix C):** Added `--taxonomy` CLI arg + `validate_taxonomy_tree()` function. Loads the YAML, verifies every excerpt's `taxonomy_node_id` exists and is a leaf node. A typo in a node ID is now caught at validation time, not downstream during synthesis.
- **Heading path glossary entry (Fix B):** Added dedicated `### Heading Path` entry in glossary defining construction rule, footnote excerpt behavior (always empty array), and cross-reference to heading dual-state principle.

---




## v0.3.12 — Machine-readable source anomaly flags (`content_anomalies`)

**Date:** 2026-02-22
**Schema:** gold_standard_schema_v0.3.3.json

Changes (data + derived views; no atom boundary changes):
- Introduced excerpt-level `content_anomalies` (schema v0.3.3) as a structured way to record source inconsistencies without “fixing” the source.
- Added a flagship example to `jawahir:exc:000021` (ملخص القول): `type=summary_mismatch`, with evidence atoms spanning the original enumeration, the detailed treatment of الكراهة في السمع, and the summary itself.
- Added a `synthesis_instruction` to prevent invalid ontology growth from summary-only mentions (ابتذال/ضعف) when not taught as full topics in this slice.

Rationale: future synthesis must not silently treat author inconsistencies as true topic structure. A machine-readable anomaly flag is safer than relying on freeform prose alone.

## v0.3.11 — Cross-science consistency (explicit صرف prerequisites)

**Date:** 2026-02-22
**Schema:** gold_standard_schema_v0.3.2.json

Changes (data + derived views; no atom boundary changes):
- Marked three excerpts as cross-science (صرف):
  - `jawahir:exc:000005` (غرابة: premise "مادة (فعل) تدل...")
  - `jawahir:exc:000008` (حاشية تعريف الفصاحة: "القواعد الصرفية" / "مادتها وصيغتها")
  - `jawahir:exc:000011` (حاشية تعليل "فعّل" ودلالة النسبة)
- For each, set: `cross_science_context=true`, `related_science=sarf`, and added `D4_cross_science` to `case_types`.
- Added a short `CROSS-SCIENCE:` note inside `boundary_reasoning` to make the threshold decision reviewable.
- Updated derived excerpt Markdown rendering to display cross-science flags and tag cross-science excerpts in `excerpts_rendered/INDEX.md`.

Rationale: cross-science handling must be learnable by example. Passage 1 now contains clear examples where البلاغة reasoning depends on technical صرف content, making the encoding unambiguous for a future AI software builder.


## v0.3.10 — Excerpt titles (source-anchored display names)

**Date:** 2026-02-22
**Schema:** gold_standard_schema_v0.3.2.json

Changes (data + derived views; no atom boundary changes):
- Added `excerpt_title` + `excerpt_title_reason` to every excerpt record in `passage1_excerpts_v02.jsonl`.
- Titles follow the binding convention: base label from taxonomy leaf title + source-anchored disambiguator (page range; source_layer; core atom span/list).
- Derived Markdown rendering now uses `excerpt_title` as the H1 heading (falls back to excerpt_id when absent).

Rationale: numeric excerpt_ids are machine-unique but not reviewer-friendly. Source-anchored titles provide unambiguous sibling distinction under the same taxonomy node for a future AI software builder.
## v0.3.9 — CP6 audit hardening + taxonomy registry identity

**Date:** 2026-02-22
**Schema:** gold_standard_schema_v0.3.1.json (unchanged)

Changes (packaging/audit; no atom/excerpt boundary changes):
- CP6 now produces `checkpoint_outputs/cp6_tool_fingerprint.json` (tool + key-file sha256 anchor).
- `validation_report.txt` is regenerated from the actual CP6 validator stdout to prevent stale reports.
- `baseline_manifest.json` is refreshed at CP6 to reflect the exact baseline file inventory.
- Validation commands now include `--taxonomy-registry` to enforce taxonomy snapshot identity against `ABD/taxonomy/taxonomy_registry.yaml`.

Rationale: remove audit drift and make the baseline package unambiguous for a future AI software builder.
