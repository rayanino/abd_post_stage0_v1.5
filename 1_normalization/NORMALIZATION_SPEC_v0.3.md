# ABD Normalization Specification v0.3

> **SUPERSEDED — use `NORMALIZATION_SPEC_v0.5.md` instead.** This version is retained for history only.

**Status:** Superseded by v0.5
**Date:** 2026-02-26  
**Scope:** Shamela desktop HTML exports → structured JSONL (per-page records with separated layers)  
**Supersedes:** v0.3  
**Changes from v0.3:** Critical fixes — `footnote_preamble` field captures text before first `(N)` marker (§3, §4.5), asterisks preserved as source data instead of stripped (§4.8, Rule V1), `pages_with_fn_preamble` and `pages_with_zwnj_heading` report metrics (§5), prose `… إلخ` excluded from verse detection (§4.8, Rule V2)  
**Changes from v0.2:** Audit-driven fixes — `seq_index` unique key (§3, §4.2), tightened verse detection (§4.8), table cell separator corrected (§4.10), ZWNJ heading detection (§4.12), `footnote_ref_numbers` deduplication semantic (§4.6), `starts_with_zwnj_heading` output field (§3)  
**Changes from v0.1:** Multi-volume support (§2.2, §3, §4.2), table extraction (§4.10), image-only page detection (§4.11), corpus-wide assumption validation (§6)

---

## 1. Purpose

This document defines the transformation rules for converting a raw Shamela HTML book export into a structured, machine-readable format suitable for downstream processing (atomization, excerpting).

The normalization step is the first stage of the ABD extraction pipeline (CP0 in the app spec). It is **fully deterministic** — given the same HTML input, it must produce identical output. No LLM is involved.

---

## 2. Input

### 2.1 Single-volume books

