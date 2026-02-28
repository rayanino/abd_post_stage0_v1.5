# Corpus Survey Report: كتب النحو والصرف (Parts 1 + 2)

**Date:** 2026-02-25
**Source:** Shamela exports, user-provided sarf/nahw collections
**Files analyzed:** 19 .htm files (8 multi-volume books)
**Total pages:** 7,271
**Total content headings (tagged):** 5,925

---

## 1. Quote-Style Pattern: CONFIRMED

0 violations across 19 files. Grand total now **176 files, 46,456 pages** — zero exceptions.

---

## 2. القسم Field

**All 19 files: القسم = "كتب اللغة"**

These sarf/nahw books were filed under the broad "كتب اللغة" category, not a science-specific section. Three collections surveyed so far:

| Collection | القسم | Science-useful? |
|-----------|-------|----------------|
| كتب البلاغة | البلاغة | ✓ Yes |
| كتب اللغة | كتب اللغة | ✗ No |
| sarf/nahw uploads | كتب اللغة | ✗ No |

---

## 3. New Keyword: إعراب

| Metric | Value |
|--------|-------|
| Tagged instances | 90 |
| Untagged instances | 280 |
| % untagged | 76% |

**إعراب (syntactic parsing)** is a نحو-specific structural keyword. It marks sections that analyze the grammatical parsing of specific words, verses, or sentences. This is a domain keyword not seen in بلاغة or general لغة books.

**Impact:** Must be added to the structural patterns library as a mid-level division keyword specific to نحو books.

---

## 4. Books Analyzed

| Book | Vols | Pages | Headings | Notes |
|------|------|-------|----------|-------|
| معجم تيمور الكبير في الألفاظ العامية | 5 | 1,771 | 4,346 | Dictionary — extremely high heading density (2.98 h/p max). Each "heading" is a dictionary entry. |
| إسفار الفصيح | 2 | 997 | 0 | **Zero headings** — 997 pages with no tagged structure |
| المزهر في علوم اللغة وأنواعها | 2 | 942 | 630 | Well-structured |
| المذكر والمؤنث | 2 | 892 | 50 | Low heading density |
| تصحيفات المحدثين - العسكري | 2 | 870 | 0 | **Zero headings** — 870 pages with no tagged structure |
| إيضاح شواهد الإيضاح | 2 | 856 | 889 | Rich structure |
| سر صناعة الإعراب | 2 | 761 | 91 | Low-moderate |
| أبو تراب اللغوي وكتابه الاعتقاب | 2 | 182 | 33 | Small |

### Books with zero tagged headings

Two large books have **zero content headings** (double-quote title spans):

- **إسفار الفصيح** (997 pages) — commentary on a lexical text
- **تصحيفات المحدثين** (870 pages) — collected linguistic corrections

These are worst-case scenarios for Stage 2. All structural information must come from Pass 2 (keyword heuristics) and Pass 3 (LLM).

### Dictionary-style books

**معجم تيمور الكبير** has 4,346 headings across 1,771 pages (2.5 h/p average). Each heading is a dictionary entry, not a structural division in the traditional sense. This represents a distinct genre that may need special handling — each "entry" is a micro-passage, potentially too small for standard atomization.

---

## 5. Untagged Keyword Distribution

| Keyword | Untagged | Tagged | % Untagged | Notes |
|---------|----------|--------|-----------|-------|
| إعراب | 280 | 90 | 76% | NEW: نحو-specific |
| شرح | 224 | 2 | 99% | Consistent with other collections |
| كتاب | 100 | 2 | 98% | |
| باب | 95 | 92 | 51% | |
| فصل | 53 | 28 | 65% | |
| قسم | 30 | 13 | 70% | |
| فن | 28 | 8 | 78% | |
| فائدة | 21 | 4 | 84% | |
| حاشية | 20 | 0 | 100% | Consistent |
| تنبيه | 13 | 2 | 87% | |
| ضرب | 22 | 1 | 96% | |
| فرع | 7 | 0 | 100% | |

---

## 6. Impact on Stage Specs

| Finding | Stage | Action |
|---------|-------|--------|
| إعراب as structural keyword (76% untagged) | 2 | Add to patterns library |
| Dictionary-style books (2.5+ h/p) | 2, 3, 4 | New genre: micro-passages. Need passaging strategy. |
| Zero-heading large books (إسفار الفصيح, تصحيفات المحدثين) | 2 | Stress tests for Pass 2+3. Need keyword/LLM-only structure discovery. |
| All القسم = "كتب اللغة" | 0 | Confirms broad-category pattern |
