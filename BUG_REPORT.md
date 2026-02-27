# ABD Bug Report — Codebase Audit (2026-02-27)

> **Scope**: Full-application audit across all pipeline stages, tools, schemas, gold data, and committed outputs.
> **Auditor**: Claude (Opus 4.6) — automated deep-dive
> **Status**: Initial findings. Each bug needs triage + fix before downstream stages depend on it.

---

## Severity Legend

| Tag | Meaning |
|-----|---------|
| 🔴 CRITICAL | Silently produces wrong results or skips validation entirely |
| 🟠 ERROR | Produces incorrect output that surfaces as false positives/negatives |
| 🟡 WARNING | Data loss, stale data, or schema drift that will bite later |
| 🔵 INFO | Inconsistency or cleanup needed, low immediate impact |

---

## BUG-001 🔴 Taxonomy Format Incompatibility — Validation Silently Skipped for بلاغة

**Location**: `tools/extract_passages.py:911-930` (`extract_taxonomy_leaves()`)

**Impact**: Validation Check 10 (leaf-only placement) **completely fails** for بلاغة taxonomy — returns 0 leaves, so all taxonomy-placement validation is silently skipped.

**Root cause**: Two incompatible taxonomy schemas coexist in production:

| Schema style | Example file | Format |
|---|---|---|
| Dict-nested | `taxonomy/imlaa_v0.1.yaml` | `{node_id: {_leaf: true}}` |
| List-of-nodes | `taxonomy/balagha/balagha_v0_{2,3,4}.yaml` | `{nodes: [{id: x, leaf: true}]}` |

`extract_taxonomy_leaves()` only handles the dict-nested (`_leaf`) format.

**Reproduction**:
```python
from extract_passages import extract_taxonomy_leaves
import yaml

# imlaa — works ✅
with open('taxonomy/imlaa_v0.1.yaml') as f:
    print(len(extract_taxonomy_leaves(f.read())))  # → 44

# balagha — broken ❌
with open('taxonomy/balagha/balagha_v0_4.yaml') as f:
    print(len(extract_taxonomy_leaves(f.read())))  # → 0  (expected: 143)
```

**Fix**: Either (a) unify all taxonomy files to one schema, or (b) teach `extract_taxonomy_leaves()` to detect and parse both formats.

---

## BUG-002 🟠 `prose_tail` Atom Type Not in VALID_ATOM_TYPES

**Location**: `tools/extract_passages.py:39-41`

**Impact**: Every passage containing `prose_tail` atoms triggers a **false** Check 3 warning ("invalid atom_type 'prose_tail'") and a **false** Check 7 ERROR ("Uncovered atoms").

**Details**:
- `prose_tail` is a valid atom type actively produced by the LLM (confirmed in P004, P010 outputs).
- It is missing from:
  ```python
  VALID_ATOM_TYPES = {"heading", "prose_sentence", "bonded_cluster",
                      "verse_evidence", "quran_quote_standalone", "list_item"}
  ```
- Because it's absent, Check 3 flags it as invalid, and Check 7 (which relies on `is_prose_tail`) also misfires (see BUG-003).

**Fix**: Add `"prose_tail"` to `VALID_ATOM_TYPES`.

---

## BUG-003 🟠 `is_prose_tail` Never Derived from `atom_type`

**Location**: `tools/extract_passages.py:557-667` (`post_process_extraction()`)

**Impact**: Prose-tail atoms are incorrectly required to appear in excerpts, generating false ERROR messages.

**Details**:
- Post-processing renames `type` → `atom_type` and sets `is_prose_tail: False` for **all** atoms.
- It never checks `if atom_type == "prose_tail": is_prose_tail = True`.
- Validation Check 7 uses the `is_prose_tail` boolean to decide whether an atom must be covered by an excerpt.
- Result: prose-tail atoms (which are intentionally uncovered) are flagged as errors.

**Reproduction**:
```python
result = {
    'atoms': [{'atom_id': 'x:matn:000001', 'type': 'prose_tail', 'text': '...'}],
    'excerpts': []
}
processed = post_process_extraction(result, 'book', 'science', 'tax.yaml')
assert processed['atoms'][0]['is_prose_tail'] == True   # FAILS — is False
```

