# Stage 1 Round 2 Critical Analysis — Bulletproofing for Stage 2

**Date:** 2026-02-26
**Scope:** Adversarial code review + 11 targeted corpus probes (332 books, 167,106 pages)
**Baseline:** Post C1+C2 fixes, 172/172 tests pass
**Objective:** Ensure Stage 1 output is a foundation that Stage 2 can trust unconditionally.

---

## NEW CRITICAL — Fix Before Stage 2

### N1. 78% of "Preamble" Is Actually Unparsed Bare-Number Footnotes (MISCLASSIFICATION)

**Severity:** 🔴 CRITICAL — 24,775 pages have structurally misclassified footnotes

The C1 fix correctly captures text before the first `(N)` marker. However, **24,775 pages** (78.8% of all preamble pages) have footnote sections that use bare-number format (`1 text` instead of `(1) text`). Since `parse_footnotes()` only recognizes `(N)` markers, the **entire footnote section** lands in `footnote_preamble` with `footnotes=[]`.

**Preamble content breakdown (31,453 pages total):**

| Category | Pages | % | Example |
|----------|-------|---|---------|
| Bare-number footnotes (`1 text`, `2 text`) | 24,775 | 78.8% | `1 تاريخ النقد الأدبي...` |
| Long unnumbered commentary | 3,315 | 10.5% | Verse citations, editorial |
| True preamble (before real `(N)` footnotes) | 3,094 | 9.8% | Bibliographic refs before (1) |
| Short unnumbered | 159 | 0.5% | Brief notes |
| Verse citations | 102 | 0.3% | Poetry in footnote section |
| Letter-marker footnotes `(أ)`, `(ب)` | 8 | 0.0% | Letter-based enumeration |

**Impact on Stage 2:**
- `pages_with_footnotes` undercounts by ~25K pages
- `footnotes` list is empty for 25K pages that DO have footnotes
- Footnote cross-referencing impossible for these pages
- Stage 2 must parse `footnote_preamble` to extract individual notes

**The content is NOT lost** — it's correctly captured in `footnote_preamble`. But the classification is wrong and the report metrics are misleading.

**Fix:** Add a `footnote_section_format` field to PageRecord and JSONL output. Detect the format by checking what markers the footnote section uses:

```
"footnote_section_format": "numbered_parens"  — standard (1), (2) format
"footnote_section_format": "bare_number"      — 1 text, 2 text format
"footnote_section_format": "unnumbered"       — text without any numbering
"footnote_section_format": "none"             — no footnote section at all
```

Also: split the warning into `FN_PREAMBLE` (true preamble before `(N)` fns) vs `FN_UNPARSED_SECTION` (entire section without `(N)` markers). Add `pages_with_unparsed_fn_section` to the report so Stage 2 knows the real number.

**Why not parse bare-number footnotes now?** `\n1 text` is ambiguous — it could be a footnote or an enumerated list or a page reference. Since this text is in the footnote section (after `<hr>`), it's almost certainly footnote content. But correctly splitting individual bare-number notes requires heuristics (is `3` a new footnote or the number 3 in a sentence?). This is better handled by Stage 2 with LLM assistance. Stage 1's job is to capture and classify, not interpret.

---

### N2. `detect_verse()` Has 667 Remaining False Positives from Uncovered "Etc." Variants

**Severity:** 🟡 IMPORTANT — misclassification (not data loss)

The I1 fix excluded `… إلخ` patterns, but three alternate spellings of "etcetera" are not excluded:

| Pattern | Occurrences | Currently excluded? |
|---------|-------------|-------------------|
| `… إلخ` | 399 | ✅ Yes |
| `… الخ` | 455 | ❌ No |
| `… إلى آخره` | 166 | ❌ No |
| `… إلى آخر` | 46 | ❌ No |
| **Total remaining** | **667** | |

**Fix:** Expand the exclusion in `detect_verse()`:

```python
# Exclude prose "etcetera" patterns (all known variants)
ETC_PATTERNS = ("إلخ", "الخ", "إلى آخره", "إلى آخر")
if any(right.startswith(pat) for pat in ETC_PATTERNS):
    continue
```

---

### N3. Duplicate Page Numbers Generate No Warning

**Severity:** 🟡 IMPORTANT — Stage 2 could process duplicate content twice

3 books have duplicate `page_number_int` values within the same volume:

| Book | Volume | Duplicates |
|------|--------|-----------|
| الأسلوب | v1 | p79×2, p102×2, p178×2, p190×2 |
| الإيضاح في علوم البلاغة | v1-v3 | 11 duplicate pairs |
| البديع عند الحريري | v1 | p295×2, p296×2, p303×2, p305×2, p307×2+ |

`seq_index` correctly disambiguates them (each gets a unique index). But there is **no warning** generated and no metric in the report. Stage 2 needs to know about duplicates to avoid:
- Double-processing the same content
- Incorrect page cross-references
- Excerpt boundary errors at duplicate page joins

**Fix:** In `normalize_book()`, after building the page list, check for duplicate `page_number_int` values per volume. Emit `DUPLICATE_PAGE` warning for each duplicate. Add `pages_with_duplicate_numbers` to `NormalizationReport`.

---

## IMPORTANT — Should Fix

### N4. Single FN_REF_IN_MATN_RE False Negative Due to ZWNJ

**Severity:** 🟢 LOW — 1 page in entire corpus

One page (المرتجل في شرح الجمل لابن الخشاب p201) has `(1)‌‌` where a ZWNJ character (U+200C) sits between the `)` and the following space. The regex `\s*` after `)` can't match ZWNJ, so the ref isn't stripped.

