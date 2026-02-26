# Stage 1 Critical Audit Report

**Date:** 2026-02-26
**Scope:** Full code review + corpus-wide stress test (332 books, 167,106 pages, 165,175 footnotes)
**Files reviewed:** `normalize_shamela.py` (943 lines), `test_normalization.py` (1,324 lines), `NORMALIZATION_SPEC_v0.2.md` (342 lines)

---

## CRITICAL — Must Fix Before Stage 2

### 1. Unique Key Guarantee is Broken

**The spec claims** `(book_id, volume, page_number_int)` is a guaranteed unique key (§3).

**Reality:** 99 of 332 books (29.8%) have duplicate keys. 1,541 total duplicate page records.

**Root cause:** Shamela exports sometimes repeat the same page number for consecutive physical pages. This happens in books with editorial pagination errors, appendices, or مقدمة sections using the same numbering as the body.

**Impact on Stage 2+:** Every downstream stage will reference pages by this key. Duplicate keys mean lost data, corrupt cross-references, and ambiguous passage boundaries.

**Fix:** Add a `seq_index` field — a zero-based document-order index assigned during normalization. This is monotonically increasing and globally unique within a book, regardless of page number collisions. The compound key becomes `(book_id, volume, page_number_int, seq_index)`, but consumers can use `seq_index` alone as an unambiguous page reference.

```json
{
  "record_type": "normalized_page",
  "seq_index": 74,
  "volume": 1,
  "page_number_int": 79,
  ...
}
```

### 2. `has_verse` Has a 13.6% False Positive Rate

**The spec says** (§4.8, V2): `has_verse = true` when page contains `…` (U+2026).

**Reality:** 74,399 pages flagged as containing verse. Of these, 10,108 (13.6%) have only a lone `…` that is a prose continuation marker, not a hemistich separator. The remaining 64,291 are genuine verse (balanced hemistich pattern or star markers).

**Root cause:** The horizontal ellipsis `…` is used in Arabic prose for truncation, omission, and continuation — not exclusively for verse. A lone `…` on a line or within a quotation is not poetry.

**Impact on Stage 2+:** Verse pages receive special handling (verse lines aren't split into prose atoms). False positives would cause prose to be incorrectly treated as verse, creating corrupted excerpts.

**Fix:** Tighten the detection heuristic. A `…` should only trigger `has_verse` when it appears on a line with text on both sides (balanced hemistich pattern): `left_text … right_text` where both sides are ≥ 5 characters. Star markers (`* text *`) remain a trigger as-is.

### 3. Spec–Code Mismatch: Table Cell Separator

**Spec TAB2** says cells are joined with `\t` (tab). The code uses ` | ` (pipe with spaces) on line 337.

**Impact:** Minor, but any downstream parser expecting tab-separated table content will break.

**Fix:** Either update the code to use `\t` or update the spec. Given that ` | ` is more human-readable and there are only 104 pages with tables across the entire corpus, updating the spec to match the code is the pragmatic choice. The important thing is that they agree.

---

## IMPORTANT — Should Fix

### 4. `footnote_ref_numbers` Contains Duplicates

When footnote `(1)` is referenced twice on the same page (common in jawahir — 90 of 308 pages), `footnote_ref_numbers` contains `[1, 1, 2, 3]` instead of `[1, 2, 3]`.

**Impact:** The field's semantics are ambiguous. Is it "the set of footnote numbers referenced" or "the ordered list of all ref occurrences"? Stage 2 needs a clear contract.

**Fix:** Choose one semantic and document it. Recommended: keep it as a unique sorted list `[1, 2, 3]` (a set). The occurrence count is not useful downstream. Add deduplication: `footnote_ref_numbers: sorted(set(fn_refs))`.

### 5. ZWNJ Section Heading Markers — Undocumented Gold

15,814 pages (9.5% of corpus) start with `‌‌` (double U+200C ZERO WIDTH NON-JOINER). These consistently mark section headings in Shamela exports: المقدمة, الفصل الأول, الكتاب الثاني, etc.

**Impact:** This is extremely valuable for Stage 2 (Structure Discovery), but it's completely undocumented. The normalizer correctly preserves ZWNJ (it's source data), but nobody knows it's there or what it means.

**Fix:** Document the pattern in the spec. Add a `has_zwnj_heading` boolean flag to the output record so Stage 2 can use it as a high-confidence structural signal without needing to re-scan text. This is a free gift — the data is already there, it just needs to be exposed.

### 6. Cross-Page Footnote Warnings Are Noisy

The warning `"Footnotes with no matching ref in matn"` fires for both genuine orphans (editorial notes without refs) and cross-page footnotes (ref on page N, footnote text on page N+1). After our regex fix, 613 pages still trigger this warning, but 65 are cross-page (legitimate) and 548 are source-inherent.

