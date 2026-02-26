# Stage 1: Normalization — Specification

**Status:** High maturity — existing tooling and spec validated against 1,046 files / 189,676 pages
**Precision level:** High (deterministic, no LLM involvement)
**Dependencies:** Stage 0 (Intake) must be complete. Requires frozen source HTML.

> **Document relationship:** This file is the **stage-level overview**. The detailed transformation rules (12 subsections covering every normalization step) live in `NORMALIZATION_SPEC_v0.2.md` in this same folder. Read this file first for orientation, then v0.2 for the full technical reference.

---

## 1. Purpose

Convert the frozen Shamela HTML export into a clean, structured, page-aligned JSONL file. This is a **deterministic, lossless** transformation. No content is added, removed, or corrected. Spelling errors are preserved. The output is the canonical text representation used by all downstream stages.

---

## 2. Existing Assets

This stage already has validated tooling and documentation:

| Asset | Location | Status |
|-------|----------|--------|
| `normalize_shamela.py` | `tools/normalize_shamela.py` | 595 lines, validated |
| `NORMALIZATION_SPEC_v0.2.md` | `1_normalization/NORMALIZATION_SPEC_v0.2.md` | Complete |
| `SHAMELA_HTML_REFERENCE.md` | `1_normalization/SHAMELA_HTML_REFERENCE.md` | Complete |
| `CORPUS_SURVEY_REPORT.md` | `1_normalization/CORPUS_SURVEY_REPORT.md` | 1,046 files surveyed |
| Gold output (jawahir) | `1_normalization/gold_samples/` | Validated |

---

## 3. What the normalizer does

1. Parses the Shamela HTML DOM
2. Extracts each `PageText` div as a page
3. Separates main text (matn) from footnotes
4. Strips Shamela-specific markup (decorative spans, navigation elements)
5. Preserves meaningful markup (title spans → heading markers)
6. Outputs one JSON object per page to `pages.jsonl`

---

## 4. Output format

### 4.1 `pages.jsonl`

One JSON object per line, one line per page:

```json
{
  "record_type": "page",
  "book_id": "jawahir",
  "seq_index": 0,
  "volume": 1,
  "page_number_arabic": "٢٣",
  "page_number_int": 23,
  "content_type": "text",
  "matn_text": "الباب الأول: فَعَلَ يَفعُل\nبكسر العين في الماضي وضمها في المضارع...",
  "footnotes": [
    {"number": 1, "text": "هذا تقسيم أبي عمرو بن العلاء...", "raw_text": "(1) هذا تقسيم ..."}
  ],
  "footnote_ref_numbers": [1],
  "footnote_preamble": "",
  "has_verse": false,
  "has_table": false,
  "starts_with_zwnj_heading": false,
  "warnings": []
}
```

**Field notes:**
- `footnote_preamble`: Text appearing before the first `(N)` marker in the footnote
  section. Common in scholarly editions — contains bibliographic references,
  grammatical analysis, or editorial commentary. Empty string when absent.
- `has_verse`: Signals verse presence via `* text *` markers or balanced hemistich
  patterns. Asterisks are **preserved as-is** in `matn_text` (source data, not
  Shamela artifacts). Stage 2 handles verse formatting with full context.
- `starts_with_zwnj_heading`: True when matn begins with double U+200C — a Shamela
  convention marking section headings.

### 4.2 `normalization_report.json`

Statistics: page count, footnote count, preamble count, heading count, warnings, hash.

Includes `pages_with_fn_preamble` — count of pages where footnote preamble text
was captured (text before first numbered footnote marker).

### 4.3 `book_review.md`

Single Markdown file rendering the full book content for human review in VSCode.

---

## 5. Key Rules (from NORMALIZATION_SPEC_v0.2)

- **Zero information loss:** Every character in the source is accounted for in the output (content, metadata, or explicitly discarded structural markup).
- **Source text fidelity:** NEVER alter author's text. Asterisks (`*`), diacritics, tatweel, ZWNJ, and all Unicode content are preserved byte-identical. `clean_verse_markers()` exists as a utility but is NOT called during normalization — Stage 2 handles verse formatting with full book context.
- **No spelling correction:** Errors in the source are preserved exactly.
- **Footnote separation:** Footnotes are extracted into their own field, not mixed with matn. Text before the first `(N)` marker (preamble) is captured in `footnote_preamble`, not silently dropped.
- **Page alignment:** Each output object corresponds exactly to one source `PageText` div.
- **Deterministic:** Same input always produces same output. No randomness, no LLM.

---

## 6. Known Patterns Requiring Attention

From the corpus survey:

| Pattern | Prevalence | Handling |
|---------|-----------|----------|
| Editorial footnotes marked "ن" | شذا العرف | Treated as footnotes; marker preserved |
| Multi-paragraph footnotes | Rare | Concatenated into single footnote entry |
| Quranic citations in brackets | Common | Preserved as-is in matn |
| Poetry/verse blocks | Common | Preserved as-is; asterisks and line breaks maintained. `has_verse` flag set for Stage 2 |
| Empty pages | Occasional | Output with empty matn, flagged in report |
| Pages with only footnotes | Rare | matn is empty, footnotes populated |

---

## 7. Open Questions

1. **New book patterns:** Each new book may introduce normalization edge cases not seen in the corpus survey. The normalizer should flag unexpected HTML patterns rather than silently dropping content.
2. **Multi-volume stitching:** For multi-volume books, pages.jsonl should be a single continuous file with volume boundaries marked. Page numbering restarts per volume — the `page_label` field preserves the volume's numbering while a separate `global_seq` field provides continuous ordering.

---

## 8. What This Stage Does NOT Do

- Does not detect structural divisions (that's Stage 2)
- Does not correct text or normalize Arabic orthography
- Does not classify content
- Does not involve any LLM processing