A single HTML file exported from [المكتبة الشاملة (Shamela)](https://shamela.ws/) desktop application. The filename is the Arabic book title with a `.htm` extension.

### 2.2 Multi-volume books

A directory containing numbered HTML files: `001.htm`, `002.htm`, ..., `NNN.htm`. Each file represents one volume (جزء) of the book. The directory name is the Arabic book title.

The normalizer processes each volume file independently, tagging output records with the volume number derived from the filename. The volume number is the integer value of the filename stem (e.g., `001.htm` → volume 1, `014.htm` → volume 14).

**Pagination regimes** (the normalizer does not need to distinguish these — it simply records the volume and page number as-is):

- **Continuous pagination:** Page numbers carry across volumes without resetting. Page numbers are globally unique within the book. (~29% of multi-volume books in the corpus.)
- **Restarted pagination:** Page numbers reset at the start of each volume. The same page number may appear in multiple volumes. (~71% of multi-volume books in the corpus.)

In both cases, the compound key `(volume, page_number_int)` is **not** guaranteed unique — 29.8% of books have duplicate page numbers. Use `seq_index` (§4.2, Rule VOL5) as the authoritative unique page reference.

**Observed HTML structure (Shamela desktop export format):**

```
<html lang='ar' dir='rtl'>
  <body>
    <div class='Main'>
      <div class='PageText'>                    ← one per printed page
        <div class='PageHead'>                  ← running header
          <span class='PartName'>TITLE</span>
          <span class='PageNumber'>(ص: N)</span>
          <hr/>
        </div>
        MATN CONTENT                            ← author's text
        </p>                                    ← paragraph breaks (note: orphaned </p>)
        <font color=#be0000>N.</font>           ← numbered list markers
        VERSE LINE                              ← poetry
        <hr width='95' align='right'>           ← footnote separator
        <div class='footnote'>                  ← footnote content
          (1) TEXT                               ← footnotes numbered inline
          <font color=#be0000>(2)</font> TEXT
        </div>
      </div>
      ... next page ...
    </div>
  </body>
</html>
```

**Key structural markers:**

| Marker | Purpose | Corpus prevalence |
|--------|---------|-------------------|
| `<div class='PageText'>` | Page wrapper | Every file (189,676 pages) |
| `<div class='PageHead'>` | Running header (title + page num) | Every file |
| `<span class='PageNumber'>` | Page number `(ص: N)` | Every content page |
| `<hr width='95'>` | Footnote separator | 6,776 instances across corpus |
| `<div class='footnote'>` | Footnote content wrapper | Paired 1:1 with footnote hr |
| `<font color=#be0000>` | Decorative numbering (red) | Only font color in corpus |
| `</p>` | Paragraph/line breaks | Orphaned closing tags |
| `<table dir=rtl>` | Content tables (rare) | 206 tags in 5 files (3 books) |
| `<img src='data:image/...'>` | Embedded page scan (rare) | 7 tags in 5 files (3 books) |
| `<span class='title'>` | Metadata page labels | Title pages only (skipped) |
| `<span data-type='title'>` | Section heading (rare) | 1 book only |

---

## 3. Output

A JSONL file with one record per printed page:

```json
{
  "record_type": "normalized_page",
  "book_id": "jawahir",
  "seq_index": 1,
  "volume": 1,
  "page_number_arabic": "٢٠",
  "page_number_int": 20,
  "content_type": "text",
  "matn_text": "فصاحة الكلمة\n1. خلوصها من تنافر الحروف...",
  "footnotes": [
    {"number": 1, "text": "ففصاحة الكلمة تكونها من حروف..."},
    {"number": 2, "text": "«الغدائر» الضفائر..."}
  ],
  "footnote_ref_numbers": [1, 2],
  "footnote_preamble": "",
  "has_verse": true,
  "has_table": false,
  "starts_with_zwnj_heading": false,
  "warnings": []
}
```

**Fields added/changed in v0.4:**

| Field | Type | Description |
|-------|------|-------------|
| `footnote_preamble` | string | Text appearing before the first `(N)` marker in the footnote section, or the entire footnote text when no numbered markers exist. Empty string when absent. Contains bibliographic references, grammatical analysis, editorial commentary. See §4.5. |

**Fields added/changed in v0.3:**

| Field | Type | Description |
|-------|------|-------------|
| `seq_index` | int | Zero-based document-order index, monotonically increasing, globally unique within a book. Assigned during normalization across all volumes. Provides an unambiguous page reference regardless of page-number collisions. |
| `starts_with_zwnj_heading` | bool | `true` when the matn text begins with `\u200c\u200c` (double ZWNJ), which marks section headings in Shamela exports. See §4.12. |

**Fields added in v0.2:**

| Field | Type | Description |
|-------|------|-------------|
| `volume` | int | Volume number. Always 1 for single-volume books. Derived from filename for multi-volume books. |
| `content_type` | string | `"text"` for normal pages, `"image_only"` for pages whose sole content is an embedded image. |
| `has_table` | bool | `true` when the page contains one or more `<table>` elements. |

**Unique key:** The compound key `(book_id, volume, page_number_int)` is **not** guaranteed unique — 29.8% of books have duplicate page numbers from editorial pagination errors, appendices, or مقدمة sections reusing body numbering. The field `seq_index` is the authoritative unique identifier within a book. Consumers should use `seq_index` as the primary page reference.

Plus a JSON report file with book-level statistics (unchanged from v0.1, with added volume-level breakdown).

---

## 4. Transformation Rules

### 4.1 Forbidden Transformations (source fidelity)

These transformations are **NEVER** applied. The output must contain the author's text **exactly** as it appears in the HTML source (after tag stripping):

- **No spelling correction** (even for obvious typos)
- **No diacritic normalization** (preserve tashkeel exactly as encoded)
- **No Unicode normalization** (preserve NFC/NFD as-is)
- **No reordering** of content within a page
- **No editorial insertions** (no "[sic]", no completion of truncated words)
- **No punctuation changes** (preserve original spacing around marks)

### 4.2 Volume Detection

**Rule VOL1:** If the input path is a single `.htm` file, set `volume = 1` for all output records.

**Rule VOL2:** If the input path is a directory, discover all `.htm` files whose filename stems are numeric (e.g., `001.htm`, `002.htm`). Process each file independently. Set `volume` to the integer value of the filename stem.

**Rule VOL3:** Non-numeric `.htm` files in a multi-volume directory (if any) are skipped with a warning.

**Rule VOL4:** Volume files are processed in numeric order. This ensures output records are ordered by `(volume, page_number_int)`.

**Rule VOL5:** Each emitted page receives a `seq_index` — a zero-based, monotonically increasing integer assigned in document order. For multi-volume books, `seq_index` is continuous across volumes (volume 2's first page continues from volume 1's last). This field is the authoritative unique page identifier within a book.

### 4.3 Page Structure Extraction

**Rule P1:** Split the HTML into page blocks at `<div class='PageText'>` boundaries. Each block runs from one `<div class='PageText'>` to the next.

**Rule P2:** Extract the page number from `<span class='PageNumber'>(ص: N)</span>` where N uses Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩). Pages without a page number are skipped (these are metadata/title pages).