**Fix:** Split into two distinct warning types: `CROSS_PAGE_FN` (when orphan fn numbers match previous page's refs) and `ORPHAN_FN` (when they don't). This requires tracking `prev_page_refs` during `normalize_book`, not just per-page. The warning classification gives Stage 2 actionable information.

---

## DESIGN CONCERNS — For Future-Proofing

### 7. `page_start`/`page_end` is Volume-Blind

The `--page-start` and `--page-end` CLI flags filter identically across ALL volumes. For a 3-volume book with restarted pagination, `--page-start 1 --page-end 5` returns pages 1–5 from every volume (~15 pages), not just one.

**Impact:** Confusing behavior. Not a bug per se (the filter is clearly documented as page-number-based), but there's no way to target a specific volume.

**Fix:** Add `--volume` flag for multi-volume mode that limits processing to a single volume. Low priority since the CLI is mainly for debugging.

### 8. Silent Data Loss on Non-UTF-8 Files

Files are read with `encoding="utf-8", errors="ignore"`, which silently drops invalid bytes. Currently all 788 corpus files are clean UTF-8, so zero impact. But a future Shamela export encoded in Windows-1256 (common for older Arabic software) would lose data silently.

**Fix:** Add encoding detection. Read as bytes first, check for BOM or try UTF-8 strict. If UTF-8 fails, try Windows-1256, then raise if nothing works. Log the detected encoding in the normalization report.

### 9. Source Hash Computed from Decoded Text, Not Raw Bytes

`normalize_book` computes `source_sha256` from `html_text.encode("utf-8")` — the text after decoding. Stage 0 computes SHA from raw file bytes. Currently they match (all files are UTF-8), but if issue #8 ever triggers, the hashes will diverge.

**Fix:** Compute the hash from the original file bytes, not the decoded text. Pass `raw_bytes_hash` as a parameter to `normalize_book`.

### 10. No Idempotency Guard

Nothing prevents normalizing the same book twice, silently overwriting `pages.jsonl` and `normalization_report.json`. In a multi-stage pipeline, accidental re-runs can corrupt state.

**Fix:** Check if output files exist before writing. Add `--force` flag to override. Write a `.normalization_complete` marker file after successful normalization that Stage 2 can check as a gate.

### 11. The `raw_matn_html` Field Stores Post-Header-Removal HTML

`raw_matn_html` is set after `PAGE_HEAD_RE.sub("", page_html)` and after splitting at the footnote separator. This means it's not truly "raw" — it's the matn portion after two transformations. The gold sample tests rely on re-normalizing from `raw_matn_html`, which works only because those two steps are excluded from the test.

**Fix:** Rename to `matn_html` (drop "raw" prefix) to avoid confusion. Or store the truly raw `page_html` block and re-derive matn/fn in tests. Low priority since `raw_matn_html` is debugging-only and not in the JSONL output.

---

## What's Solid

These aspects passed rigorous stress-testing and need no changes:

- **Core tag stripping pipeline** (T1–T4): Zero residual HTML in 167,106 pages of output. Flawless.
- **Footnote parsing** (L1–L4): Correct for all 165,175 footnotes. Monotonic-merge logic handles sub-points correctly.
- **Source fidelity** (§4.1): Diacritics, tatweel, Unicode forms all preserved exactly. Zero forbidden transformations detected.
- **Multi-volume support** (VOL1–VOL4): Correct volume tagging, ordering, and pagination across all multi-volume books.
- **Image-only detection** (IMG1–IMG2): Correct for all 3 image-only pages.
- **Whitespace normalization** (W1–W5): Correct behavior. ZWNJ preserved. No original double spaces in corpus (all are HTML artifacts).
- **Determinism**: Same input → identical output. Verified across multiple runs.
- **Performance**: 167,106 pages in 21.5 seconds (7,770 pages/sec). No bottlenecks.

---

## Recommended Fix Priority

| # | Issue | Severity | Effort | Fix |
|---|-------|----------|--------|-----|
| 1 | Duplicate keys | CRITICAL | Small | Add `seq_index` field |
| 2 | has_verse false positives | CRITICAL | Small | Tighten `…` heuristic |
| 3 | Spec–code mismatch (tables) | IMPORTANT | Trivial | Update spec |
| 4 | Duplicate footnote_ref_numbers | IMPORTANT | Trivial | Deduplicate to set |
| 5 | ZWNJ heading markers | IMPORTANT | Small | Add flag + document |
| 6 | Cross-page fn warning split | IMPORTANT | Medium | Track prev_page_refs |
| 7 | Volume-blind page filtering | LOW | Small | Add --volume flag |
| 8 | Silent encoding loss | LOW | Small | Add encoding detection |
| 9 | Hash from decoded text | LOW | Trivial | Hash raw bytes |
| 10 | No idempotency guard | LOW | Small | Check existing output |
| 11 | Misleading raw_matn_html name | LOW | Trivial | Rename field |
