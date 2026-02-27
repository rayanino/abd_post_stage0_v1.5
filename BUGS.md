# ABD Bug Tracker

> Generated: 2025-02-27  
> Method: Adversarial code audit across all tools, specs, schemas, data files, and tests.  
> Scope: Every `.py` tool, every committed output file, every schema, every gold baseline, and cross-file consistency.

---

## Severity Definitions

| Severity | Meaning |
|----------|---------|
| 🔴 CRITICAL | Blocks correct operation of a pipeline stage or produces silently wrong output |
| 🟡 MODERATE | Produces degraded output, confusing errors, or inconsistent data — but doesn't block |
| 🟢 LOW | Cosmetic, documentation, or future-proofing issue |

---

## BUG-001 🔴 Taxonomy Format Divergence Breaks Leaf Extraction for بلاغة

**Location:** `tools/extract_passages.py` → `extract_taxonomy_leaves()` (line ~911)  
**Also affects:** SYSTEM_PROMPT template (line ~316: "Use ONLY leaf nodes (`_leaf: true`)")

**Problem:**  
The `extract_taxonomy_leaves()` function searches for `_leaf: true` (underscore prefix) via line-by-line text scanning. The إملاء taxonomy (`taxonomy/imlaa_v0.1.yaml`) uses `_leaf: true` and a nested-dict structure — this works. But the بلاغة taxonomy (`taxonomy/balagha/balagha_v0_4.yaml`) uses `leaf: true` (no underscore) and a completely different list-of-nodes structure with explicit `id` fields. Result:

- `extract_taxonomy_leaves()` returns **0 leaves** for بلاغة (should return 143).
- Every excerpt placement triggers a "non-leaf" validation warning.
- The retry loop fires on every passage and can never succeed.
- The SYSTEM_PROMPT tells the LLM to look for `_leaf: true`, further confusing it.

**Reproduction:**
```python
from tools.extract_passages import extract_taxonomy_leaves
with open('taxonomy/balagha/balagha_v0_4.yaml') as f:
    text = f.read()
print(len(extract_taxonomy_leaves(text)))  # → 0 (expected: 143)
```

**Impact:** Extraction pipeline is **completely broken** for any science that uses the list-based taxonomy format. Currently only إملاء works.

**Fix:** `extract_taxonomy_leaves()` must handle both formats — either by proper YAML parsing (not line scanning) or by supporting both `_leaf: true` and `leaf: true` markers in both dict-based and list-based structures.

---

## BUG-002 🔴 `prose_tail` Atom Type Creates Contradictory State and False Errors

**Location:** `tools/extract_passages.py` → `post_process_extraction()` (line ~571) + `validate_extraction()` (line ~667)

**Problem:**  
The SYSTEM_PROMPT instructs the LLM: *"type it according to its actual form (`prose_sentence` or `bonded_cluster`) but add `is_prose_tail: true`"*. However, in practice the LLM sometimes returns `"type": "prose_tail"` as the atom type (evidenced in committed `output/imlaa_extraction/P004_extraction.json`).

