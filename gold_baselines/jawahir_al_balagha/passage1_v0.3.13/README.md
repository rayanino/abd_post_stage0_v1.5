# Gold Standard Package v0.3.13 — passage1

## What This Is

This baseline is a **manually annotated, fully validated** gold-standard decomposition of a slice of:

- **Book:** جواهر البلاغة في المعاني والبيان والبديع
- **Author:** أحمد الهاشمي
- **Pages:** ص ١٩–٢٥
- **Topic focus:** الفصاحة وشروط فصاحة الكلمة المفردة

It exists as **spec-by-example** for the Arabic Book Digester (ABD) project.

## Canonical “law stack” (do not guess)
This baseline is governed by the repo-level canonical files:

- Glossary: `../../../project_glossary.md`
- Binding decisions: `../../00_BINDING_DECISIONS_v0.3.16.md`
- Checklists: `../../checklists_v0.4.md`
- Schema: `../../../schemas/gold_standard_schema_v0.3.3.json`

Baseline-local duplicates of these files are intentionally **not** carried here to avoid silent divergence.

## Quick Start

```bash
# Validate everything
python ../../../tools/validate_gold.py \
  --atoms passage1_matn_atoms_v02.jsonl passage1_fn_atoms_v02.jsonl \
  --excerpts passage1_excerpts_v02.jsonl \
  --schema ../../../schemas/gold_standard_schema_v0.3.3.json \
  --canonical matn:passage1_matn_canonical.txt footnote:passage1_fn_canonical.txt \
  --taxonomy balagha_v0_2.yaml \
  --taxonomy-changes taxonomy_changes.jsonl \
  --decisions passage1_decisions.jsonl \
  --checklists ../../checklists_v0.4.md \
  --metadata passage1_metadata.json \
  --manifest baseline_manifest.json \
  --support-schemas ../../../schemas 

# Generate human-readable report
python generate_report.py \
  --atoms passage1_matn_atoms_v02.jsonl passage1_fn_atoms_v02.jsonl \
  --excerpts passage1_excerpts_v02.jsonl \
  --metadata passage1_metadata.json \
  --output passage1_excerpting_report.txt

# Render derived Markdown excerpt views (non-canonical)
python ../../../tools/render_excerpts_md.py \
  --atoms passage1_matn_atoms_v02.jsonl passage1_fn_atoms_v02.jsonl \
  --excerpts passage1_excerpts_v02.jsonl \
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

## Notes
- Canonical output is JSONL. Markdown in `excerpts_rendered/` is derived and must be regeneratable.
- `baseline_manifest.json` is the authoritative inventory + fingerprint for this baseline package.

