# ABD Development Roadmap

> This file is the **strategic task list** for ABD development. The overnight autonomous system reads this file to determine what to work on next. Update task statuses after each session.
>
> **Task selection rule:** Work on the first `TODO` task whose dependencies are all `DONE`.

---

## Status Key

| Status | Meaning |
|--------|---------|
| `TODO` | Not started |
| `IN_PROGRESS` | Partially done (notes explain what remains) |
| `DONE` | Completed and verified |
| `BLOCKED` | Cannot proceed (reason documented) |
| `HUMAN` | Needs human decision before proceeding |

---

## Phase 1: Stabilize the Foundation

> Fix critical bugs so the pipeline works correctly on ALL sciences.

### 1.1 — Fix taxonomy leaf extraction for v1 format
- **Status:** `TODO`
- **Bug:** BUG-001
- **Location:** `tools/extract_passages.py` → `extract_taxonomy_leaves()` (line 911)
- **Problem:** Function uses line-by-line text matching for `_leaf: true`. The v1 taxonomy format uses `leaf: true` (no underscore) in a list-of-nodes structure with explicit `id` fields. Returns 0 leaves for all v1 taxonomies.
- **Fix:** Parse YAML properly with `yaml.safe_load()`. Walk the tree recursively. Handle both `_leaf: true` (v0 nested-dict) and `leaf: true` (v1 list-of-nodes).
- **Acceptance criteria:**
  - `extract_taxonomy_leaves()` returns correct leaf count for all v1 files:
    - `imlaa_v1_0.yaml` → 105 leaves
    - `sarf_v1_0.yaml` → 226 leaves
    - `nahw_v1_0.yaml` → 226 leaves
    - `balagha_v1_0.yaml` → 335 leaves
  - Also still works for v0 format (`imlaa_v0.1.yaml` → 44 leaves)
  - New parametrized test covering all taxonomy files
- **Depends on:** —

### 1.2 — Handle prose_tail atom type
- **Status:** `TODO`
- **Bug:** BUG-002
- **Location:** `tools/extract_passages.py` → `post_process_extraction()`
- **Problem:** When LLM returns `"type": "prose_tail"`, it's not in `VALID_ATOM_TYPES`. Causes contradictory validation errors.
- **Fix:** In `post_process_extraction()`, detect `atom_type == "prose_tail"` → set `is_prose_tail = True`, change `atom_type` to `"prose_sentence"`.
- **Acceptance criteria:**
  - Atom with `"type": "prose_tail"` is correctly transformed
  - No validation errors fire for prose_tail atoms
  - Test with inline data confirming the transformation
- **Depends on:** —

### 1.3 — Enforce canonical book_id across pipeline
- **Status:** `TODO`
- **Bug:** BUG-004
- **Location:** Cross-cutting: intake, normalization, structure discovery, extraction
- **Problem:** Same book has 3 different IDs: `imla`, `qawaid_imlaa`, `qimlaa`
- **Fix:** Use `book_id` from `intake_metadata.json` as canonical. Add `--book-id` validation in downstream tools that cross-checks against intake metadata. Update committed test data.
- **Acceptance criteria:**
  - `pages.jsonl` uses same `book_id` as `intake_metadata.json`
  - `passages.jsonl` uses same `book_id` as `intake_metadata.json`
  - Extraction uses same `book_id` as `intake_metadata.json`
  - Test verifying consistency
- **Depends on:** —

### 1.4 — Include footnote preamble in extraction
- **Status:** `TODO`
- **Bug:** BUG-005
- **Location:** `tools/extract_passages.py` → `get_passage_footnotes()` (line ~418)
- **Problem:** `get_passage_footnotes()` ignores `footnote_preamble` field. For pages with `"bare_number"` or `"unnumbered"` format, ALL footnote content is lost.
- **Fix:** Read `footnote_preamble` field and prepend to footnote text sent to LLM.
- **Acceptance criteria:**
  - Function returns preamble content for pages with `footnote_preamble`
  - Test with `footnote_section_format: "bare_number"` page
