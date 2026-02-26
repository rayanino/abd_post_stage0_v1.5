# Passage 2 — Audit Log

This log tracks versions of the Passage 2 gold standard package and explains changes that affect reproducibility or interpretation.

---

## v0.3.1 — Initial Gold Standard (Passage 2)

**Date:** 2026-02-21
**Schema:** gold_standard_schema_v0.3.1.json

First complete gold standard for Passage 2 (جواهر البلاغة, pp. 26–32). Introduced the checkpoint-based workflow (1–6) and decision-log traceability (`passage2_decisions.jsonl`). Added taxonomy version `balagha_v0_3` (TC-004..TC-007).

---

## v0.3.2 — Spec Hardening + Validator Alignment (Historical Note)

**Date:** 2026-02-21
**Schema:** gold_standard_schema_v0.3.1.json (unchanged)

Changes (package-level, non-breaking):
- **Validator v0.3.3:** aligns validation with binding decisions v0.3.3:
  - controlled core-duplication exceptions (interwoven groups + shared_shahid evidence)
  - strict taxonomy leaf policy (`leaf:true` required for childless nodes)
  - relation target integrity, with `--allow-external-relations` for cross-passage targets
  - split_discussion must mirror split_* relations
- **taxonomy_changes.jsonl made cumulative:** now contains TC-001..TC-007 (was TC-004..TC-007 only). This prevents ambiguity about whether the file is a delta or a full log.
- **Packaging parity:** added `AUDIT_LOG.md` and `generate_report.py` to match Passage 1 baseline completeness.
- **Verification refresh:** regenerated `validation_report.txt`, updated `passage2_metadata.json` → `validation` (command + warning/error counts), and recomputed `baseline_manifest.json` file hashes/fingerprint.

No changes were made to atoms, excerpts, exclusions, or decisions content.

---

## v0.3.3 — Canonical JSONL + Derived Markdown Views

**Date:** 2026-02-21
**Schema:** gold_standard_schema_v0.3.1.json (unchanged)

Changes:
- **Binding decisions v0.3.3 included:** locks canonical JSONL vs derived Markdown and gold traceability uniformity.
- **Derived review views added:** `excerpts_rendered/` generated deterministically from JSONL and `tools/render_excerpts_md.py` included for reproduction.
- **README updated:** clarifies non-canonical derived Markdown and the rendering command.

No changes were made to atoms, excerpts, exclusions, decisions, or taxonomy changes.

---

## How to Use This Log

When working with this package, check `baseline_manifest.json` → `baseline_id` and confirm it matches the latest entry here. If it does not, you may be working with stale files.

---

## v0.3.9 — CP6 audit hardening + taxonomy registry identity

**Date:** 2026-02-22
**Schema:** gold_standard_schema_v0.3.1.json (unchanged)

Changes (packaging/audit; no atom/excerpt boundary changes):
- CP6 now produces `checkpoint_outputs/cp6_tool_fingerprint.json` (tool + key-file sha256 anchor).
- `validation_report.txt` is regenerated from the actual CP6 validator stdout to prevent stale reports.
- `baseline_manifest.json` is refreshed at CP6 to reflect the exact baseline file inventory.
- Validation commands now include `--taxonomy-registry` to enforce taxonomy snapshot identity against `ABD/taxonomy/taxonomy_registry.yaml`.

Rationale: remove audit drift and make the baseline package unambiguous for a future AI software builder.

## v0.3.10 — Governance alignment + derived-doc truthfulness

**Scope:** No changes to atoms, excerpts, exclusions, taxonomy, or canonical text.