When this happens, the post-processing chain produces contradictory state:
1. `post_process_extraction()` renames `type` → `atom_type`, yielding `atom_type: "prose_tail"`
2. It sets `is_prose_tail: False` via `setdefault` (because the LLM didn't include the field)
3. `validate_extraction()` Check 3 flags `prose_tail` as an invalid `atom_type` → WARNING
4. Check 7 (Coverage) sees `is_prose_tail=False`, so the atom is NOT excluded from coverage
5. The atom isn't in any excerpt's `core_atoms` either (correctly)
6. Coverage check fires → ERROR: "Uncovered atoms"

The retry loop then sends both the WARNING and ERROR back to the LLM, which gets confused because it's being told its output format is wrong AND its coverage is wrong, when really the tool should have corrected the atom type.

**Reproduction:**
```python
from tools.extract_passages import post_process_extraction, validate_extraction
result = {
    'atoms': [
        {'atom_id': 'x:matn:000001', 'type': 'prose_tail', 'text': 'test'},
        {'atom_id': 'x:matn:000002', 'type': 'prose_sentence', 'text': 'content'},
    ],
    'excerpts': [{'excerpt_id': 'x:exc:000001', 'core_atoms': [{'atom_id': 'x:matn:000002', 'role': 'author_prose'}],
                  'taxonomy_node_id': 'leaf', 'boundary_reasoning': 'x', 'source_layer': 'matn',
                  'excerpt_title': 'x', 'case_types': ['A1_pure_definition']}],
    'footnote_excerpts': [],
}
p = post_process_extraction(result, 'x', 'imlaa')
# p['atoms'][0] has atom_type='prose_tail' AND is_prose_tail=False
v = validate_extraction(p, 'P', {'leaf'})
# v['errors'] = ['Uncovered atoms...'], v['warnings'] = ['invalid atom_type prose_tail']
```

**Impact:** Every passage with prose_tail content triggers unnecessary retries (wasting ~$0.03–0.10 per passage) and potentially degrades LLM output quality on retry.

**Fix:** `post_process_extraction()` should detect `atom_type == "prose_tail"` and (a) set `is_prose_tail = True`, (b) change `atom_type` to `"prose_sentence"`. Alternatively, add `"prose_tail"` to `VALID_ATOM_TYPES` and treat it as an excluded type in validation.

---

## BUG-003 🔴 Committed Extraction Output Is Stale / Pre-Dates Post-Processing

**Location:** `output/imlaa_extraction/P004_extraction.json`, `P010_extraction.json`

**Problem:**  
The committed extraction output files were generated before the current `post_process_extraction()` code existed. They have:

| Field | Expected (current code) | Actual (committed file) |
|-------|------------------------|------------------------|
| `atom_type` | present | MISSING (has `type` instead) |
| `record_type` | `"atom"` | MISSING |
| `book_id` | `"qimlaa"` | MISSING |
| `source_layer` | `"matn"` | MISSING |
| `is_prose_tail` | `true`/`false` | MISSING |
| `bonded_cluster_trigger` | `null`/object | MISSING |
| `exclusions` (top-level) | array | MISSING |
| `notes` (top-level) | string | MISSING |

Also, `extraction_summary.json` has `book_id: "qimlaa"` which doesn't match the registry book_id `"imla"`.

**Impact:** Anyone using committed output as reference data gets a wrong picture of the tool's current output format. The gold calibration file (`3_extraction/gold/P004_gold_excerpt.json`) also uses a third, different field set — creating three competing "truth" sources.

**Fix:** Re-run extraction for P004 and P010 with current code and recommit. Alternatively, add a clear warning that committed output is from an older tool version.

---

## BUG-004 🔴 `book_id` Inconsistency Across Pipeline Stages

**Location:** Cross-cutting: registry, intake, Stage 1, Stage 2, extraction

**Problem:**  
The same book is identified differently at each stage:

| Source | `book_id` |
|--------|-----------|
| `books/books_registry.yaml` | `imla` |
| `books/imla/intake_metadata.json` | `imla` |
| `books/imla/stage1_output/pages.jsonl` | `qawaid_imlaa` |
| `books/imla/stage2_output/passages.jsonl` | `qawaid_imlaa` |
| `books/imla/stage2_output/divisions.json` | `qawaid_imlaa` |
| `output/imlaa_extraction/P004_extraction.json` atoms | (none — field missing) |
| `output/imlaa_extraction/extraction_summary.json` | `qimlaa` |
| Atom ID prefix in extraction output | `qimlaa:matn:...` |

The `imla` vs `qawaid_imlaa` vs `qimlaa` discrepancy means no downstream tool can reliably join data across stages using `book_id`. The Stage 1/2 tools were apparently run with `--id qawaid_imlaa` while the extraction was run with `--book-id qimlaa`.

**Impact:** Any pipeline that chains stages (e.g., "find all excerpts for book X") will silently miss data due to ID mismatch.

**Fix:** Enforce a single canonical book_id from Stage 0 intake metadata and propagate it automatically to all downstream stages. The `--book-id` CLI args should default to reading from intake_metadata.json rather than requiring manual entry.

---

## BUG-005 🟡 Footnote Preamble Silently Dropped in Extraction

**Location:** `tools/extract_passages.py` → `get_passage_footnotes()` (line ~418)

**Problem:**  
The `get_passage_footnotes()` function collects only the structured `footnotes` array (numbered entries). It completely ignores the `footnote_preamble` field, which contains text that appeared before the first numbered footnote marker.

In the إملاء book, 4 pages have preamble content (up to 313 chars), and across the full corpus, the Stage 1 analysis found preamble content on thousands of pages. For pages with `footnote_section_format: "bare_number"` or `"unnumbered"`, the ENTIRE footnote section is captured as preamble (since no `(N)` markers were found), meaning all footnote content on those pages is silently dropped.

**Reproduction:**
```python
import json
with open('books/imla/stage1_output/pages.jsonl') as f:
    pages = [json.loads(l) for l in f if l.strip()]
# Page at seq_index=20 has 313 chars of preamble
p = [p for p in pages if p['seq_index'] == 20][0]
print(p['footnote_preamble'][:100])  # Content exists
print(len(p['footnotes']))           # 2 numbered footnotes
# But get_passage_footnotes() only returns the 2 numbered ones
```

**Impact:** Scholarly footnote content is lost before the LLM ever sees it. For `bare_number` and `unnumbered` formats (24,775+ pages across corpus), ALL footnote text is invisible to extraction.

**Fix:** `get_passage_footnotes()` should prepend `footnote_preamble` to the assembled footnote text when it exists, clearly marked (e.g., `[preamble] ...text...`).

---

## BUG-006 🟡 `starts_with_zwnj_heading` Loaded But Never Used in Structure Discovery

**Location:** `tools/discover_structure.py` (lines 101, 681)

**Problem:**  
The `starts_with_zwnj_heading` field is loaded from `pages.jsonl` into the `PageRecord` dataclass but is never referenced by any of the three discovery passes (Pass 1 HTML, Pass 2 Keyword, Pass 3 LLM). The ZWNJ marker (`\u200c\u200c` at the start of matn text) indicates section headings in many Shamela exports. The corpus analysis documents note this marker appears on 15,000+ pages across the corpus.

**Impact:** A reliable heading signal is captured at Stage 1 but wasted at Stage 2. Books that rely primarily on ZWNJ headings (rather than `<span class="title">` tags) will have degraded structure discovery.

**Fix:** Add a ZWNJ-based heading detection step to Pass 1 or Pass 2. When `starts_with_zwnj_heading` is true, extract the first line (or text up to the first period/paragraph break) as a heading candidate with `confidence: "high"`.

---

## BUG-007 🟡 Three Competing Schema Definitions for Atoms/Excerpts

**Location:** Cross-cutting schema drift

**Problem:**  
There are three mutually incompatible "truth" sources for what an atom/excerpt record looks like:

| Field | Gold Schema v0.3.3 | Extraction Tool Output | Extraction Gold Calibration |
|-------|-------------------|----------------------|---------------------------|
| `source_anchor` | REQUIRED (`char_offset_start/end`) | Not produced | Not present |
| `page_hint` | Present | Not produced | Not present |
| `canonical_text_sha256` | Present | Not produced | Not present |
| `footnote_refs` | Present | Not produced | Not present |
| `internal_tags` | Present | Not produced | Not present |
| `book_id` on atoms | REQUIRED | Set by post-process | Present |
| `source_spans` on excerpts | Present in gold | Not produced | Not present |
| `tests_nodes` on excerpts | Present in gold | Not produced | Not present |
| `split_discussion` on excerpts | Present in gold | Not produced | Not present |
| `excerpt_title_reason` | In gold baselines | In prompt but not validated | Present in calibration |

The authoritative gold schema (`schemas/gold_standard_schema_v0.3.3.json`) requires fields like `source_anchor` that no tool produces. The gold baselines have fields like `source_spans` and `tests_nodes` that the extraction tool doesn't generate. The extraction tool's gold calibration file (`3_extraction/gold/P004_gold_excerpt.json`) uses yet another subset.

**Impact:** No single validation can confirm output correctness. Schema validation against `gold_standard_schema_v0.3.3.json` would reject ALL extraction output. Gold baselines can't serve as calibration targets because their field sets don't match what the tool produces.

**Fix:** Decide which schema is authoritative and align the others. Either (a) update the extraction tool to produce all required gold schema fields (including `source_anchor`, which requires character-offset tracking), or (b) create a separate `extraction_schema_v1.0.json` that reflects what the tool actually produces and plan a migration path to the full gold schema.

---

## BUG-008 🟡 Page Filtering Creates Non-Contiguous `seq_index` in Output

**Location:** `tools/normalize_shamela.py` → `normalize_multivolume()` (line ~759), `normalize_book_by_id()` (line ~900), `_run_single_html_mode()` (line ~1047)

**Problem:**  
When `--page-start` or `--page-end` is used, pages are filtered AFTER `seq_index` has been assigned. This means the output JSONL has gaps in `seq_index` (e.g., 0, 5, 6, 7, ... if pages 1-4 were filtered out). Downstream tools (Structure Discovery, extraction) use `range(start_seq_index, end_seq_index + 1)` to iterate pages, which would attempt to look up non-existent seq indices.

Additionally, the normalization report reflects ALL pages (pre-filter), not just the filtered subset, making the report inconsistent with the actual output.

**Impact:** Using `--page-start`/`--page-end` produces output that downstream tools can't correctly consume. Currently mitigated by the fact that nobody uses these flags in production (only full-book runs have been done).

**Fix:** Either (a) reassign `seq_index` after filtering to maintain continuity, or (b) document that filtering is for debugging only and not for pipeline consumption, or (c) filter before seq_index assignment.

---

## BUG-009 🟡 `discover_structure.py` LLM Default Model Is Outdated

**Location:** `tools/discover_structure.py` (line ~52)

**Problem:**  
```python
LLM_DEFAULT_MODEL = "claude-sonnet-4-20250514"  # discover_structure.py
```
vs.
```python
default="claude-sonnet-4-5-20250929"             # extract_passages.py
```

Stage 2 (Structure Discovery) defaults to an older model while Stage 3+4 (Extraction) defaults to a newer one. The Stage 2 constant appears twice in the file (suggesting a copy-paste or merge artifact).

**Impact:** Stage 2 LLM calls use an older model with potentially lower quality, and the duplication could cause confusion when updating.

**Fix:** Update to a consistent model across all tools. Remove the duplicate constant.

---

## BUG-010 🟡 Hardcoded Cost Calculation Assumes Sonnet Pricing

**Location:** `tools/extract_passages.py` (line ~1204)

**Problem:**  
```python
cost = in_tok * 3 / 1_000_000 + out_tok * 15 / 1_000_000
```

This is hardcoded for Claude Sonnet pricing ($3/$15 per MTok). If the user passes `--model` with a different model (e.g., Opus at $15/$75, or Haiku at $0.25/$1.25), the cost tracking is silently wrong.

**Impact:** Misleading cost reports when using non-Sonnet models. Low severity since the default is Sonnet and cost is informational only.

**Fix:** Add a model→pricing lookup table, or at minimum note the assumption in the output.

---

## BUG-011 🟡 Empty and Duplicate Files Committed to Repository

**Location:** Multiple

**Problem:**  
Several files are empty, duplicated, or misplaced:

1. `1_normalization/jawahir_normalized.jsonl` — **0 bytes** (empty file committed to git)
2. `1_normalization/jawahir_normalized_full.jsonl` — 22 pages, has data  
   `1_normalization/gold_samples/jawahir_normalized_full.jsonl` — duplicate copy (148KB)  
   `1_normalization/gold_samples/jawahir_normalized.jsonl` — DIFFERENT content (1MB, includes raw HTML)
3. The `jawahir_normalized_full.jsonl` in `1_normalization/` is missing modern fields (`schema_version`, `footnote_section_format`, `seq_index`, `content_type`, `starts_with_zwnj_heading`) — it was generated by an older version of the normalizer.

**Impact:** Confusion about which file is authoritative. Old normalized output missing critical fields.

**Fix:** Delete the 0-byte file. Decide which jawahir normalization is canonical and remove duplicates. Regenerate with current normalizer if jawahir gold samples need to be maintained.

---

## BUG-012 🟡 `requirements.txt` Missing Runtime Dependencies

**Location:** `requirements.txt`

**Problem:**  
The file lists only `PyYAML>=6.0` but the tools also require:
- `httpx` — used by `extract_passages.py` for Claude API calls
- `anthropic` — used by `discover_structure.py` and `enrich.py` for Claude API calls

`CLAUDE.md` correctly documents `pip install PyYAML httpx` but omits `anthropic`. The actual dependency situation:

| Tool | HTTP library | Package needed |
|------|-------------|----------------|
| `extract_passages.py` | `httpx` (raw HTTP) | `httpx` |
| `discover_structure.py` | `anthropic` SDK | `anthropic` |
| `enrich.py` | `anthropic` SDK | `anthropic` |

**Impact:** `pip install -r requirements.txt` doesn't install all needed packages. LLM-dependent stages fail at runtime with import errors.

**Fix:** Add `httpx>=0.24` and `anthropic>=0.18` to `requirements.txt`.

---

## BUG-013 🟡 Normalization Default Output Path Doesn't Match Actual Repository Layout

**Location:** `tools/normalize_shamela.py` → `_run_book_id_mode()` (line ~993)

**Problem:**  
```python
out_jsonl = args.out_jsonl or os.path.join(books_dir, book_id, "pages.jsonl")
```

The default output is `books/{book_id}/pages.jsonl`, but the actual committed output is at `books/imla/stage1_output/pages.jsonl`. There's no `stage1_output/` subdirectory in the default path. This means running the tool with default settings would write to a different location than where Stage 2 expects to find the file.

**Impact:** Re-running normalization with defaults creates the file in the wrong place. Stage 2 would need to be told the correct path explicitly.

**Fix:** Either change the default to `books/{book_id}/stage1_output/pages.jsonl` or document the expected layout.

---

## BUG-014 🟡 Gold Schema `divisions_schema_v0.1.json` Has Empty Division Item Definition

**Location:** `schemas/divisions_schema_v0.1.json`

**Problem:**  
The divisions schema defines required top-level fields but the division item schema has:
```json
"items": {
  "required": [],
  "properties": {}
}
```

This means ANY object passes validation as a valid division item — the schema provides zero field-level validation for the most important part of its data.

**Impact:** Schema validation against `divisions_schema_v0.1.json` is essentially no-op for division records. Invalid divisions would pass silently.

**Fix:** Populate the division item schema with the actual fields and constraints (matching the 23 fields present in committed `divisions.json` data).

---

## BUG-015 🟢 Cost Comment in Extraction Uses Sonnet, Model Default Targets Sonnet 4.5

**Location:** `tools/extract_passages.py` (line ~1203)

**Problem:**  
```python
# Cost estimate (Claude Sonnet pricing)
cost = in_tok * 3 / 1_000_000 + out_tok * 15 / 1_000_000
```

The comment says "Sonnet" but the default model is `claude-sonnet-4-5-20250929` (Sonnet 4.5). The pricing happens to be the same, but the comment is misleading and will break if pricing changes.

**Fix:** Update comment to reference the specific model and pricing source.

---

## BUG-016 🟢 `jawahir_normalization_report.json` Has Fewer Fields Than Current Report Schema

**Location:** `1_normalization/jawahir_normalization_report.json`

**Problem:**  
This report was generated by an older normalizer version and is missing fields that the current `NormalizationReport` dataclass includes:
- `pages_with_fn_preamble`
- `pages_with_bare_number_fns`
- `pages_with_unnumbered_fns`
- `total_matn_chars` / `total_footnote_chars` / `total_preamble_chars`
- `pages_with_tables`
- `pages_image_only`
- `pages_with_zwnj_heading`
- `pages_with_duplicate_numbers`

**Impact:** Stale report provides incomplete picture of jawahir book characteristics.

**Fix:** Regenerate when jawahir is next processed.

---

## BUG-017 🟢 `LLM_DEFAULT_MODEL` Defined Twice in `discover_structure.py`

**Location:** `tools/discover_structure.py`

**Problem:**  
The constant `LLM_DEFAULT_MODEL = "claude-sonnet-4-20250514"` appears twice in the file (grep confirms two identical definitions). Same for `LLM_MAX_RETRIES = 3`.

**Impact:** No functional impact (same value), but suggests a merge or copy-paste error that could cause silent bugs if one is updated and the other isn't.

**Fix:** Remove the duplicate definitions.

---

## BUG-018 🟢 `discover_structure.py` Uses `anthropic` SDK While `extract_passages.py` Uses Raw `httpx`

**Location:** `tools/discover_structure.py` (line 711), `tools/extract_passages.py` (line 466)

**Problem:**  
Two tools that both call the Claude API use different HTTP clients:
- `discover_structure.py`: `import anthropic` → uses the official Anthropic Python SDK
- `extract_passages.py`: `import httpx` → makes raw HTTP POST requests

This means different error handling, different retry behavior, different request formatting, and two dependencies instead of one.

**Impact:** Maintenance burden. If the API changes, two different call sites need updating. Different error messages for the same underlying failures.

**Fix:** Standardize on one approach. The `anthropic` SDK is generally preferred (handles retries, rate limits, versioning).

---

## BUG-019 🟢 Page 0 (Title Page) Not Explicitly Excluded from Structure Discovery

**Location:** `books/imla/stage2_output/divisions.json`

**Problem:**  
In the إملاء book, page `seq_index=0` (printed page 1, containing title/publisher metadata) is not covered by any division. The first division starts at `seq_index=1`. While this is correct behavior (title pages shouldn't be in divisions), there's no explicit exclusion record or warning.

If a book has substantive content before the first HTML heading, this gap would silently drop real content.

**Impact:** Low for current data, but could become a problem for books where scholarly content begins before the first tagged heading.

**Fix:** Add a "preamble before first heading" detection that either creates a preamble division or emits a warning when `seq_index < first_division_start` contains non-trivial content.

---

## BUG-020 🟢 Gold Baselines Use Separate Atom Files While Extraction Tool Produces Combined Output

**Location:** `gold_baselines/jawahir_al_balagha/passage*/passage*_matn_atoms_v02.jsonl` + `passage*_fn_atoms_v02.jsonl` vs `output/imlaa_extraction/P004_extraction.json`

**Problem:**  
Gold baselines store matn atoms and footnote atoms in separate JSONL files. The extraction tool produces a single JSON file with a combined `atoms` array containing both matn and footnote atoms (distinguished by `source_layer`). The gold baselines also use separate `decisions.jsonl` and `taxonomy_changes.jsonl` files that have no equivalent in the extraction tool output.

**Impact:** Gold baselines cannot be directly used as few-shot examples or validation targets for the extraction tool without format conversion. The gold calibration file (`3_extraction/gold/P004_gold_excerpt.json`) bridges this gap partially but uses yet another format.

**Fix:** Document the format differences explicitly. Consider adding a conversion utility for gold baselines → extraction format.

---

## Summary

| Severity | Count | Key Items |
|----------|-------|-----------|
| 🔴 CRITICAL | 4 | Taxonomy format breaks بلاغة (BUG-001), prose_tail contradictory state (BUG-002), stale committed output (BUG-003), book_id inconsistency (BUG-004) |
| 🟡 MODERATE | 10 | Footnote preamble dropped (BUG-005), ZWNJ signal wasted (BUG-006), schema drift (BUG-007), page filter seq gaps (BUG-008), outdated model (BUG-009), hardcoded cost (BUG-010), empty/duplicate files (BUG-011), missing deps (BUG-012), wrong default path (BUG-013), empty division schema (BUG-014) |
| 🟢 LOW | 6 | Cost comment (BUG-015), stale report (BUG-016), duplicate constant (BUG-017), mixed HTTP clients (BUG-018), page 0 gap (BUG-019), gold format mismatch (BUG-020) |

### Recommended Fix Order

1. **BUG-001** (taxonomy format) — blocks all non-إملاء extraction
2. **BUG-002** (prose_tail) — causes unnecessary retries on every passage with continuations
3. **BUG-004** (book_id) — prevents reliable cross-stage data joins
4. **BUG-005** (footnote preamble) — silently drops scholarly content
5. **BUG-007** (schema drift) — prevents any meaningful schema validation
6. **BUG-012** (requirements.txt) — prevents clean installs
7. Everything else
