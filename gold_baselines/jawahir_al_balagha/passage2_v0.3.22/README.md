# Gold Standard Package v0.3.22 — passage2
## What This Is

This baseline is a **manually annotated, fully validated** gold-standard decomposition of a slice of:

- **Book:** جواهر البلاغة في المعاني والبيان والبديع
- **Author:** أحمد الهاشمي
- **Pages:** ص ٢٦–٣٢
- **Topic focus:** استكمال تطبيقات فصاحة المفرد + بدء فصاحة الكلام (التعريف وعيب تنافر الكلمات) + تنبيهات الحواشي

It exists as **spec-by-example** for the Arabic Book Digester (ABD) project.

## Canonical “law stack” (do not guess)
This baseline is governed by the repo-level canonical files:

- Glossary: `../../../project_glossary.md`
- Binding decisions: `../../00_BINDING_DECISIONS_v0.3.16.md`
- Checklists: `../../checklists_v0.4.md`
- Schema (this baseline validates against): `../../../schemas/gold_standard_schema_v0.3.3.json`
- Canonical schema currently in force (repo-level): `../../../schemas/gold_standard_schema_v0.3.3.json`

## Version notes (delta)
- **v0.3.21:** Documentation hardening: clarify why `passage2_clean_fn_input.txt` is empty.
  - The CP1 “clean footnote input” extractor produced no standalone footnote stream for this Shamela slice.
  - Footnote-layer atomization in this baseline is sourced instead from the **page-banded raw extraction** in `checkpoint1_fixed_report.md` (section **B**) and the companion CP1 artifacts (`checkpoint1_footnotes_pages_26_32_raw.txt`, `checkpoint1_footnotes_unitized.txt`).
  - No changes to atoms, excerpts, relations, taxonomy changes, or validation command.

- **v0.3.20:** Converted `jawahir:exc:000079` (footnote answer pack for items `jawahir:exc:000050–000052`) from generic teaching into an explicit `exercise_role=answer` excerpt under `tatbiq_fasahat_alfard` per PLACE.X3.
  - Added relations: `answers_exercise_item` → `jawahir:exc:000050`, `jawahir:exc:000051`, `jawahir:exc:000052`; and `belongs_to_exercise_set` → `jawahir:exc:000048`.
  - Retagged its core atom roles to `exercise_answer_content` and updated decision log for placement rationale.
  - No changes to text, anchors, offsets, atom boundaries, excerpt boundaries, exclusions, or taxonomy_changes.

- **v0.3.18:** remove unsupported reliance on excluded footnote apparatus in exercise `TESTS:` reasoning. Updated `boundary_reasoning` TESTS lines for `jawahir:exc:000050`, `jawahir:exc:000051`, `jawahir:exc:000052`, `jawahir:exc:000059` to justify the tested defect directly from the specimen text (no footnote IDs / “footnote flags …” claims).
  - No changes to text, anchors, offsets, atoms, boundaries, relations, exclusions, or taxonomy_changes; reasoning-only precision upgrade.

- **v0.3.17:** targeted tests_nodes precision: `jawahir:exc:000059` now encodes the specific defect leaf `3uyub_alfard_ibtidhal` (semantic misuse visible in «حلاوة الشيم» / «ظرف خلق الزمان»). Updated its parent set `jawahir:exc:000057` union tests_nodes accordingly.
  - No changes to text, anchors, offsets, atoms, boundaries, relations, exclusions, or taxonomy_changes; metadata-only precision upgrade.


- **v0.3.15:** made exercise items in the continuation of the Passage-1 `تطبيقات فصاحة المفرد` set (page 26–28 specimen quotes) encode **which defect leaf nodes they test**, via `tests_nodes` + `primary_test_node`, matching Passage 1 conventions.
  - Updated items: `jawahir:exc:000022–000030`.
  - Example: `jawahir:exc:000026` now tests `3uyub_alfard_gharaba` + `3uyub_alfard_mukhalafat_qiyas` (rare/harsh lexemes + مخالفة القياس in مصوون/بوقات).
  - **No changes** to text, anchors, offsets, atoms, boundaries, relations, or taxonomy changes; this is a metadata precision upgrade for future automation.

- **v0.3.13:** normalized the quoted two-line unit under exercise item `jawahir:exc:000043` by retagging `jawahir:matn:000099` as `verse_evidence` to match its paired line `jawahir:matn:000098` (two-line quoted verse split at line break).
  - **No changes** to `text`, `source_anchor`, offsets, exclusions, excerpt boundaries, relations, or taxonomy changes.
  - Rationale: avoid a single quoted verse unit being split across conflicting atom types; punctuation is not a reliable prose/verse discriminator in quoted verse.