**Rule P3:** Pages are emitted in document order (the order they appear in the HTML), within each volume.

### 4.4 Running Header Removal

**Rule H1:** Remove the entire `<div class='PageHead'>...</div>` block. This contains the book title (repeated on every page) and the page number — both are metadata, not content.

**Rationale:** The running header is a print layout artifact. The book title is invariant; the page number is captured in `page_number_arabic`/`page_number_int`.

### 4.5 Layer Separation (Matn / Footnotes)

**Rule L1:** Within each page block (after header removal), split at the first `<hr width='95'>` horizontal rule. Everything before is **matn** (متن); everything after is **footnotes** (حواشي).

**Rule L2:** If no `<hr width='95'>` is found, the entire page content is matn and footnotes is empty.

**Rule L3:** Parse footnotes into individual entries by splitting at `(N)` boundaries at the start of a line or start of text, where N is a digit sequence. The optional separator `ـ` or `-` or `–` after `(N)` is stripped. The footnote number prefix is stripped from the text.

**Rule L4:** Two footnote formats exist in Shamela exports (discovered empirically):
- `(N) ـ text` — with dash separator (minority: ~6% in جواهر)
- `(N) text` — without dash (majority: ~94% in جواهر)

Both must be handled.

### 4.6 Footnote Reference Stripping

**Rule F1:** In the matn text, footnote reference markers `(N)` are stripped **only when** a footnote numbered N exists on the same page. This prevents stripping exercise numbers, Quran verse references, or other parenthesized numbers.

**Rule F2:** The regex for footnote reference markers is: `\s*\((\d+)\)\s*` followed by a punctuation mark, whitespace, or end of text. This matches ` (1) .` and `(2)` at line end, but not `(وأخي هارون)` (Arabic text in parentheses).

**Rule F3:** After stripping, double spaces are collapsed to single spaces.

**Rule F4:** The `footnote_ref_numbers` field is a **unique sorted list** (set semantic). When footnote `(1)` is referenced multiple times on the same page, it appears once in the list. The occurrence count is not recorded as it is not useful downstream.

**Rule F5 (new in v0.4):** The `footnote_preamble` field captures any text in the footnote section that appears **before** the first `(N)` marker. When the footnote section contains no `(N)` markers at all, the entire footnote text is stored as preamble. This text commonly contains: bibliographic references (شواهد المغني 2/ 923), grammatical analysis (اللُّغة: الغواني: جمع الغانية), editorial commentary, or section-level notes. A `FN_PREAMBLE` warning is emitted when preamble is non-empty.

### 4.7 HTML Tag Handling

**Rule T1:** `<br>` and `</p>` tags are replaced with newline characters.

**Rule T2:** `<font color=...>TEXT</font>` tags are unwrapped — the text content is preserved, the tag is removed. These are purely decorative (red numbering).

**Rule T3:** All other HTML tags are removed (content between `<` and `>` is stripped), **except** `<table>`, `<tr>`, `<th>`, `<td>` which are handled by Rule TAB1–TAB3.

**Rule T4:** HTML entities (`&amp;`, `&nbsp;`, etc.) are decoded to their Unicode equivalents.

### 4.8 Verse/Poetry Detection

**Rule V1:** Asterisks in the source text (`* text *`, `*****heading*****`, `* *` separators) are **preserved as-is** in the output. They are source data, not Shamela artifacts. Stage 2 handles verse formatting with full structural context. The `clean_verse_markers()` function remains available for downstream use but is **not** called during normalization.

**Rule V2:** The `has_verse` flag is set to `true` when the page contains either:
- Asterisk-wrapped patterns matching `* text *` (star markers), OR
- A **balanced hemistich separator**: the character `…` (U+2026 HORIZONTAL ELLIPSIS) appearing on a line with ≥ 5 characters of text on each side (i.e., `left_text … right_text` where both `left_text.strip()` and `right_text.strip()` are at least 5 characters long).

A lone `…` used for prose truncation, omission, or continuation does **not** trigger `has_verse`. Additionally, lines where the right side of `…` starts with `إلخ` (etcetera) are excluded as prose continuation markers. This distinction eliminates the 13.6% false positive rate that would result from treating all `…` occurrences as verse, and the 0.6% residual false positives from `… إلخ` prose patterns.

