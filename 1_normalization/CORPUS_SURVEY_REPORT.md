# Shamela HTML Corpus Structural Survey Report

**Date:** 2025-02-24  
**Scope:** Complete Arabic-language book corpus from Shamela Library exports  
**Purpose:** Validate normalizer assumptions across the full target corpus before builder handoff

---

## 1. Corpus Summary

| Metric | Value |
|---|---|
| Total files scanned | 1,046 |
| Total pages | 189,676 |
| Parse errors | 0 |
| Sciences covered | لغة (Language), بلاغة (Rhetoric), نحو (Grammar), صرف (Morphology) |

### Breakdown by science

| Corpus | Files | Pages |
|---|---|---|
| كتب اللغة | 79 | 18,981 |
| كتب البلاغة | 78 | 20,218 |
| كتب النحو والصرف (6 batches) | 889 | 150,477 |
| **Total** | **1,046** | **189,676** |

---

## 2. Assumption Validation

The normalizer (NORMALIZATION_SPEC_v0.1.md) declares 8 structural assumptions about Shamela HTML exports. Each was tested against every file in the corpus.

| # | Assumption | Result | Notes |
|---|---|---|---|
| A1 | Every page lives in a `<div class='PageText'>` | ✅ Holds universally | 1,046/1,046 files |
| A2 | Headers use `PageHead`, `PartName`, `PageNumber` | ✅ Holds universally | 1,046/1,046 files |
| A3 | Page numbers are Eastern Arabic-Indic in `(ص: N)` | ✅ Holds universally | 189,676 pages checked |
| A4 | Footnote separator is `<hr width='95' align='right'>` | ✅ Holds universally | 6,776 footnote separators found, all matching |
| A5 | Footnotes are in `<div class='footnote'>` | ✅ Holds universally | All footnote divs paired with hr separators |
| A6 | Only decorative font color is `#be0000` (red) | ✅ Holds universally | Zero non-red font colors in corpus |
| A7 | No tables, images, or embedded media | ⚠️ Broken in 3 books | 5 files affected out of 1,046 (99.5% clean) |
| A8 | No Quran/Hadith-specific CSS classes | ✅ Holds universally | Zero quran/hadith classes found |

**Conclusion:** 7/8 assumptions hold with zero exceptions across 189,676 pages. A7 fails in exactly 3 books (detailed in §4).

---

## 3. Universal Structural Patterns

These patterns appear in every file and are handled correctly by the existing normalizer.

### 3.1 HR (horizontal rule) variants

| Pattern | Count | Purpose |
|---|---|---|
| `<hr />` | ~18,989 (1 per page) | Header/body separator within each page |
| `<hr width='95' align='right'>` | 6,776 | Footnote separator (our normalizer target) |
| `<hr>` | ~79 (1 per file) | Title/metadata page separator |

The normalizer correctly targets only `width='95'` for footnote splitting. The other two HR types are removed during tag stripping. No action needed.

### 3.2 The `title` CSS class

Found in every file, but only on title/metadata pages (the first page of each book/volume that shows book name, author, section). These pages lack a `(ص: N)` page number, so the normalizer already skips them. No action needed.

### 3.3 Page structure mismatch pattern

Nearly every file shows `PageText count = PageHead count + 1 = PageNumber count + 1` (occasionally +2). This is because title/metadata pages have a `PageText` div but no `PageHead`/`PageNumber` inside them. The normalizer already handles this: pages without `(ص: N)` are skipped. No action needed.

### 3.4 Zero presence of

The following were checked for and found to be completely absent across the entire corpus:

- Bold/italic/underline tags (`<b>`, `<strong>`, `<i>`, `<em>`, `<u>`)
- Hyperlinks (`<a href>`)
- Embedded media (`<iframe>`, `<object>`, `<embed>`)
- Non-red font colors
- Quran/Hadith CSS classes
- `<p>` tags (in the body; Shamela uses `</p>` as a line break, not paired `<p>...</p>`)

---

## 4. A7 Edge Cases: Tables and Images

### 4.1 التبيان في قواعد النحو وتقويم اللسان

This is a modern Arabic grammar textbook with the richest structural variation in the corpus.

| Feature | Count | Location |
|---|---|---|
| `<table dir=rtl>` | 186 | All in matn (zero in footnotes) |
| `<img>` (base64 JPEG, full-width) | 3 | Pages 14, 189, ~190 — full page scans |
| `<span data-type='title'>` | 90 | Section headings within pages |

The tables are genuine content: comparison charts (noun vs verb), conjugation paradigms, declension summaries. Each table has 2–14 rows and uses `<th>` for headers and `<td>` for data. All have `dir=rtl`.

The images are base64-encoded JPEG page scans embedded inline (`<img src='data:image/jpg;base64,...' style='width: 100%;height: auto'>`). These pages contain no extractable text — the entire page content is a photograph of the printed book.

