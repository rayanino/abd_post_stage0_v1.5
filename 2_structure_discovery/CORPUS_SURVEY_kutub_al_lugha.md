# Corpus Survey Report: كتب اللغة Collection

**Date:** 2026-02-25
**Source:** Shamela desktop library export, كتب اللغة section
**Files analyzed:** 79 .htm files (60 single-volume + 8 multi-volume books totaling 19 files)
**Total pages:** 18,981
**Total content headings (tagged):** 9,111

---

## 1. Critical Discovery: Quote-Style Differentiator

Shamela HTML uses **two distinct quote styles** for `<span>` title attributes:

| Style | Example | Location | Count | Purpose |
|-------|---------|----------|-------|---------|
| Single quotes | `<span class='title'>` | ONLY in first PageText div | 685 | Metadata labels (القسم, المؤلف, etc.) |
| Double quotes | `<span class="title">` | Content pages | 9,505 | Content headings (باب, فصل, مبحث, etc.) |

**This is 100% reliable across all 79 files.** All 685 single-quote spans are in the first PageText div. All 9,505 double-quote spans are in content pages. Zero exceptions.

**Impact on Stage 2 (Structure Discovery):** Pass 1 should use ONLY double-quote spans for content heading extraction. The metadata card parsing (Stage 0) should use single-quote spans.

---

## 2. Metadata Card Structure

### 2.1 Field prevalence

| Field | Label(s) in HTML | Prevalence | Notes |
|-------|------------------|-----------|-------|
| Title | First `<span class='title'>` | 79/79 (100%) | Always present; followed by `&nbsp;` padding |
| القسم | `القسم:` | 79/79 (100%) | **Always "كتب اللغة"** in this collection — NOT science-specific |
| الكتاب | `الكتاب:` | 79/79 (100%) | Book title (may differ from span title) |
| المؤلف | `المؤلف:` | 79/79 (100%) | Author name with death date in parentheses |
| تاريخ النشر بالشاملة | `تاريخ النشر بالشاملة:` | 79/79 (100%) | Shamela upload date (Hijri) |
| الناشر | `الناشر:` | 73/79 (92%) | Publisher + city |
| عدد الصفحات | `عدد الصفحات:` | 52/79 (66%) | **Often inaccurate** — see §2.3 |
| المحقق / تحقيق | `المحقق:` or `تحقيق:` | 41/79 (52%) | Editor — **two different label variants** |

### 2.2 Editor field label variants

| Label | Count | Notes |
|-------|-------|-------|
| المحقق | 33 | Standard form |
| تحقيق | 8 | Alternative form |

**Impact on Stage 0 (Intake):** Must check for BOTH labels when extracting editor.

### 2.3 Page count mismatch

Of the 52 books with a عدد الصفحات field, **36 (69%) have a mismatch** of more than 5 pages with the actual HTML page count.

Examples of extreme mismatches:
- أصول علم العربية في المدينة: declared 383, actual 121 (diff -262)
- إصلاح المنطق: declared 312, actual 386 (diff +74)

**Impact on Stage 0:** The عدد الصفحات field is **informational only — never trust it for validation**. Use actual HTML page count.

### 2.4 القسم field finding

**All 79 files in this collection have القسم: "كتب اللغة"**. This is the Shamela library section name, NOT a science classification.