**Fix**: In `post_process_extraction()`, after renaming `type` → `atom_type`, add:
```python
atom['is_prose_tail'] = (atom.get('atom_type') == 'prose_tail')
```

---

## BUG-004 🟡 Footnote Preamble Ignored in Extraction Prompt

**Location**: `tools/extract_passages.py:418-430` (`get_passage_footnotes()`)

**Impact**: Footnote content is **lost** for pages with bare-number or unnumbered footnote sections.

**Details**:
- `get_passage_footnotes()` only collects the `footnotes` list (numbered `(N)` entries).
- It ignores the `footnote_preamble` field, which contains text before the first `(N)` marker.
- For bare-number/unnumbered footnote sections, the `footnotes` list is empty but `footnote_preamble` holds actual content.
- The LLM receives `"(none)"` even when footnote content exists.

**Affected pages** (in `books/imla/stage1_output/pages.jsonl`):

| seq | page_num | preamble_chars | footnotes |
|-----|----------|----------------|-----------|
| 10 | 14 | 139 | 0 |
| 20 | 24 | 313 | 0 |
| 21 | 25 | 67 | 0 |
| 22 | 26 | has preamble | 1 |

**Fix**: Prepend `footnote_preamble` to the footnotes string when non-empty.

---

## BUG-005 🟡 book_id Inconsistency Across Stages

**Impact**: Cross-stage data correlation broken; confusing when tracing data lineage.

| Source | book_id used |
|--------|-------------|
| Registry / Intake (`intake_metadata.json`) | `imla` |
| Stage 1 `pages.jsonl` | `qawaid_imlaa` |
| Stage 2 `passages.jsonl` | `qawaid_imlaa` |
| Extraction CLI (`RUNBOOK.md`) | `qimlaa` |
| Extraction summary | `qimlaa` |
| Extraction atoms/excerpts | `None` (missing!) |

**Root cause**: Stage 1 was run with `--id qawaid_imlaa` instead of pulling `book_id` from `intake_metadata.json`.

**Fix**: Decide on one canonical `book_id` per book and enforce it from Stage 0 forward. Regenerate stage outputs for consistency.

---

## BUG-006 🟡 Committed Extraction Outputs Are Pre-Post-Processing (Stale)

**Location**: `output/imlaa_extraction/P004_extraction.json`, `output/imlaa_extraction/P010_extraction.json`

**Impact**: Committed files don't match current tool schema — misleading for anyone inspecting them.

**Symptoms**:
- Atoms have `type` instead of `atom_type`
- Atoms have `role` field (should be removed by post-processing)
- Atoms missing: `record_type`, `book_id`, `source_layer`, `is_prose_tail`, `bonded_cluster_trigger`
- Excerpts have bare-string `core_atoms` instead of objects with roles
- Excerpts missing: `record_type`, `book_id`, `taxonomy_version`, `status`, `cross_science_context`, `relations`, `case_types`, `heading_path`, `context_atoms`

**Conclusion**: Files were produced by an older tool version before `post_process_extraction()` existed. Current code does apply post-processing, but these saved outputs are stale.

**Fix**: Re-run extraction with current tool or delete stale outputs.

---

## BUG-007 🟠 Gold Baseline vs Extraction Schema Mismatch (18 Missing Fields)

**Location**: `gold_baselines/jawahir_al_balagha/passage1_v0.3.13/passage1_excerpts_v02.jsonl` vs extraction output

**Impact**: Extraction tool cannot produce schema-compliant output that matches the gold standard.

**Gold-only fields** (18 fields not produced by extraction):
- Post-process should add: `book_id`, `record_type`, `case_types`, `relations`, `status`, `taxonomy_version`
- Not handled by LLM or post-process: `source_spans`, `split_discussion`, `tests_nodes`, `primary_test_node`, `exercise_role`, `excerpt_title_reason`, `rhetorical_treatment_of_cross_science`, `content_anomalies`, `taxonomy_change_triggered`, `interwoven_group_id`, `cross_science_context`, `related_science`

**Extraction-only field**: `content_type` (not in gold)

**Shared fields**: Only 10 of 28 gold fields are present in extraction output.

**Fix**: Either update gold baselines to match current output schema, or extend `post_process_extraction()` + LLM prompt to produce all required fields. This needs a design decision.

---

## BUG-008 🟡 Stale Normalization Outputs in Wrong Directories