The `<span data-type='title'>` markers are non-standard section headings not seen elsewhere in the corpus. They wrap heading text with a zero-width non-joiner (`&#8204;`) prefix.

### 4.2 شرح الفارضي (4 volumes)

Each volume file (001.htm–004.htm) contains exactly 1 embedded page-scan image (same base64 JPEG pattern as above). No tables. These are likely title pages or colophon pages that were scanned rather than typeset.

### 4.3 ضياء السالك إلى أوضح المسالك (4 volumes)

Volumes 003.htm and 004.htm each contain 5 `<table>` tags. Volume 001.htm contains 1 embedded image. The tables are likely conjugation/declension charts (same pattern as التبيان but much smaller scale).

### 4.4 Normalizer impact

**Tables:** The normalizer should extract table cell text in reading order (right-to-left, top-to-bottom for `dir=rtl` tables). Cell content is separated by tabs or newlines to preserve tabular structure. Tables are rare enough (206 total `<table>` tags out of 189,676 pages) that a simple extraction is sufficient — we do not need sophisticated table-to-text rendering.

**Image-only pages:** The normalizer should detect pages whose only content is a `<img>` tag, emit the page record with `"content_type": "image_only"` and empty `matn`/`footnotes` fields, and log a warning. Downstream pipeline steps can skip these pages. Total affected: ~7 pages out of 189,676.

**`data-type='title'` spans:** These should be stripped like all other HTML tags. The text content is preserved. Only affects 1 book.

---

## 5. Multi-Volume Books

### 5.1 Prevalence

| Category | Books | Files |
|---|---|---|
| Single-volume (one .htm per book) | hundreds | — |
| Multi-volume (numbered .htm files in a directory) | 104 | 600+ |

### 5.2 Pagination regimes

Multi-volume books fall into two distinct patterns:

**Continuous pagination (30 books):** Page numbers carry across volumes without resetting. Volume 1 ends at page N, volume 2 starts at page N+k. Page numbers are globally unique within the book. Example: بغية الإيضاح has 4 volumes with pages 3→219, 221→376, 379→567, 571→720.

**Restarted pagination (74 books):** Page numbers reset at the start of each volume. Every volume starts from page 1–7. Page numbers are NOT unique — volume 1 page 50 and volume 2 page 50 are different content. Example: معجم تيمور الكبير has 5 volumes all starting from page 1.

### 5.3 Extreme cases

- شرح ألفية ابن مالك (one variant): 138 volumes, each 4–39 pages, all starting from page 1. Likely a lecture series.
- تمهيد القواعد: 11 volumes, continuous pagination spanning pages 4→5,696.
- الإعراب المفصل لكتاب الله المرتل: 12 volumes, each ~450 pages, all starting from page 5. Over 5,500 pages total with completely overlapping page ranges.

### 5.4 Volume identification

The Shamela export encodes volumes as numbered .htm files within a directory: `001.htm`, `002.htm`, etc. The filename number directly corresponds to the volume number. Single-volume books are exported as a single .htm file with the book title as filename (no number prefix).

Some edge cases in volume numbering:
- أبو تراب اللغوي uses `114.htm` and `115.htm` (sections from a larger compilation)
- Books with high-numbered filenames like `039.htm`/`040.htm` may be extracted sections

### 5.5 Design decision: Option B

The pipeline adopts a **separate volume field** approach:

- Each normalized JSONL record includes `"volume": N` (integer, derived from filename)
- Single-volume books always get `"volume": 1`
- The passage config gains an optional `volume_hint` field
- CP1 filters by volume first (when volume_hint is present), then slices by page number
- For continuous-pagination books, volume_hint is technically redundant but recommended for explicitness

---

## 6. Duplicate Detection

The survey revealed some books appear to be duplicated across corpus batches (identical directory names appearing in multiple nahw/sarf parts). These are likely the same book included in overlapping zip archives. The normalizer is idempotent, so processing the same book twice produces identical output. The builder should deduplicate by book ID at the config level, not at the normalizer level.

---

## 7. Methodology

**Tool:** `survey_shamela.py` — a custom Python script that scans directories of .htm files and tests 30+ structural patterns via regex, aggregating results into JSON reports.

**Patterns tested:** PageText/PageHead/PageNumber structure, CSS classes, font colors, HR variants, tables, images, anchors, bold/italic/underline, iframes/objects/embeds, charset encoding, lang/dir attributes, paragraph tags, line breaks, volume markers, footnote div nesting, Quran/Hadith classes.

**Raw data:** JSON survey reports are available per-corpus in the `corpus/` directory: `lugha_survey.json`, `balagha_survey.json`, `nahw_sarf_{1-6}_survey.json`.