Changes:
- **Decision log governance:** updated all `excerpt_decision.checklist_version` values to `"checklists_v0.4"` to match the canonical checklist file (`2_atoms_and_excerpts/checklists_v0.4.md`) per Binding Decision #19.
- **Metadata consistency:** set `passage2_metadata.json.counts.taxonomy_changes = 7` to reflect that `taxonomy_changes.jsonl` is **cumulative** within a baseline package (Binding Decision #11 (taxonomy_changes.jsonl is cumulative)).
- **Derived-doc truthfulness:** updated baseline-local reports to treat `passage2_metadata.json.validation.*` and `checkpoint_outputs/cp6_validate.stdout.txt` as the only authoritative validation record (Binding Decision #20).
- Added `decision_log_format_v0.2.md` (current guidance) while retaining v0.1 as legacy reference.

## v0.3.11 — Atom type corrections (prose mislabeled as verse)

**Scope:** No changes to atom/excerpt boundaries, offsets, relations, exclusions, taxonomy, or canonical text.

Changes:
- Retagged clearly non-verse atoms that were incorrectly labeled `verse_evidence` as `prose_sentence` (form-correct typing per ATOM.V4):
  - Matn prompts: `jawahir:matn:000089`, `jawahir:matn:000107`
  - Footnote prose/lead-ins: `jawahir:fn:000069`, `jawahir:fn:000073`, `jawahir:fn:000077`, `jawahir:fn:000100`
- Updated `atomization_notes` for those atoms to match prose typing and record the colon/lead-in edge case.
- Updated `passage2_metadata.json.counts.*_atom_types` accordingly (matn: +2 prose/-2 verse; footnote: +4 prose/-4 verse).

Rationale: `atom_type` encodes **structural form** (prose vs standalone verse), not pedagogical function; prompts/attribution lead-ins must remain prose to prevent future automation errors.


## v0.3.12 — Atom type corrections (verse mislabeled as prose)

**Scope:** No changes to atom/excerpt boundaries, offsets, relations, exclusions, taxonomy, or canonical text.

Changes:
- Retagged clearly standalone verse/poetry lines that were incorrectly labeled `prose_sentence` as `verse_evidence` (form-correct typing per ATOM.V1):
  - Matn exercise verse items: `jawahir:matn:000092–000096`, `jawahir:matn:000104–000105`, `jawahir:matn:000132–000137`.
  - Footnote poem lines: `jawahir:fn:000074`, `jawahir:fn:000080` (part of multi-line poem sequences).
- Updated `atomization_notes` for those atoms to record the exercise-label/ellipsis edge case and multi-line poem continuity.
- Updated `passage2_metadata.json.counts.*_atom_types` accordingly (matn: -13 prose/+13 verse; footnote: -2 prose/+2 verse).

Rationale: `atom_type` encodes **structural form** (prose vs standalone verse). Verse evidence must be typed consistently to prevent downstream heuristics (poetry formatting, evidence parsing) from learning wrong patterns.

## v0.3.13 (2026-02-23)
- Slice D: Normalize atom_type for the quoted two-line unit in `jawahir:matn:000098–000099`: retag `jawahir:matn:000099` as `verse_evidence` to match its paired verse line and the line-break verse boundary rule.

## v0.3.14 (2026-02-23)
- Slice E: Added `internal_tags` (`verse_fragment_embedded`) for footnote atoms with leading embedded verse fragments: `jawahir:fn:000065` (core) and `jawahir:fn:000064` (excluded apparatus). No changes to text/anchors/boundaries.

## v0.3.15 (2026-02-23)
- Slice F: Precision upgrade for exercise items: filled `tests_nodes` and `primary_test_node` with the **actual defect leaf nodes** tested (matching Passage 1 conventions) for `jawahir:exc:000022–000030`.
  - No changes to text, anchors, offsets, atoms, boundaries, relations, exclusions, or taxonomy_changes.


## v0.3.16 (2026-02-23)
- Slice G: Targeted tests_nodes precision for high-evidence exercise items (no boundary/text/offset changes):
  - Updated `tests_nodes` + `primary_test_node` + added explicit `TESTS:` line in `boundary_reasoning` for:
    - `jawahir:exc:000042` → `3uyub_alfard_tanafur` (phonotactic heaviness in «أشكوك كوكك…»).
    - `jawahir:exc:000050–000052` → `3uyub_alfard_mukhalafat_qiyas` (explicitly flagged by footnotes: اسم التفضيل من «أسود»، قطع همزة الوصل في «إتسع»، وفك الإدغام/شذوذ «هوالك»).
  - Updated exercise set union tests_nodes (per EXC rules) for:
    - `jawahir:exc:000035` (now includes `3uyub_alfard_tanafur` alongside general practice).
    - `jawahir:exc:000048` (now includes `3uyub_alfard_mukhalafat_qiyas` alongside general practice).
- Fixed internal consistency: `passage2_metadata.json.baseline_version` now matches the folder version (`v0.3.16`).


## v0.3.17 (2026-02-23)
- Slice H: Added high-evidence tests_nodes precision for `jawahir:exc:000059` (semantic misuse flagged in footnote `jawahir:fn:000090`, ص:٣٠).
  - `jawahir:exc:000059`: tests_nodes → [`3uyub_alfard_ibtidhal`], primary_test_node → `3uyub_alfard_ibtidhal`, added explicit `TESTS:` line in boundary_reasoning.
  - `jawahir:exc:000057` (set): union tests_nodes now includes `3uyub_alfard_ibtidhal` (reflecting child item).
  - No changes to text/anchors/offsets/atoms/boundaries/relations/exclusions/taxonomy_changes.


## v0.3.18 (2026-02-23)
- Slice I: Removed unsupported reliance on excluded footnote apparatus in exercise `TESTS:` reasoning.
  - Updated `boundary_reasoning` TESTS lines for `jawahir:exc:000050`, `jawahir:exc:000051`, `jawahir:exc:000052`, `jawahir:exc:000059` so the defect justification is derived directly from the specimen text (no `footnote flags ...` phrasing; no `jawahir:fn:` ID references).
  - No changes to text/anchors/offsets/atoms/boundaries/relations/exclusions/taxonomy_changes.

## v0.3.19 (2026-02-23)
- Slice J: Exercise answer-footnote modeling + apparatus correction (no text/offset edits).
  - Converted footnote excerpts that function as **answers** for continued exercise items into explicit `exercise_role=answer` records at `tatbiq_fasahat_alfard`, with `exercise_answer_content` roles and relations:
    - `jawahir:exc:000070` → answers `jawahir:exc:000022`
    - `jawahir:exc:000071` → answers `jawahir:exc:000023`
    - `jawahir:exc:000072` → answers `jawahir:exc:000024`
    - `jawahir:exc:000073` → answers `jawahir:exc:000024` (second answer footnote)
    - `jawahir:exc:000074–000077` → answers `jawahir:exc:000026` (distributed answer footnotes)
  - Removed the mis-modeled gloss-only footnote excerpt `jawahir:exc:000078` and excluded its atom `jawahir:fn:000056` as `footnote_apparatus`.
  - Updated decision log records to match PLACE.X3 exercise placement policy.

## v0.3.20 (2026-02-24)
- Slice K: Converted `jawahir:exc:000079` from teaching-at-defect into an explicit exercise answer excerpt for the three application items `jawahir:exc:000050–000052`.
  - Updated fields: `excerpt_kind=exercise`, `exercise_role=answer`, taxonomy placement to `tatbiq_fasahat_alfard` (PLACE.X3), `tests_nodes=['3uyub_alfard_mukhalafat_qiyas']`.
  - Retagged core roles to `exercise_answer_content`.
  - Added relations: `answers_exercise_item` (to each of the three items) and `belongs_to_exercise_set` (to `jawahir:exc:000048`).
  - Updated decision record for placement governance.
  - No changes to text/anchors/offsets/atom boundaries/excerpt boundaries/exclusions/taxonomy_changes.

## v0.3.21 (2026-02-24)
- Documentation hardening: clarify why `passage2_clean_fn_input.txt` is empty.
  - CP1 did not yield a separate “clean footnote input” stream for this Shamela slice.
  - Footnote-layer work is sourced from the CP1 page-banded raw extraction in `checkpoint1_fixed_report.md` (section **B**) and the companion artifacts `checkpoint1_footnotes_pages_26_32_raw.txt` + `checkpoint1_footnotes_unitized.txt`.
  - No changes to atoms/excerpts/relations/exclusions/taxonomy_changes; validation command unchanged.