**Rule V3:** Verse text is **not** reformatted. Hemistich separators, line breaks within verses, and original formatting are preserved.

### 4.9 Whitespace Normalization

**Rule W1:** `\r\n` and `\r` are normalized to `\n`.

**Rule W2:** Non-breaking spaces (U+00A0) are normalized to regular spaces.

**Rule W3:** Multiple consecutive spaces within a line are collapsed to a single space.

**Rule W4:** Lines are trimmed (leading/trailing whitespace removed).

**Rule W5:** Three or more consecutive blank lines are collapsed to one blank line.

### 4.10 Table Extraction (new in v0.2)

**Rule TAB1:** When a `<table>` element is encountered in the matn, extract cell text in reading order. For `dir=rtl` tables (all observed cases), reading order is: top row to bottom row, right cell to left cell within each row.

**Rule TAB2:** Row content is joined with ` | ` (pipe with spaces) between cells. Rows are joined with `\n` (newline). A blank line is inserted before and after the table block to separate it from surrounding text.

**Rule TAB3:** Set `has_table = true` for the page record. Tables in footnote sections follow the same extraction rules.

**Rationale:** Tables are extremely rare (206 total `<table>` tags across 189,676 pages, concentrated in 3 books). All observed tables are simple comparison/conjugation charts with `<th>`/`<td>` cells and no nested tables, colspan, or rowspan. A simple cell-text extraction is sufficient. The pipe-separated format preserves columnar structure for downstream consumption while remaining human-readable.

### 4.11 Image-Only Page Detection (new in v0.2)

**Rule IMG1:** When a page's only content (after header removal) is an `<img>` tag, set `content_type = "image_only"`, set `matn_text = ""` and `footnotes = []`, and add a warning: `"image_only_page"`.

**Rule IMG2:** When a page contains both text and an `<img>` tag, set `content_type = "text"`, extract text normally, strip the `<img>` tag, and add a warning: `"page_contains_image"`.

**Rationale:** Embedded images are base64-encoded JPEG page scans (`<img src='data:image/jpg;base64,...'>`). They are extremely rare (7 total across 189,676 pages, in 3 books). The image data is not extractable as text. Image-only pages are flagged so downstream steps can skip them. Mixed pages (text + image) are extracted normally with the image data discarded.

### 4.12 ZWNJ Section Heading Detection (new in v0.3)

**Rule ZWNJ1:** When the matn text (after all cleaning) starts with `\u200c\u200c` (double ZERO WIDTH NON-JOINER, U+200C), set `starts_with_zwnj_heading = true`.

**Rule ZWNJ2:** The ZWNJ characters are **preserved** in the matn text (they are source data, not presentation artifacts). The boolean flag exposes the pattern as structured metadata so Stage 2 can use it as a high-confidence structural signal without re-scanning text.

**Rationale:** 15,814 pages (9.5% of corpus) start with double ZWNJ. These consistently mark section headings in Shamela exports: المقدمة, الفصل الأول, الكتاب الثاني, etc. This is an extremely valuable signal for Structure Discovery (Stage 2).

### 4.13 Cross-Reference Validation

**Rule X1:** For each page, cross-reference footnote reference numbers found in matn against footnote entries parsed from the footnote layer. Report mismatches as warnings:
- **Orphan ref:** A `(N)` was stripped from matn but no footnote N exists (should not happen with Rule F1)
- **Orphan footnote:** A footnote N exists but no `(N)` was found in matn (common: the ref may be on the previous page)

---

## 5. Scope and Limitations

### 5.1 What normalization does NOT do

- **Atomization:** Does not split text into sentence-level atoms. That's the next pipeline step (CP2).
- **Layer content classification:** Does not determine whether a footnote is scholarly commentary vs apparatus. That's an excerpting decision.
- **Heading detection:** Does not identify section headings within the matn text. That's an atomization decision.
- **Cross-page continuity:** Does not join text that flows across page boundaries. Each page is an independent record.
- **Character-level normalization:** Does not normalize Arabic Unicode forms (e.g., different representations of shadda+kasra). Preserves bytes as-is.
- **Volume sequencing logic:** Does not determine whether a book uses continuous or restarted pagination. It records volume + page number; the consumer decides how to interpret them.

### 5.2 Known edge cases