**Impact on Stage 0:** The original intake spec assumed القسم would indicate the science (بلاغة, نحو والصرف, etc.). This assumption is **WRONG** for this collection. The science validation logic must be updated:
- القسم MAY indicate the science in dedicated science collections (e.g., Shamela's النحو والصرف section)
- القسم may be a broader category (كتب اللغة, أصول الفقه, etc.) that doesn't map to our four sciences
- The user's science hint becomes MORE important, not less

### 2.5 HTML structure pattern

```html
<!-- Metadata card: single-quote spans -->
<div class='PageText'>
  <span class='title'>BOOK_TITLE&nbsp;&nbsp;&nbsp;</span>
  <span class='footnote'>(AUTHOR_SHORT)</span>
  <p><span class='title'>القسم:</span> VALUE
  <hr>
  <p><span class='title'>الكتاب<font color=#be0000>:</font></span> VALUE
  <p><span class='title'>المؤلف<font color=#be0000>:</font></span> VALUE
  ...
</div>

<!-- Content pages: double-quote spans -->
<div class='PageText'>
  <div class='PageHead'>
    <span class='PartName'>BOOK_TITLE</span>
    <span class='PageNumber'>(ص: ١)</span>
    <hr/>
  </div>
  &#8204;<span class="title">&#8204;HEADING_TEXT</span>
  ...
</div>
```

**Notable:** Content headings are preceded by `&#8204;` (ZWNJ — zero-width non-joiner). This is a Shamela convention, not a meaningful character.

---

## 3. Structural Heading Analysis

### 3.1 Heading density distribution

| Category | Count | Description |
|----------|-------|-------------|
| Zero headings | 7 books | Worst case for Stage 2 — pure keyword/LLM detection needed |
| Low (1–5 headings, >50 pages) | 1 book | Nearly unstructured |
| Moderate (6–20 headings) | 16 books | Partially structured |
| Rich (>20 headings) | 55 books | Well-structured, Pass 1 covers most divisions |

### 3.2 Books with zero content headings

| Book | Pages | Notes |
|------|-------|-------|
| مغالطات لغوية | 264p | Large book, zero tagged headings — all structure is untagged |
| إسفار الفصيح vol.1 | 547p | Multi-volume, likely has structure via keywords |
| تصحيفات المحدثين vol.2 | 489p | Multi-volume |
| إسفار الفصيح vol.2 | 450p | Multi-volume |
| تصحيفات المحدثين vol.1 | 381p | Multi-volume |
| حكمة الإشراق (نوادر) | 50p | Short book |
| اختصار كتاب درة الغواص | 42p | Short book |

**Key concern:** The multi-volume books' individual volume files may have zero tagged headings even though the book IS structured. The headings might only exist via keywords or TOC.

### 3.3 Division keywords used in tagged headings

| Keyword | Count in title spans | Notes |
|---------|---------------------|-------|
| باب | 526 | Most common structural division |
| فصل | 256 | Second most common |
| قسم | 102 | Section divisions |
| كتاب | 89 | Top-level (in large compilations) |
| مدخل | 60 | Entry/introduction (common in this collection) |
| نوع | 49 | Type classification |
| مقدمة | 30 | Introduction |
| مطلب | 25 | Topic/request |
| مبحث | 20 | Investigation/study |
| خاتمة | 15 | Conclusion |
| فهرس | 13 | Table of contents |
| تمهيد | 9 | Preliminary |
| تنبيه | 8 | Note/warning — mostly UNTAGGED (see below) |
| فن | 8 | Art/discipline |
| ملحق | 5 | Appendix |
| أصل | 4 | Principle/root |
| فائدة | 4 | Benefit/note |
| فرع | 3 | Branch/sub-topic |
| تقسيم | 1 | Classification — rare in tags, common in شذا العرف |
| تتمة | 1 | Supplement |
| ضرب | 1 | Type |

### 3.4 Untagged division keywords (outside title spans)

**82% of books (65/79) have untagged division keywords.**

| Keyword | Untagged instances | Notes |
|---------|-------------------|-------|
| مدخل | 895 | Extremely common untagged — likely dictionary/chapter entries |
| فصل | 744 | Major untagged structural marker |
| باب | 282 | Significant untagged presence |
| كتاب | 166 | |
| فن | 64 | |
| قاعدة | 48 | Rule — common in grammar books |
| قسم | 47 | |
| مقدمة | 44 | |
| تنبيه | 37 | Almost always untagged |
| فائدة | 27 | Note — almost always untagged |
| مبحث | 26 | |
| نوع | 21 | |
| تمهيد | 20 | |
| فرع | 14 | |

**Impact on Stage 2:** Pass 2 (keyword heuristics) is ESSENTIAL. The untagged-to-tagged ratio for some keywords is very high:
- تنبيه: 37 untagged vs 8 tagged (82% missed by Pass 1)
- فائدة: 27 untagged vs 4 tagged (87% missed)
- قاعدة: 48 untagged vs 0 tagged (100% missed)
- مدخل: 895 untagged vs 60 tagged (94% missed)

---

## 4. Multi-Volume Books

| Book | Volumes | Total pages |
|------|---------|-------------|
| معجم تيمور الكبير في الألفاظ العامية | 5 | 1,771 |
| إسفار الفصيح | 2 | 997 |
| المزهر في علوم اللغة وأنواعها | 2 | 942 |
| المذكر والمؤنث | 2 | 892 |
| تصحيفات المحدثين - العسكري | 2 | 870 |
| إيضاح شواهد الإيضاح | 2 | 856 |
| سر صناعة الإعراب | 2 | 761 |
| أبو تراب اللغوي وكتابه الاعتقاب | 2 | 182 |

**Finding:** Volume files are numbered (`001.htm`, `002.htm`, etc.). Metadata is in the first volume only.

---

## 5. Structural Patterns Library Updates

New patterns discovered from this corpus that must be added to `structural_patterns.yaml`:

1. **Quote-style differentiator** (single vs double quotes) — deterministic metadata/content separator
2. **مدخل** as major structural keyword (895 untagged instances)
3. **فائدة** and **قاعدة** as structural keywords (almost always untagged)
4. **ZWNJ (&#8204;)** prefix before content headings — Shamela convention
5. **`<span class='footnote'>` after book title** — contains author short name
6. **`<font color=#be0000>:</font>`** — red-colored colons in metadata fields
7. **`[ترقيم الكتاب موافق للمطبوع]`** — standard Shamela note about page numbering alignment

---

## 6. Impact on Stage Specs

| Stage | Impact |
|-------|--------|
| **0 (Intake)** | القسم field is unreliable for science identification. عدد الصفحات often wrong. Editor field has label variants. |
| **1 (Normalization)** | New patterns confirmed: red-colored colons, ZWNJ prefixes, footnote span format. |
| **2 (Structure Discovery)** | Pass 1 must use double-quote spans ONLY. Pass 2 is critical (82% of books have untagged divisions). New keywords: مدخل, فائدة, قاعدة. |
| **3–4 (Atomization/Excerpting)** | No direct impact from this survey (content analysis needed separately). |