- **Depends on:** —

### 1.5 — Complete requirements.txt
- **Status:** `TODO`
- **Bug:** BUG-012
- **Fix:** Add `httpx` and `anthropic` to `requirements.txt`.
- **Acceptance criteria:** `pip install -r requirements.txt` installs all dependencies for all tools.
- **Depends on:** —

### 1.6 — Fix normalization default output path
- **Status:** `TODO`
- **Bug:** BUG-013
- **Fix:** Change default from `books/{book_id}/pages.jsonl` to `books/{book_id}/stage1_output/pages.jsonl`.
- **Acceptance criteria:** Default output path matches convention. Existing tests still pass.
- **Depends on:** —

### 1.7 — Align extraction output with gold schema
- **Status:** `TODO`
- **Bug:** BUG-007
- **Location:** `tools/extract_passages.py` → `post_process_extraction()`
- **Fix:** Ensure output includes all fields required by `schemas/gold_standard_schema_v0.3.3.json`. Add missing fields with sensible defaults where appropriate.
- **Acceptance criteria:** Post-processed extraction output validates against gold schema. Diff between current fields and schema fields is zero.
- **Depends on:** 1.1, 1.2

---

## Phase 2: Documentation Integrity

> Specs match reality. Anyone reading specs produces valid output.

### 2.1 — Fix EXCERPTING_SPEC relation types
- **Status:** `TODO`
- **Bug:** BUG-021
- **Fix:** Replace §4.2 with real 13 relation types from `project_glossary.md` §7.
- **Acceptance criteria:** Every relation type in EXCERPTING_SPEC exists in `project_glossary.md` §7.
- **Depends on:** —

### 2.2 — Fix EXCERPTING_SPEC excerpt example
- **Status:** `TODO`
- **Bug:** BUG-022
- **Fix:** Replace §5.2 example with one matching `schemas/gold_standard_schema_v0.3.3.json`.
- **Acceptance criteria:** Example excerpt validates against schema. All field names match.
- **Depends on:** —

### 2.3 — Fix ATOMIZATION_SPEC field names
- **Status:** `TODO`
- **Bug:** BUG-023
- **Fix:** Replace §5 example field names or add mapping table.
- **Acceptance criteria:** Either example matches schema OR mapping table is complete and accurate.
- **Depends on:** —

### 2.4 — Fix TAXONOMY_SPEC field names
- **Status:** `TODO`
- **Bug:** BUG-024
- **Fix:** Replace `placed_at` → `taxonomy_node_id`, fix ID format.
- **Depends on:** —

### 2.5 — Fix RUNBOOK model and JSON claims
- **Status:** `TODO`
- **Bugs:** BUG-025, BUG-026
- **Fix:** Update default model to `claude-sonnet-4-5-20250929`. Align JSON structure with actual output.
- **Depends on:** —

### 2.6 — Fix CLAUDE.md and REPO_MAP counts
- **Status:** `TODO`
- **Bugs:** BUG-027, BUG-028, BUG-030
- **Fix:** Update test counts, line counts, add missing tools, remove بلاغة from "missing trees" list.
- **Depends on:** —

### 2.7 — Clean stale output and old specs
- **Status:** `TODO`
- **Bugs:** BUG-003, BUG-031, BUG-032, BUG-033, BUG-034
- **Fix:** `git rm --cached output/`. Move old normalization specs to `archive/`. Delete empty JSONL. Add historical headers.
- **Depends on:** —

---

## Phase 3: Extraction Hardening — بلاغة Verification

> Prove extraction works on بلاغة by matching gold baselines.

### 3.1 — Build gold comparison tool
- **Status:** `TODO`
- **Description:** Create `tools/compare_gold.py` that takes extraction output + gold baseline and reports alignment metrics.
- **Input:** extraction JSON + gold passage directory
- **Output:** Report with: atom count diff, text coverage %, excerpt boundary alignment, taxonomy placement accuracy
- **Acceptance criteria:** Tool runs on passage 1 gold, produces meaningful metrics
- **Depends on:** Phase 1 complete

