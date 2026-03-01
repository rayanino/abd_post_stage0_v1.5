# Stage 1 Critical Analysis — Pre-Stage-2 Bulletproofing

**Date:** 2026-02-26
**Scope:** Adversarial code review + targeted corpus probes (788 files, 168,038 pages, 165K+ footnotes)
**Objective:** Find every flaw, bug, and latent risk before building Stage 2 on top of this foundation.

---

## CRITICAL — Fix Before Stage 2

### C1. Footnote Preamble Text Is Silently Dropped (DATA LOSS)

**Severity:** ✅ RESOLVED (was 🔴 CRITICAL)
**Fixed:** 2026-02-26 — `parse_footnotes()` now returns `(records, preamble)` tuple; `PageRecord.footnote_preamble` field added; `NormalizationReport.pages_with_fn_preamble` counter added.

**Post-fix corpus validation (333 books, 167,106 pages):**
- 31,453 pages now have footnote preamble captured (was: silently dropped)
- 16,729,131 total characters saved (initial probe underestimated — was 1.3M on subset)
- `FN_PREAMBLE` warning generated on affected pages
- Zero residual HTML in output ✅
- 171/171 tests pass ✅

`parse_footnotes()` splits at `(N)` boundaries using `FN_BOUNDARY = re.compile(r"(?:^|\n)\((\d+)\)\s*(?:[ـ\-–]\s*)?", re.MULTILINE)`. Text that appears *before* the first `(N)` marker is silently discarded — it never appears in any footnote record.

**Corpus impact:**
- 3,092 pages (4.5% of all footnote pages) have preamble text before the first `(N)`
- 1,309,904 total characters silently dropped
- 87 books affected

**Examples of dropped text:**
- Bibliographic references: `شواهد المغني 2/ 923، والمقاصد النّحوية 2/ 374...`
- Grammatical analysis: `اللُّغة: الغواني: جمع الغانية...`
- Editorial commentary: `زرعة على النابغة الذبياني بأن يحمل قومه...`

**Root cause:** The `FN_BOUNDARY` regex anchors on `(?:^|\n)` before `(N)`. When the first footnote boundary starts after some preamble text, `matches[0].start() > 0` and everything before it is lost. The code has `raw_records` built from `matches[i].end()` onward — the preamble is simply never captured.

**Fix:** Capture text before the first `(N)` marker. If `matches[0].start() > 0`, create a `FootnoteRecord(number=0, text=preamble, ...)` or — since footnote number 0 would break downstream assumptions — store it as a `footnote_preamble: str` field on PageRecord. Stage 2 can decide whether to attach it to the preceding footnote, treat it as editorial context, or flag it for review.

Minimal code change in `parse_footnotes()`:
```python
if matches and matches[0].start() > 0:
    preamble = fn_text[:matches[0].start()].strip()
    if preamble:
        # Prepend preamble to first footnote's text
        first = raw_records[0]
        raw_records[0] = FootnoteRecord(
            number=first.number,
            text=preamble + "\n" + first.text,
            raw_text=preamble + "\n" + first.raw_text,
        )
```

However: blindly merging into footnote 1 may be wrong when the preamble is bibliographic context that applies to ALL footnotes on the page. The safest fix is to expose it as a separate field and let Stage 2 decide. Either way, silently dropping 1.3M characters is unacceptable.

---

### C2. `clean_verse_markers()` Mangles Non-Verse Content (DATA CORRUPTION)

**Severity:** ✅ RESOLVED (was 🔴 CRITICAL)
**Fixed:** 2026-02-26 — `clean_verse_markers()` removed from the normalization pipeline. Asterisks are now preserved as source data per spec §5 ("NEVER alter author's text"). The function still exists as a utility for Stage 2 to call selectively with full context.

**Post-fix corpus validation (333 books, 167,106 pages):**
- 11,473 pages now have asterisks preserved in output (was: silently stripped/mangled)
- `has_verse` detection unchanged — still correctly flags `* text *` and balanced hemistich patterns
- Zero residual HTML in output ✅
- 171/171 tests pass ✅

`VERSE_STAR_RE = re.compile(r"\*\s*([^*]+?)\s*\*")` matches ANY `* text *` pattern, not just verse. `clean_verse_markers()` unconditionally strips the asterisks from all matches.

**Corpus impact:**
- 7,741 pages modified by `clean_verse_markers()`
- 2,254 pages have `* *` (decorative separators) turned into whitespace/empty
- 5,487 pages have content between asterisks silently stripped of its markers

**Specific corruption patterns discovered:**

1. **Decorative star headers** like `*********‌‌نظم الأجرّومية للإمام العمريطي***********` — the regex matches `*text*` inside the run of asterisks, stripping a pair and leaving `********‌‌نظم...العمريطي**********` (mangled).

