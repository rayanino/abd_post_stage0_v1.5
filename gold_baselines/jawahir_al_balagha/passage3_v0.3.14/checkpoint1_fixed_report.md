# CHECKPOINT 1 — FIXED & DECISIONED (Passage 3)

**Scope:** printed pages ص ٣٣ → ص ٤٠ (جواهر البلاغة)

This file documents CP1-only decisions and produces **human-review views** derived from the Shamela HTML page blocks:
- `checkpoint1_matn_pages_33_40_fixed.txt` (MATN-only view; footnote bodies removed)
- `checkpoint1_footnotes_pages_33_40_raw.txt` (FOOTNOTES view by page)
- `checkpoint1_footnotes_unitized.txt` (FOOTNOTES split into (n) units per page)

**Binding note:** the canonical CP1 artifacts remain:
- `passage3_clean_matn_input.txt`
- `passage3_clean_fn_input.txt` (empty)
- `passage3_source_slice.json`

The “fixed” views do **not** replace the CP1 artifacts; they are review aids only (regeneratable from HTML).

---

## Decisions resolving CP1 flags / risks

### FLAG 1 — Truncated footnote at slice boundary (p40 fn(1))

- **Observation:** p40 footnote (1) ends with `ومنها ما يكون في =` indicating continuation beyond ص ٤٠.
- **Decision:** keep the footnote text **as-is** (no guessing / no completion).
- **Downstream impact:** later excerpting must use **split-resumes-later** relations for the relevant footnote excerpt(s), with an unresolved target hint (continued after ص ٤٠).

### FLAG 2 — Repeated footnote numbers across pages

- **Observation:** numbering (1)(2)… restarts per page (book/print convention).
- **Decision:** treat markers as **page-local**; do not renumber.
- **Downstream mapping rule:** matn→footnote linking must use **(page_hint + within-page order)** to map markers to globally unique footnote atoms.

### FLAG 3 — Mixed marker encodings inside footnote blocks

- **Observation:** within a page’s footnote block, the first note appears as literal `(1)`, while subsequent notes are introduced by red `<font>(2)</font>` etc.
- **Decision:** in review views (and later canonicalization), normalize these to literal line-start markers `(n)` for deterministic unit splitting, while preserving CP1 raw extraction.

### FLAG 4 — Exercise verse continuity (multi-line units)

- **Observation:** the “تطبيق” section contains verse units that may span two lines (and some lines include `… ...` separators).
- **Decision (recorded now; applied later at CP4):** treat clearly single quoted units as one exercise item, even if multiple lines.

### FLAG 5 — Page 39 has no footnote block

- **Observation:** p39 has no `<div class='footnote'>` in the Shamela HTML.
- **Decision:** accept as source truth; no synthetic empty footnote units.

---

## A) MATN extraction (review view, fixed)

See: `checkpoint1_matn_pages_33_40_fixed.txt`

## B) FOOTNOTE extraction (review view, raw by page)

See: `checkpoint1_footnotes_pages_33_40_raw.txt`

## C) FOOTNOTE extraction (review view, unitized)

See: `checkpoint1_footnotes_unitized.txt`