1. **Pages without page markers** are skipped (typically metadata/title pages at the book's start). These are reported in `pages_skipped`.
2. **Footnotes spanning pages:** When a footnote reference `(N)` is on one page and the footnote text is on the next page's footnote section, this manifests as an orphan footnote. The warning is informational, not an error.
3. **Exercise numbering:** Exercise items like `(1)`, `(2)` in تطبيق sections look syntactically identical to footnote references. Rule F1 (conditional stripping) prevents false removal.
4. **Quran parenthetical markers:** Text like `(وأخي هارون هو أفصح منِّي لساناً)` uses parentheses for Quranic quotation. Rule F2 (digits-only regex) prevents stripping these.
5. **Image-only pages:** Rare pages (~7 across 189,676) that are scanned page images with no extractable text. Flagged with `content_type: "image_only"`.
6. **Content tables:** Rare comparison/conjugation tables (~206 across 189,676 pages) in 3 books. Extracted as pipe-separated text.
7. **`<span data-type='title'>` headings:** Found in exactly 1 book (التبيان في قواعد النحو). Stripped like all other HTML tags; text content preserved. No special handling needed.

---

## 6. Shamela Format Assumptions

These assumptions were validated against **1,046 files containing 189,676 pages** across all three target sciences (لغة, بلاغة, نحو/صرف). See `CORPUS_SURVEY_REPORT.md` for full methodology and data.

| # | Assumption | Validation result |
|---|---|---|
| A1 | Every content page has a `PageText` div wrapper. | ✅ Holds universally (1,046/1,046 files) |
| A2 | Running headers use `PageHead > PartName + PageNumber` structure. | ✅ Holds universally |
| A3 | Page numbers use Arabic-Indic digits in `(ص: N)` format. | ✅ Holds universally (189,676 pages) |
| A4 | The footnote separator is `<hr width='95'>`. | ✅ Holds universally (6,776 separators) |
| A5 | Footnote content is inside `<div class='footnote'>`. | ✅ Holds universally |
| A6 | The only `<font>` usage is `color=#be0000` for decorative numbering. | ✅ Holds universally |
| A7 | No tables, images, or embedded media exist in the export. | ⚠️ Broken in 3 books (5 files). See §4.10–§4.11. |
| A8 | No Quran/hadith-specific CSS classes exist. | ✅ Holds universally |

**Corpus clean rate for A7:** 99.5% (1,041/1,046 files have zero tables/images).

The normalizer handles A7 violations gracefully via Rules TAB1–TAB3 and IMG1–IMG2. All other assumptions can be treated as invariants.

---

## 7. Reference Implementation

```
tools/normalize_shamela.py
```

Usage (single-volume):
```bash
python tools/normalize_shamela.py \
  --html path/to/shamela_export.htm \
  --out-jsonl normalized_pages.jsonl \
  --out-report normalization_report.json \
  --book-id jawahir
```

Usage (multi-volume):
```bash
python tools/normalize_shamela.py \
  --html-dir path/to/book_directory/ \
  --out-jsonl normalized_pages.jsonl \
  --out-report normalization_report.json \
  --book-id kitab_sibawayh
```

Options:
- `--page-start N` / `--page-end N` — process a page range only (within each volume)
- `--include-raw-html` — include raw HTML in output (for debugging)

---

## 8. Gold Samples

See `0_normalization/gold_samples/`:
- `GOLD_SAMPLES.md` — annotated input→output comparisons for 6 representative page types
- `jawahir_normalized.jsonl` — full-book normalized output (308 pages)
- `jawahir_normalized_full.jsonl` — pages 19–40 with raw HTML included
- `jawahir_normalization_report.json` — book-level statistics

---

## 9. Validation Against Gold Standard Passages

The normalizer's output was compared against the gold canonical texts from Passages 1–3 (ص ١٩–٤٠). Expected differences:

| Difference type | Count | Explanation |
|----------------|-------|-------------|
| Parenthetical content preserved | 1 | `(في معرفة...)` — gold stripped during atomization |
| Diacritic Unicode form | 2 | Different codepoint sequences for same rendering |
| Cross-page line break | 3 | Normalizer outputs per-page; gold joins across pages |
| **Unexpected differences** | **0** | — |

The normalizer correctly preserves all source text while stripping only Shamela presentation artifacts.

---

## 10. Related Documents

| Document | Relationship |
|---|---|
| `CORPUS_SURVEY_REPORT.md` | Detailed findings from scanning 1,046 files / 189,676 pages |
| `normalization_contract_v0.2.md` | Input/output contract for integration with the pipeline |
| `APP_SPEC.md` | Pipeline architecture (CP0 = normalization) |