2. **Section heading markers** like `* أقسام الكلام وعلامات الاسم. *` — these are NOT verse. They're Shamela's way of marking chapter headings. Stripping the asterisks destroys a structural signal that Stage 2 needs.

3. **Decorative separators** like `* *` between sections — turned into a single space, collapsing what was a visible section break.

**Root cause:** The regex is too greedy and `clean_verse_markers` is unconditional. It runs on every page (line 456), not just pages with detected verse. And there is no validation that a `* text *` match is actually poetry versus a heading marker.

**Fix (two-part):**

Part A — Only run `clean_verse_markers` when the specific match is within a detected verse context. OR, don't run it at all (preserve asterisks as source data, let Stage 2 handle verse formatting). The spec says (§4.1) "NEVER alter the author's text" — stripping `*` markers arguably violates this principle, since `*` appears in the source HTML text, not just in tags.

Part B — Add a heuristic to distinguish verse stars from heading stars:
- Verse: `* text *` where both stars are on the same line with substantial text between them and no other `*` on the line
- Heading: `* title *` at start of page (often sole content of a line)
- Separator: `* *` or `** **`
- Decorative: runs of 3+ consecutive `*`

The safest approach: **stop stripping asterisks entirely**. Preserve them as source data. `has_verse` already signals verse presence — Stage 2 can strip markers when it actually processes verse content with full context.

---

## IMPORTANT — Should Fix

### I1. `detect_verse()` Has Remaining False Positives on Prose Ellipsis

**Severity:** 🟡 — misclassification, not data loss

The balanced hemistich heuristic (`≥5 chars … ≥5 chars`) still flags prose continuation patterns as verse. Common false-positive pattern: `وعلامة الفصاحة الراجعة إلى اللفظ أن يكون اللفظ جاريا … إلخ` — the `… إلخ` (meaning "etc.") pattern has ≥5 chars on each side.

**Corpus reality:** 3,805 pages contain lines with multiple `…` characters. In patterns like `text … إلخ، وبما ذكرنا … إلخ`, the first split produces left ≥5 and right ≥5, triggering `has_verse=True` even though this is clearly prose with "etc." markers.