### 3.2 — Run extraction on jawahir passage 1
- **Status:** `TODO`
- **Description:** Run `extract_passages.py` on jawahir passage 1 using `balagha_v1_0.yaml` taxonomy. Requires API key.
- **Acceptance criteria:** Extraction completes without errors, produces valid JSON output
- **Depends on:** 3.1, 1.1

### 3.3 — Analyze discrepancies and tune prompts
- **Status:** `TODO`
- **Description:** Compare extraction output vs gold. Categorize discrepancies by root cause. Iterate on extraction prompts.
- **Acceptance criteria:** ≥80% atom alignment, ≥70% excerpt boundary match with gold passage 1
- **Depends on:** 3.2

### 3.4 — Verify passages 2 and 3
- **Status:** `TODO`
- **Description:** Run extraction on passages 2-3, compare vs gold.
- **Acceptance criteria:** ≥80% alignment on both passages
- **Depends on:** 3.3

### 3.5 — Build regression test suite
- **Status:** `TODO`
- **Description:** Freeze verified outputs as regression anchors in test suite.
- **Acceptance criteria:** `pytest` includes extraction quality regression tests
- **Depends on:** 3.4

### 3.6 — Cross-science test: صرف
- **Status:** `TODO`  
- **Description:** Run extraction on شذا العرف. Flag for `HUMAN` review.
- **Depends on:** 3.5

### 3.7 — Cross-science test: نحو
- **Status:** `TODO`
- **Description:** Run extraction on قطر الندى. Flag for `HUMAN` review.
- **Depends on:** 3.5

---

## Phase 4: Multi-Model Consensus Engine

> Two models extract independently; agreements auto-merge, disagreements flagged.

### 4.1 — Add OpenAI extraction path
- **Status:** `TODO`
- **Depends on:** Phase 3 complete

### 4.2 — Define consensus data model
- **Status:** `TODO`
- **Depends on:** —

### 4.3 — Build atom-level alignment
- **Status:** `TODO`
- **Depends on:** 4.1, 4.2

### 4.4 — Build excerpt-level alignment
- **Status:** `TODO`
- **Depends on:** 4.3

### 4.5 — Build arbiter
- **Status:** `TODO`
- **Depends on:** 4.4

### 4.6 — Build consensus CLI
- **Status:** `TODO`
- **Depends on:** 4.5

### 4.7 — Test on gold passages
- **Status:** `TODO`
- **Depends on:** 4.6

---

## Phase 5: Assembly + Distribution

### 5.1 — Design excerpt file format
- **Status:** `TODO`
- **Depends on:** Phase 3 complete

### 5.2 — Build assembly tool
- **Status:** `TODO`
- **Depends on:** 5.1

### 5.3 — Build self-containment validator
- **Status:** `TODO`
- **Depends on:** 5.2

### 5.4 — Build folder distribution tool
- **Status:** `TODO`
- **Depends on:** 5.2

### 5.5 — Build coverage validator
- **Status:** `TODO`
- **Depends on:** 5.4

### 5.6 — End-to-end test
- **Status:** `TODO`
- **Depends on:** 5.5

---

## Phase 6: Taxonomy Evolution Engine

### 6.1–6.7 — See ABD_AUTONOMOUS_SYSTEM.md for full breakdown
- **Status:** `TODO`
- **Depends on:** Phase 5 complete

---

## Phase 7: Feedback Learning System

### 7.1–7.6 — See ABD_AUTONOMOUS_SYSTEM.md for full breakdown
- **Status:** `TODO`
- **Depends on:** Phase 5 complete

---

## Phase 8: Cross-Validation Layers

### 8.1–8.4 — See ABD_AUTONOMOUS_SYSTEM.md for full breakdown
- **Status:** `TODO`
- **Depends on:** Phase 4 complete

---

## Last Updated

- **Date:** 2026-02-28
- **Last completed task:** — (initial creation)
- **Next priority:** Task 1.1 (BUG-001: taxonomy format)
