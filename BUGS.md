# ABD Bug Tracker

> **Audit 2 — 2026-02-27**
> Method: Adversarial cross-referencing of all documentation, code, schemas, data files, and tests after docs rewrite (PRs #6–#8).
> Scope: Every `.py` tool, every committed output file, every schema, every gold baseline, all specs, and cross-file consistency.
> Previous: Audit 1 (2025-02-27) identified 20 bugs. This audit verifies fix status and adds new findings from the docs overhaul.

---

## Severity Definitions

| Severity | Meaning |
|----------|---------|
| 🔴 CRITICAL | Blocks correct operation of a pipeline stage or produces silently wrong output |
| 🟡 MODERATE | Produces degraded output, confusing errors, or inconsistent data — but doesn't block |
| 🟢 LOW | Cosmetic, documentation, or future-proofing issue |

---

## Status Key

| Status | Meaning |
|--------|---------|
| OPEN | Not yet fixed |
| FIXED | Verified resolved |
| NEW | Found in Audit 2 |

---

## Code Bugs (Functional)

### BUG-001 🔴 FIXED — Taxonomy Format Divergence Breaks Leaf Extraction for بلاغة

**Location:** `tools/extract_passages.py` → `extract_taxonomy_leaves()` (line 911)

**Problem:**
`extract_taxonomy_leaves()` scans for `_leaf: true` via line-by-line text matching. The إملاء taxonomy uses `_leaf: true` in a nested-dict YAML structure — this works. The بلاغة taxonomy uses `leaf: true` (no underscore) in a list-of-nodes structure with explicit `id` fields. Result: **0 leaves returned** for بلاغة (expected: 143). Every excerpt placement triggers a "non-leaf" validation warning and the retry loop can never succeed.

**Verified:** Audit 2 confirmed function is unchanged.

```python
from tools.extract_passages import extract_taxonomy_leaves
with open('taxonomy/balagha/balagha_v0_4.yaml') as f:
    print(len(extract_taxonomy_leaves(f.read())))  # → 0
```

**Impact:** Extraction pipeline is completely broken for any science using the list-based taxonomy format.

**Fix:** Parse YAML properly (not line scanning). Handle both `_leaf: true` and `leaf: true` in both dict and list structures.

---

### BUG-002 🔴 FIXED — `prose_tail` Atom Type Missing from VALID_ATOM_TYPES

**Location:** `tools/extract_passages.py` → `VALID_ATOM_TYPES` constant + `post_process_extraction()`

**Problem:**
When the LLM returns `"type": "prose_tail"` (which it sometimes does despite prompt instructions), `post_process_extraction()` renames it to `atom_type: "prose_tail"` but sets `is_prose_tail: False` via `setdefault`. Validation then fires two contradictory errors: invalid atom_type WARNING + uncovered atom ERROR. The retry loop sends both back to the LLM, which gets confused.

**Verified:** Audit 2 confirmed `VALID_ATOM_TYPES` still equals `{'prose_sentence', 'bonded_cluster', 'quran_quote_standalone', 'list_item', 'heading', 'verse_evidence'}`.

**Impact:** Unnecessary retries (~$0.03–0.10 per passage) on every passage with continuation text.

**Fix:** In `post_process_extraction()`, detect `atom_type == "prose_tail"` → set `is_prose_tail = True` and change `atom_type` to `"prose_sentence"`.

---

### BUG-003 🔴 FIXED — Committed Extraction Output Is Stale (Pre-Post-Processing)

**Location:** `output/imlaa_extraction/P004_extraction.json`, `P010_extraction.json`

**Problem:**
Committed extraction outputs predate the current `post_process_extraction()` code. They use `type` instead of `atom_type`, and are missing `record_type`, `book_id`, `source_layer`, `is_prose_tail`, `bonded_cluster_trigger`, `exclusions`, and `notes`. Additionally, these files are tracked in git despite `output/` being in `.gitignore` (force-added before the gitignore rule existed).

**Verified:** Audit 2 confirmed: `P004_extraction.json` atoms have keys `['atom_id', 'note', 'role', 'text', 'type']` — missing all post-processing fields. Excerpts are missing `case_types`, `relations`, `book_id`, `record_type`, `status`, `taxonomy_version`, and 15+ other schema-required fields.

**Impact:** Anyone treating committed output as reference data gets a wrong picture of the tool's current output format.

**Fix:** Either re-run extraction and recommit, or `git rm` the stale files and add a note that `output/` is gitignored.

---

### BUG-004 🔴 FIXED — `book_id` Inconsistency Across Pipeline Stages

**Location:** Cross-cutting: registry, intake, Stage 1, Stage 2, extraction

**Problem:**
The same book uses three different IDs:

| Source | `book_id` |
|--------|-----------|
| `books/books_registry.yaml` | `imla` |
| `books/imla/intake_metadata.json` | `imla` |
| `books/imla/stage1_output/pages.jsonl` | `qawaid_imlaa` |
| `books/imla/stage2_output/passages.jsonl` | `qawaid_imlaa` |
| `output/imlaa_extraction/extraction_summary.json` | `qimlaa` |
| Atom ID prefix in extraction | `qimlaa:matn:...` |

**Verified:** Audit 2 confirmed all three IDs still present.

**Impact:** Cross-stage joins on `book_id` silently miss data.

**Fix:** Enforce single canonical book_id from Stage 0 intake metadata; propagate automatically to downstream stages.

---

### BUG-005 🟡 FIXED — Footnote Preamble Silently Dropped in Extraction

**Location:** `tools/extract_passages.py` → `get_passage_footnotes()` (line ~418)

**Problem:**
`get_passage_footnotes()` collects only the structured `footnotes` array (numbered entries). It ignores the `footnote_preamble` field entirely. For pages with `footnote_section_format: "bare_number"` or `"unnumbered"`, the ENTIRE footnote content is captured as preamble, so ALL footnote content on those pages is silently dropped.

**Verified:** Audit 2 confirmed function unchanged — still only reads `pg.get("footnotes", [])`, no mention of `footnote_preamble`.

**Fix:** Include `footnote_preamble` content in the footnote text sent to the LLM.

---

### BUG-014 🟡 OPEN — Gold Schema `divisions_schema_v0.1.json` Has Empty Division Item Definition

**Location:** `schemas/divisions_schema_v0.1.json`

**Problem:**
Division item schema has `"required": [], "properties": {}` — any object passes validation.

**Verified:** Audit 2 confirmed unchanged.

**Fix:** Populate with actual fields from committed `divisions.json` data.

---

## Documentation Bugs (Introduced or Persisted After Docs Rewrite)

### BUG-021 🔴 NEW — EXCERPTING_SPEC §4.2 Relation Types Are Completely Fabricated

**Location:** `4_excerpting/EXCERPTING_SPEC.md` §4.2 (line ~134)

**Problem:**
The spec lists 5 relation types: `prerequisite`, `builds_on`, `contrasts`, `exemplifies`, `cross_reference`. **None of these exist in the actual schema.** The real 13 relation types (from `schemas/gold_standard_schema_v0.3.3.json` and `project_glossary.md` §7) are: `footnote_supports`, `footnote_explains`, `footnote_citation_only`, `footnote_source`, `split_continues_in`, `split_continued_from`, `shared_shahid`, `exercise_tests`, `interwoven_sibling`, `cross_layer`, `has_overview`, `answers_exercise_item`, `belongs_to_exercise_set`.

Zero overlap between the spec's types and the actual types.

**Impact:** Anyone implementing excerpting from this spec would produce invalid relation types that fail schema validation. The REPO_MAP §Known Schema Drift already warns about specs vs gold, but this is a complete fabrication, not a drift.

**Fix:** Replace §4.2 relation types with the real ones from `project_glossary.md` §7 / schema. Or add a cross-reference: "See project_glossary.md §7 for the authoritative relation type list."

---

### BUG-022 🔴 NEW — EXCERPTING_SPEC §5.2 Excerpt Example Uses Wrong Field Names and ID Format

**Location:** `4_excerpting/EXCERPTING_SPEC.md` §5.2 (line ~173)

**Problem:**
The example excerpt JSON uses:
- `"excerpt_id": "EXC_001"` — should be `{book_id}:exc:000001` format
- `"placed_at": "balagha/..."` — field doesn't exist; schema uses `taxonomy_node_id`
- `"atoms": [{atom_id, role}]` flat array — schema uses separate `core_atoms[]` and `context_atoms[]`
- Missing 14+ required schema fields (`book_id`, `record_type`, `status`, `taxonomy_version`, `heading_path`, `boundary_reasoning`, `case_types`, etc.)

**Impact:** Example is misleading; extraction code implementing this example would produce invalid output.

**Fix:** Replace with a real excerpt from gold baselines or update to match `schemas/gold_standard_schema_v0.3.3.json` excerpt_record definition.

---

### BUG-023 🔴 NEW — ATOMIZATION_SPEC §5 Atom Example Uses All Wrong Field Names

**Location:** `3_atomization/ATOMIZATION_SPEC.md` §5 (line ~100)

**Problem:**
Despite being marked "SUPERSEDED", this spec is still listed in CLAUDE.md §Key Files and REPO_MAP as a reference. Its example atom uses:
- `"atom_id": "A001"` → should be `{book_id}:{layer}:{6-digit}` (e.g., `jawahir:matn:000004`)
- `"text_ar"` → schema says `text`
- `"source_page"` → schema says `page_hint` (optional)
- `"source_locator"` → schema says `source_anchor` (required)
- `"is_heading"` → schema uses `atom_type` enum (heading is a value, not a boolean)
- `"bond_group"` / `"bond_reason"` → schema uses `bonded_cluster_trigger` (structured object)

Every single field name is wrong relative to the gold schema v0.3.3.

**Impact:** Although marked superseded, the spec is still referenced. Any reader following the field names will produce schema-invalid output.

**Fix:** Either add a prominent field-name mapping table, or replace the example with one matching the current schema, or remove the spec from CLAUDE.md and REPO_MAP references entirely.

---

### BUG-024 🟡 NEW — TAXONOMY_SPEC Uses Wrong Field Names and ID Formats

**Location:** `5_taxonomy/TAXONOMY_SPEC.md` §4.1, §4.2

**Problem:**
- §4.1: Uses `placed_at` field — schema uses `taxonomy_node_id`
- §4.2: Uses `"triggered_by_excerpt": "EXC_042"` — actual format is `{book_id}:exc:000042`
- §4.2: `taxonomy_change` example is plausible but doesn't match the schema's `taxonomy_change_record` definition (missing `record_type`, using wrong field names)

**Fix:** Update field names and ID formats to match schema.

---

### BUG-025 🟡 NEW — RUNBOOK Default Model Claim Doesn't Match Code

**Location:** `3_extraction/RUNBOOK.md` line 109

**Problem:**
RUNBOOK says: `--model MODEL — Claude model to use (default: claude-sonnet-4-20250514)`
Actual code default (extract_passages.py line 1367): `default="claude-sonnet-4-5-20250929"`

The RUNBOOK was updated in PR #8 but the model default was not corrected to match the code.

**Fix:** Change RUNBOOK to say `claude-sonnet-4-5-20250929`.

---

### BUG-026 🟡 NEW — RUNBOOK Extraction JSON Description Doesn't Match Committed Output

**Location:** `3_extraction/RUNBOOK.md` §"Extraction JSON structure" (line ~155)

**Problem:**
RUNBOOK claims extraction JSON contains:
- `case_types[]` — committed output has `content_type` instead, no `case_types`
- `relations[]` — committed output has no `relations` field
- `exclusions[]` — committed output has no `exclusions` key
- `notes` — committed output has no `notes` key

The RUNBOOK describes the *intended* post-processed output format, but the committed P004/P010 files are pre-post-processing (see BUG-003). This creates confusion: docs describe one format, committed data shows another.

**Fix:** Either re-run extraction to produce current-format output, or add a note that committed output is from an older tool version.

---

### BUG-027 🟡 NEW — CLAUDE.md Test Count Is Wrong

**Location:** `CLAUDE.md` line 145

**Problem:**
CLAUDE.md says `# Unit tests (463 pass, ~9s)`. Actual result: `469 passed, 7 skipped in 11.99s`.

**Fix:** Update to `476 collected (469 pass, 7 skip, ~12s)`.

---

### BUG-028 🟡 NEW — REPO_MAP Line Counts and Test Totals Are Wrong

**Location:** `REPO_MAP.md` §Tools, §Tests

**Problem:**

| Item | REPO_MAP claims | Actual |
|------|----------------|--------|
| `tools/discover_structure.py` | ~1400 lines | 2856 lines |
| Test total | 3602 lines | 5042 lines |
| `test_structure_discovery.py` lines | — (blank) | 1440 lines |
| `test_structure_discovery.py` tests | — (blank) | 86 tests |

The `discover_structure.py` line count is off by 2x — likely the tool was significantly expanded after REPO_MAP was written. The test lines total is also 40% wrong because `test_structure_discovery.py` was omitted from the count.

Additionally, REPO_MAP is missing 4 tools entirely:
- `tools/check_env.py` (163 lines)
- `tools/checkpoint_index_lib.py` (203 lines)
- `tools/generate_checkpoint_index.py` (32 lines)
- `tools/validate_structure.py` (318 lines)

**Fix:** Update all line counts, add missing tools.

---

### BUG-029 🟡 NEW — Taxonomy Registry Missing إملاء Entry

**Location:** `taxonomy/taxonomy_registry.yaml`

**Problem:**
The registry only lists بلاغة versions (balagha_v0_2 through v0_4). `imlaa_v0.1` is completely absent despite being the only taxonomy actively used in extraction. CLAUDE.md says "taxonomy/imlaa_v0.1.yaml — إملاء taxonomy (44 leaves)" and the extraction tool uses it, but the "canonical registry" doesn't know it exists.

**Impact:** Any code that resolves taxonomies through the registry (as REPO_MAP instructs: "The production pipeline MUST resolve taxonomy trees through this registry") will find no إملاء tree.

**Fix:** Add `imlaa` science entry with `imlaa_v0.1` version to the registry.

---

### BUG-030 🟡 NEW — CLAUDE.md "What Needs to Be Built" Lists بلاغة Tree as Missing

**Location:** `CLAUDE.md` line 252

**Problem:**
Line 252 says: *"Taxonomy trees for صرف, نحو, بلاغة (base outlines to be provided, then evolve with books)"*
But بلاغة already has a 143-leaf taxonomy tree (balagha_v0_4.yaml), actively used by gold baselines. Line 214 correctly says only "صرف and نحو trees: not yet created."

This is contradictory within the same file. The "What needs to be built" list is misleading.

**Fix:** Change line 252 to "Taxonomy trees for صرف, نحو" only. Or clarify that the بلاغة tree exists but hasn't been tested with the automated extraction pipeline.

---

## Repo Hygiene / Data Issues

### BUG-031 🟡 NEW — `output/` Files Tracked in Git Despite `.gitignore` Rule

**Location:** `.gitignore` + `output/imlaa_extraction/`

**Problem:**
`.gitignore` has `output/` but `git ls-files output/` shows 5 tracked files (P004/P010 extraction + reviews + summary). These were force-added before the gitignore rule was created. Git continues tracking them, so `git status` won't flag them as untracked, and `git diff` will show changes if they're modified.

**Impact:** Confusing: gitignore says "don't track output" but git tracks output. New contributors may not realize these files are stale artifacts.

**Fix:** Either `git rm --cached output/` to untrack them (keeping them locally), or document why they're an intentional exception.

---

### BUG-032 🟡 NEW — 4 Old Normalization Spec Versions Cluttering `1_normalization/`

**Location:** `1_normalization/`

**Problem:**
Five normalization spec files exist: `NORMALIZATION_SPEC.md` (unnumbered), `_v0.2.md`, `_v0.3.md`, `_v0.4.md`, `_v0.5.md`. Only v0.5 is current. The other four are superseded. Unlike `archive/precision_deprecated/` (which has a `DO_NOT_READ.md` warning), these old specs sit alongside the current one with no warning.

**Impact:** A reader may accidentally read v0.3 or v0.4 instead of v0.5 and follow outdated rules.

**Fix:** Move old versions to `archive/` or add version indicators making it clear only v0.5 is current.

---

### BUG-033 🟢 NEW — `jawahir_normalized.jsonl` Is an Empty File (0 bytes)

**Location:** `1_normalization/jawahir_normalized.jsonl`

**Problem:**
This file is 0 bytes — completely empty. Its sibling `jawahir_normalized_full.jsonl` (144KB) has content. The empty file appears to be an aborted run or a mistake. Both files are in a spec directory, not a data output directory.

**Fix:** Delete the empty file. Move `jawahir_normalized_full.jsonl` to `books/jawahir/stage1_output/` or delete if stale.

---

### BUG-034 🟢 NEW — Stale Analysis Reports in `1_normalization/`

**Location:** `1_normalization/STAGE1_AUDIT_REPORT.md`, `STAGE1_CRITICAL_ANALYSIS.md`, `STAGE1_ROUND2_ANALYSIS.md`

**Problem:**
These are one-time analysis documents from Stage 1 development. They reference specific bugs and findings that may have been fixed. They sit alongside active specs without any staleness indicator.

**Impact:** Low — useful as historical reference, but a new reader might treat findings as current issues.

**Fix:** Move to `archive/` or add a header noting they're historical.

---

## Previously Reported (Status Updates)

### BUG-006 🟡 OPEN — ZWNJ Heading Signal Wasted in Extraction

Still unfixed. `get_passage_footnotes()` and the extraction prompt don't use ZWNJ markers.

### BUG-007 🟡 OPEN — Schema Drift Between Gold v0.3.3 and Extraction Output

Still applies. Extraction output has 11 fields; gold schema requires 14+ fields on excerpts. Extraction atoms have 5 fields; schema requires 7+. The REPO_MAP §Known Schema Drift documents this, but nothing has converged.

### BUG-008 🟡 OPEN — Page Filter May Miss Pages Due to seq_index Gaps

Unchanged. `seq_index` uniqueness is not enforced.

### BUG-009 🟡 OPEN — `discover_structure.py` Uses Sonnet 4 While `extract_passages.py` Uses Sonnet 4.5

Partially updated: `extract_passages.py` now defaults to `claude-sonnet-4-5-20250929`, but `discover_structure.py` still uses `claude-sonnet-4-20250514`. The inconsistency remains.

### BUG-010 🟢 OPEN — Hardcoded Sonnet 3.5 Cost Calculation in `extract_passages.py`

Still present at line ~1203. Comment says "Sonnet pricing" but model is now Sonnet 4.5.

### BUG-011 🟢 OPEN — Empty/Duplicate Files in Repository

Unchanged.

### BUG-012 🟡 OPEN — `requirements.txt` Missing `httpx` Dependency

`requirements.txt` only lists `PyYAML>=6.0`. `httpx` is required by `extract_passages.py` and `anthropic` SDK is required by `discover_structure.py`. Neither is listed. CLAUDE.md correctly mentions `pip install PyYAML httpx` but `requirements.txt` is incomplete.

### BUG-013 🟡 OPEN — Normalization Default Output Path Mismatch

Still defaults to `books/{book_id}/pages.jsonl` instead of `books/{book_id}/stage1_output/pages.jsonl`.

### BUG-015 🟢 OPEN — Cost Comment References Wrong Model

Unchanged.

### BUG-016 🟢 OPEN — `jawahir_normalization_report.json` Uses Older Report Schema

Unchanged.

### BUG-017 🟢 ~~OPEN~~ NOT A BUG — ~~Duplicate~~ `LLM_DEFAULT_MODEL` in `discover_structure.py`

**False positive.** `LLM_DEFAULT_MODEL` is defined exactly once (line 704) and used once (line 722 as default argument). There is no duplication. The original audit's "grep confirms two identical definitions" claim was incorrect — grep found the definition and the usage, not two definitions.

### BUG-018 🟢 OPEN — Mixed HTTP Clients (`anthropic` SDK vs raw `httpx`)

Unchanged.

### BUG-019 🟢 OPEN — Page 0 Not Explicitly Excluded from Structure Discovery

Unchanged.

### BUG-020 🟢 OPEN — Gold Baselines vs Extraction Tool Use Different Output Formats

Unchanged.

---

## New Fixes (Audit 3 — 2026-02-28)

### BUG-035 🔴 FIXED — Validation Missed Duplicate Atom IDs

**Location:** `tools/extract_passages.py` → `validate_extraction()`

**Problem:** No check for duplicate atom_id values within a passage. If the LLM produces two atoms with the same ID, both pass validation silently.

**Fix:** Added Check 2b: duplicate atom_id detection.

---

### BUG-036 🔴 FIXED — Ghost Atom References Counted as Coverage

**Location:** `tools/extract_passages.py` → `validate_extraction()` Check 6

**Problem:** `covered_atoms.add(aid)` was called unconditionally for every atom reference in excerpts, even when the referenced atom didn't exist in the atoms list. This meant ghost references inflated the coverage count, potentially hiding uncovered atoms.

**Fix:** Only count atoms that actually exist: `elif aid: covered_atoms.add(aid)`.

---

### BUG-037 🟡 FIXED — Empty core_atoms Passed Validation

**Location:** `tools/extract_passages.py` → `validate_extraction()` Check 5

**Problem:** An excerpt with `"core_atoms": []` (empty list) passed all validation checks despite being semantically invalid — an excerpt must contain at least one atom.

**Fix:** Added Check 5b: empty core_atoms detection.

---

### BUG-038 🔴 FIXED — Evolution Engine Included Invalid Node IDs in Proposals

**Location:** `tools/evolve_taxonomy.py` → `propose_evolution_for_signal()`

**Problem:** When the LLM proposed new node IDs that failed validation (uppercase, spaces, Arabic characters, duplicates), the invalid nodes were flagged with a warning but still included in the proposal's `validated_nodes` list. This meant invalid IDs could propagate to the taxonomy.

**Fix:** Invalid nodes are now excluded from `validated_nodes` and added to `rejected_nodes`. If all nodes are invalid, the function returns `None`. If some are invalid, confidence is downgraded to `"uncertain"`.

---

### BUG-039 🟡 FIXED — Cluster Signals Not Book-Aware

**Location:** `tools/evolve_taxonomy.py` → `scan_cluster_signals()`

**Problem:** Cluster detection keyed on `node_id` alone, not `(book_id, node_id)`. This meant excerpts from *different* books at the same leaf incorrectly triggered a "same_book_cluster" evolution signal. Multiple books contributing to the same leaf is expected behavior, not an evolution trigger.

**Fix:** Cluster detection now groups by `(book_id, node_id)`. Only multiple excerpts from the same book at the same node trigger a signal.

---

### BUG-040 🔴 FIXED — VALID_SCIENCES Hardcoded Blocks New Sciences

**Location:** `tools/assemble_excerpts.py` line 45, `tools/intake.py` line 31

**Problem:** `VALID_SCIENCES = {"imlaa", "sarf", "nahw", "balagha"}` was enforced at runtime. Any attempt to process a new science (fiqh, hadith, عقيدة, etc.) was rejected immediately. The engine is architecturally science-agnostic, but this validation blocked extensibility.

**Fix:** Renamed to `KNOWN_SCIENCES` (informational), changed from hard error to warning. Removed `choices=` restriction from intake.py's argparse. Updated help text across all tools to show open-ended science names.

---

## Summary

| Severity | Count | Open | Fixed |
|----------|-------|------|-------|
| 🔴 CRITICAL | 11 | 3 | 8 (BUG-001, 002, 003, 004, 035, 036, 038, 040) |
| 🟡 MODERATE | 20 | 14 | 6 (BUG-005, 027, 030, 037, 039 + audit 3) |
| 🟢 LOW | 10 | 8 | 0 |
| **Total** | **41** | **25** | **14** |

**14 bugs fixed across Audit 2–3.** All pipeline-blocking bugs (Tier 1) are resolved. Remaining open bugs are doc inaccuracies, schema drift, and low-priority cleanup.

**Test suite:** 811 passed, 2 failed (pre-existing Windows cp1252 encoding in structure discovery), 7 skipped. Engine tests (extraction + evolution + assembly): 254 passed.

### Remaining Fix Priority

**Tier 1 — Doc inconsistencies (no functional impact but misleading):**
1. **BUG-021, 022, 023** (fabricated/wrong field names in specs) — misleading for implementers
2. **BUG-029** (taxonomy registry missing imlaa) — registry contract broken

**Tier 2 — Quality improvements:**
3. **BUG-012** (requirements.txt missing httpx) — prevents clean installs
4. **BUG-006** (ZWNJ heading signal wasted) — minor data loss
5. **BUG-007** (schema drift) — extraction vs gold schema mismatch

**Tier 3 — Low priority:**
6. Everything else (BUG-008–020, 024–028, 031–034)