**Impact:** 1 unstripped footnote ref in 167K pages. The content is preserved (not lost). The orphan footnote warning is already generated.

**Fix (optional):** Add `\u200c*` after the `)` in `FN_REF_IN_MATN_RE`, or treat ZWNJ as whitespace in this context. Not urgent.

---

### N5. No Schema Version in JSONL Output

**Severity:** 🟢 LOW — latent risk

JSONL records have no version field. If the schema changes (as it just did with `footnote_preamble`), there's no way to distinguish old-format files from new-format files without re-running normalization.

**Fix:** Add `"schema_version": "1.1"` to each JSONL record. Bump on schema changes. Stage 2 can check this field and reject incompatible versions.

---

### N6. No Total Character Counts in Report

**Severity:** 🟢 LOW — missing sanity check

The report has page/footnote counts but no character counts. Adding `total_matn_chars` and `total_footnote_chars` provides:
- A content-volume sanity check (re-running should produce identical counts)
- Visibility into how much content each book contains
- A quick way to spot data loss (character count dropped? investigate)

**Corpus baseline:** 167.4M matn chars + 16.5M footnote chars + 16.7M preamble chars = 200.6M total.

---

### N7. Corpus Smoke Tests Still Use `errors="ignore"`

**Severity:** 🟢 LOW — test gap

Lines 1124, 1134 of `test_normalization.py` use `encoding="utf-8", errors="ignore"` instead of `read_html_file()`. This means the tests could pass on files that would fail in production (where strict UTF-8 is now enforced).

**Fix:** Replace `open(f, encoding="utf-8", errors="ignore")` with `read_html_file(str(f))` in all corpus smoke tests.

---

## DESIGN RECOMMENDATIONS (Non-Blocking)

### D1. Field Naming Inconsistency: `has_tables` vs `has_table`

The dataclass field is `has_tables` (plural) but the JSONL output field is `has_table` (singular). This works correctly but is a landmine for anyone reading the code. The test `test_no_has_tables_field` catches this, but a comment in `page_to_jsonl_record()` explaining the intentional rename would help.

### D2. Gold Samples Still Only Cover Jawahir

All 9 gold validation tests use جواهر البلاغة, which has:
- No duplicate pages
- No bare-number footnotes
- No tables
- No image-only pages
- No ZWNJ headings in the validated range

Creating 3-5 additional gold samples from books that exercise these features would dramatically increase confidence.

### D3. `discover_volume_files()` Only Matches `.htm`

The function checks `fname.lower().endswith(".htm")`. Files with `.html` extension would be silently skipped. Corpus audit confirms zero `.html` files currently exist, but this is fragile.

### D4. `raw_matn_html` Contains Outer `<div class='PageText'>` Tag

The `raw_matn_html` stored for debugging includes the outer PageText div wrapper and excludes the closing `</div>` (which ends up in `raw_fn_html`). This is technically incorrect but doesn't affect functionality since raw fields are only used for debugging and re-normalization tests.

### D5. 88 Pages Have `//` Verse Separators Not Detected by `has_verse`

A small number of pages use `//` as a hemistich separator instead of `…`. These are not detected by `detect_verse()`. Adding `//` detection would catch these, but the false positive risk (URLs, comments) makes it tricky. Best left to Stage 2 which can use full context.

---

## VERIFIED SOLID (No Changes Needed)

Everything from Round 1 that was verified solid REMAINS solid:

- **Tag stripping:** Zero residual HTML in 167K pages ✅
- **Footnote layer separation:** 100% reliable `<hr width='95'>` split ✅
- **Page number extraction:** Zero `page_number_int==0`, zero Arabic-digit refs ✅
- **Source text fidelity:** Diacritics, tatweel, ZWNJ, asterisks all byte-identical ✅
- **`seq_index`:** Unique, monotonic, continuous across volumes ✅
- **Determinism:** Identical output on repeated runs ✅
- **UTF-8 safety:** All 788 files clean, strict mode with fallback ✅
- **Performance:** 167K pages in ~26 seconds ✅
- **`footnote_ref_numbers` dedup:** Zero duplicates across corpus ✅
- **FN_REF_IN_MATN_RE accuracy:** 1 false negative in 167K pages (ZWNJ edge case) ✅
- **Footnote monotonic merge:** 20 pages affected, all correct (sub-points within footnotes) ✅
- **Empty non-image pages:** 4 pages, all correctly warned ✅
- **Bare angle brackets:** 2 pages with `<`, 8 with `>` — all decoded entities in author text, not HTML artifacts ✅

---

## Fix Priority

| # | Issue | Severity | Effort | Impact |
|---|-------|----------|--------|--------|
| N1 | Bare-number footnotes misclassified as preamble | 🔴 CRITICAL | Medium | 24,775 pages with wrong classification |
| N2 | `detect_verse` missing 667 "etc." variants | 🟡 IMPORTANT | Trivial | False positives |
| N3 | No warning for duplicate page numbers | 🟡 IMPORTANT | Small | Stage 2 safety |
| N5 | No schema version in JSONL | 🟢 LOW | Trivial | Future-proofing |
| N6 | No character counts in report | 🟢 LOW | Trivial | Sanity check |
| N7 | Smoke tests use errors="ignore" | 🟢 LOW | Trivial | Test accuracy |

**Bottom line:** N1 is the only true blocker. It doesn't lose data (content IS captured in `footnote_preamble`), but Stage 2 would be building on a foundation where 25K pages have their footnote section misclassified. Adding `footnote_section_format` gives Stage 2 the information it needs to handle each page correctly.