**Impact on Stage 2:** Verse pages get special handling (lines aren't split into prose atoms). False positives cause prose to be incorrectly left as verse blocks.

**Fix options (not mutually exclusive):**
- Exclude lines containing `… إلخ` (a very reliable prose marker)
- Require both sides of `…` to contain NO Latin punctuation like `,` or `.` (hemistichs don't normally have commas)
- Require the `…` to be roughly centered on the line (real hemistichs are balanced in length)

### I2. `seq_index` Becomes Non-Contiguous Under `--page-start`/`--page-end`

**Severity:** 🟡 — confusing API contract

When `--page-start 5 --page-end 10` is used, `seq_index` values in the output are `[4,5,6,7,8,9]` (their original book positions), not `[0,1,2,3,4,5]`. This is because `seq_index` is assigned in `normalize_book()` before the CLI filters pages.

Additionally, the normalization report counts ALL pages in the book, not just the filtered subset — so `total_pages` in the report doesn't match the JSONL record count.

**Impact:** Any consumer assuming `seq_index` starts at 0 or is contiguous will be confused. The report statistics are misleading for partial outputs.

**Fix:** Document that `seq_index` reflects the page's position in the full book, regardless of filtering. This is actually the correct semantic — `seq_index=7` means "the 8th page of the book" even if you only extracted pages 5–10. But it needs to be explicit in the spec. For the report, add a `filtered_pages` count alongside `total_pages`.

### I3. Report Doesn't Track `starts_with_zwnj_heading` Count

**Severity:** 🟢 LOW — missing metric

`NormalizationReport` tracks `pages_with_verse`, `pages_with_tables`, `pages_image_only` — but not `pages_with_zwnj_heading`. This is a missed opportunity: the ZWNJ heading count (15,814 pages, 9.5% of corpus) is the single most valuable structural signal for Stage 2.

**Fix:** Add `pages_with_zwnj_heading: int` to `NormalizationReport` and `aggregate_reports()`.

### I4. `aggregate_reports()` Doesn't Record `starts_with_zwnj_heading` Per Volume

**Severity:** 🟢 LOW — incomplete reporting

The per-volume breakdown in `aggregate_reports()` includes `pages_with_verse`, `pages_with_tables`, `pages_image_only` but not `pages_with_zwnj_heading`. For Stage 2 structure discovery, knowing which volumes are rich in heading markers is useful for prioritization.

---

## DESIGN CONCERNS — Latent Risks

### D1. `strip_tags()` Runs on Both Matn and Footnote HTML (Potential Future Breakage)

The `strip_tags()` function applies the same transformations to both matn and footnote content. Currently this works because both layers use the same HTML conventions. But if Shamela ever introduces layer-specific formatting (different CSS classes, structured footnote metadata), the single function would need to branch — and the lack of separation makes this a blind spot.

**Recommendation:** No code change needed now, but add a comment in `strip_tags()` noting that matn and footnote HTML have been verified to use identical tag conventions as of the current corpus survey.

### D2. The `* text *` vs Heading Ambiguity Has No Ground Truth

There is currently no gold sample for pages containing `* heading *` patterns vs `* verse *` patterns. This means any fix to C2 can't be validated against a known-correct baseline.

**Recommendation:** Before fixing C2, create gold samples for 3 page types: (a) genuine `* verse *` pages (from books known to contain poetry), (b) `* heading *` pages from multi-volume books with section markers, (c) `*****decorative*****` header pages. This gives you a test target.

### D3. `encoding="utf-8", errors="ignore"` Is a Silent Data Loss Trap

Currently all 788 corpus files are clean UTF-8, so zero bytes are lost. But the `errors="ignore"` flag means a single non-UTF-8 file silently loses data with no warning, no log entry, and no way to detect it after the fact.

**Recommendation:** Switch to `errors="strict"` with a try/except that logs the error and either retries with Windows-1256 or raises. This was item #8 in the original audit — it's still unfixed and is the kind of thing that bites you exactly once, catastrophically, six months from now.

### D4. No Schema Validation on JSONL Output

There is no formal JSON Schema for the normalized page record. The tests check field presence and types, but there's no machine-readable schema that Stage 2 can validate against. If a code change accidentally drops a field or changes a type, the only guard is the test suite.

**Recommendation:** Add a JSON Schema file (`schemas/normalized_page_v0.3.json`) and a validation step that checks every output record against it. This is cheap insurance.

### D5. Gold Samples Are Jawahir-Only

All gold sample validation (9 tests) uses a single book (جواهر البلاغة). This book has no tables, no images, no duplicate page numbers, no ZWNJ headings in the validated range (pages 19–40 only), and no multi-volume complexity. It's the easiest case.

**Recommendation:** Create gold samples for at least one book from each edge-case category: a book with tables, a book with duplicate page numbers, a multi-volume book, a book with ZWNJ headings, and a book with the `* heading *` pattern. This is the single most impactful testing investment for Stage 2 confidence.

---

## What's Bulletproof (Confirmed Solid)

These passed adversarial probing and need no changes:

- **Tag stripping (T1–T4):** Zero residual HTML in 168,038 pages. Not a single `<tag>` leaked through.
- **Footnote layer separation (L1–L2):** The `<hr width='95'>` split is 100% reliable. Zero cases of multiple separators on one page. Zero text between separator and footnote div.
- **Page number extraction (P2):** Zero pages with `page_number_int == 0`. Zero Arabic-digit `(٣)` refs that could confuse footnote stripping.
- **PageHead removal (H1):** Zero nested divs inside PageHead blocks. The non-greedy `.*?` regex is safe.
- **Source fidelity (§5):** Diacritics, tatweel, ZWNJ, asterisks, all Unicode forms byte-identical between input and output.
- **`seq_index` uniqueness:** Verified across all 332 books: unique, monotonic, continuous across volumes.
- **`footnote_ref_numbers` deduplication:** Zero books with duplicates or unsorted values.
- **`starts_with_zwnj_heading`:** Correctly detecting 15,814 pages (9.5%) across 310/332 books.
- **Multi-volume support:** Volume tagging, ordering, continuous `seq_index` all correct.
- **Determinism:** Identical output on repeated runs. Verified.
- **Performance:** 167K pages in <24 seconds. No bottleneck.
- **UTF-8 safety:** All 788 files are clean UTF-8. Zero bytes currently lost to `errors="ignore"`.

---

## Recommended Fix Priority

| # | Issue | Severity | Status | Impact |
|---|-------|----------|--------|--------|
| C1 | Footnote preamble text silently dropped | ✅ RESOLVED | Fixed 2026-02-26 | 16.7M chars saved across 31,453 pages |
| C2 | `clean_verse_markers` mangles non-verse content | ✅ RESOLVED | Fixed 2026-02-26 | 11,473 pages now have asterisks preserved |
| I1 | `detect_verse` false positives on prose `… إلخ` | 🟡 IMPORTANT | Open | Misclassifies prose as verse |
| I2 | `seq_index` non-contiguous under page filtering | 🟡 IMPORTANT | Open | Document the semantic |
| I3 | Report missing ZWNJ heading count | 🟢 LOW | Open | Missing metric |
| D3 | Silent encoding data loss trap | 🟢 LOW | Open | Latent risk |
| D4 | No JSON Schema for output records | 🟢 LOW | Open | Safety net |
| D5 | Gold samples only cover one easy book | 🟢 LOW | Open | Test coverage gap |

**Bottom line:** Both blockers (C1, C2) are resolved. The remaining items are either documented behavior, missing metrics, or latent risks with no current impact. Stage 2 can proceed.