- **v0.3.12:** corrected `atom_type` misclassifications where clearly **standalone verse/poetry** had been labeled `prose_sentence`.
  - Retagged 15 atoms to `verse_evidence`:
    - Matn exercise verse items: `jawahir:matn:000092–000096`, `jawahir:matn:000104–000105`, `jawahir:matn:000132–000137`.
    - Footnote poem lines: `jawahir:fn:000074`, `jawahir:fn:000080`.
  - **No changes** to `text`, `source_anchor`, offsets, exclusions, excerpt boundaries, relations, or taxonomy changes.
  - Rationale: `atom_type` must reflect **form**; standalone verse lines must be typed as `verse_evidence` to prevent future automation errors (ATOM.V1).

- **v0.3.11:** corrected `atom_type` misclassifications where clearly **non-verse prose** had been labeled `verse_evidence`.
  - Retagged 6 atoms to `prose_sentence`: `jawahir:matn:000089`, `jawahir:matn:000107`, `jawahir:fn:000069`, `jawahir:fn:000073`, `jawahir:fn:000077`, `jawahir:fn:000100`.
  - **No changes** to `text`, `source_anchor`, offsets, exclusions, excerpt boundaries, relations, or taxonomy changes.
  - Rationale: `atom_type` must reflect **form**, not function; prompts and prose lead-ins are prose (ATOM.V4).

Baseline-local duplicates of these files are intentionally **not** carried here to avoid silent divergence.

## Quick Start

```bash
# Validate everything
python ../../../tools/validate_gold.py \
  --atoms passage2_matn_atoms_v02.jsonl passage2_fn_atoms_v02.jsonl \
  --excerpts passage2_excerpts_v02.jsonl \
  --schema ../../../schemas/gold_standard_schema_v0.3.3.json \
  --canonical matn:passage2_matn_canonical.txt footnote:passage2_fn_canonical.txt \
  --taxonomy balagha_v0_3.yaml \
  --taxonomy-changes taxonomy_changes.jsonl \
  --decisions passage2_decisions.jsonl \
  --checklists ../../checklists_v0.4.md \
  --metadata passage2_metadata.json \
  --manifest baseline_manifest.json \
  --support-schemas ../../../schemas --allow-external-relations

# Generate human-readable report
python generate_report.py \
  --atoms passage2_matn_atoms_v02.jsonl passage2_fn_atoms_v02.jsonl \
  --excerpts passage2_excerpts_v02.jsonl \
  --metadata passage2_metadata.json \
  --output passage2_excerpting_report.txt

# Render derived Markdown excerpt views (non-canonical)
python ../../../tools/render_excerpts_md.py \
  --atoms passage2_matn_atoms_v02.jsonl passage2_fn_atoms_v02.jsonl \
  --excerpts passage2_excerpts_v02.jsonl \
  --outdir excerpts_rendered
```

## Checkpoint outputs (audit evidence)
`checkpoint_outputs/` contains captured stdout/stderr for CP1 and CP6, plus a deterministic index:

- `checkpoint_outputs/index.txt` (**derived-only**, deterministic; validated)
- CP1 logs: `cp1_extract_clean_input.*`
- CP6 logs: `cp6_validate.*`, `cp6_render_md.*`

Do not hand-edit `index.txt`. Regenerate via:
```bash
python ../../../tools/generate_checkpoint_index.py --baseline-dir .
```

## Authoritative validation result
All validation claims (validator version, warnings/errors, exact command) are authoritative only in:
- `passage2_metadata.json` → `validation.*`
- `checkpoint_outputs/cp6_validate.stdout.txt`

Derived docs in this folder may summarize but must not contradict those sources.

## Notes
- Canonical output is JSONL. Markdown in `excerpts_rendered/` is derived and must be regeneratable.
- `baseline_manifest.json` is the authoritative inventory + fingerprint for this baseline package.

### Footnote extraction note (important)
For this Shamela slice (ص ٢٦–٣٢), the CP1 extractor did not yield a separate “clean footnote input” stream, so:

- `passage2_clean_fn_input.txt` is intentionally empty and should not be treated as missing work.
- The **footnote-layer canonical** (`passage2_fn_canonical.txt`) and footnote atoms (`passage2_fn_atoms_v02.jsonl`) are derived from the CP1 page-banded raw extraction:
  - `checkpoint1_fixed_report.md` → section **B) FOOTNOTE extraction (raw by page)**
  - `checkpoint1_footnotes_pages_26_32_raw.txt` and `checkpoint1_footnotes_unitized.txt`

This is a deliberate documentation guard so future automation does not assume “no footnotes exist” when the clean stream is empty.