**Location**: `1_normalization/`

| File | Issue |
|------|-------|
| `jawahir_normalized.jsonl` | 0 bytes (dead file) |
| `jawahir_normalized_full.jsonl` | 22 pages, outdated schema (missing `schema_version`, `seq_index`, `volume`, `content_type`, `footnote_section_format`, `has_table`, `starts_with_zwnj_heading`; has debugging fields `raw_fn_html`, `raw_matn_html`) |

- Both files are in `1_normalization/` instead of `books/jawahir/stage1_output/`
- No stage outputs exist in `books/jawahir/` at all

**Fix**: Delete dead files, regenerate jawahir outputs with current tool into proper directory.

---

## BUG-009 🔵 Missing Normalization Report for imla

**Location**: `books/imla/stage1_output/` — no `normalization_report.json`

**Impact**: No validation statistics or summary data accompanies the Stage 1 output for imla.

**Details**:
- `pages.jsonl` exists but no report alongside it.
- An old jawahir report exists at `1_normalization/jawahir_normalization_report.json` but is missing many current-spec fields.

**Fix**: Generate `normalization_report.json` for imla, or note that report generation is a TODO.

---

## BUG-010 🔵 LLM Model Inconsistency Between Tools

| Tool | Default Model |
|------|---------------|
| `tools/discover_structure.py` | `claude-sonnet-4-20250514` |
| `tools/extract_passages.py` | `claude-sonnet-4-5-20250929` |

Not necessarily a bug, but worth standardizing for reproducibility and cost estimation.

---

## BUG-011 🔵 Hardcoded Cost Calculation

**Location**: `tools/extract_passages.py:1203-1204`

```python
cost = in_tok * 3 / 1_000_000 + out_tok * 15 / 1_000_000
```

- Hardcoded at Sonnet 3.5 pricing ($3/$15 per M tokens)
- Default model is now `claude-sonnet-4-5-20250929`
- If pricing differs, estimates are inaccurate

**Fix**: Use a model→pricing lookup dict or accept pricing as CLI args.

---

## Schema & Validation Gaps

### SCHEMA-001 🔵 Weak Division Schema
**Location**: `schemas/divisions_schema_v0.1.json`

Division item schema has `required: []` (empty) and `properties: {}` (empty) — provides zero validation of individual division fields.

### SCHEMA-002 🔵 Normalization JSONL `schema_version` Undocumented
**Location**: `1_normalization/NORMALIZATION_SPEC_v0.5.md`

Spec doesn't document the `schema_version` field, but code outputs `v1.1`. Should be documented.

---

## Cross-Tool Contract Issues

### CONTRACT-001 🟡 Stage 2 → Stage 3 book_id Mismatch
`discover_structure.py` outputs `book_id: qawaid_imlaa` but extraction expects consistent book_id from intake. See BUG-005.

### CONTRACT-002 🔴 Taxonomy Schema Incompatibility
Two incompatible taxonomy formats coexist. See BUG-001.

---

## Files Requiring Regeneration or Deletion

| File | Action |
|------|--------|
| `output/imlaa_extraction/P004_extraction.json` | Regenerate with current tool |
| `output/imlaa_extraction/P010_extraction.json` | Regenerate with current tool |
| `1_normalization/jawahir_normalized.jsonl` | Delete (0 bytes) |
| `1_normalization/jawahir_normalized_full.jsonl` | Delete or regenerate into `books/jawahir/stage1_output/` |
| `1_normalization/gold_samples/` | Review and update schema |
| `books/imla/stage1_output/normalization_report.json` | Generate |

---

## Recommended Fix Priority

1. 🔴 **BUG-001** — Taxonomy format parser (blocks all بلاغة validation)
2. 🟠 **BUG-002 + BUG-003** — prose_tail handling (false errors on every passage)
3. 🟠 **BUG-007** — Gold-vs-extraction schema gap (design decision needed)
4. 🟡 **BUG-004** — Footnote preamble data loss
5. 🟡 **BUG-005** — book_id standardization
6. 🟡 **BUG-006 + BUG-008** — Stale/misplaced outputs cleanup
7. 🔵 **BUG-009 thru BUG-011** — Reports, model consistency, cost calc
8. 🔵 **SCHEMA-001, SCHEMA-002** — Schema tightening
