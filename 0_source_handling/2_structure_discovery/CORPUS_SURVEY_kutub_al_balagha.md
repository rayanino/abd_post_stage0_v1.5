# Corpus Survey Report: كتب البلاغة Collection

**Date:** 2026-02-25
**Source:** Shamela desktop library export, كتب البلاغة section
**Files analyzed:** 78 .htm files (28 single-volume + 14 multi-volume books)
**Total pages:** 20,204
**Total content headings (tagged):** 6,190

---

## 1. Quote-Style Pattern: CONFIRMED

Single-quote metadata / double-quote content pattern holds with **0 violations across 78 files**. Combined with كتب اللغة, the pattern is now validated across **157 files, 39,185 pages** with zero exceptions.

---

## 2. القسم Field

**All 78 files: القسم = "البلاغة"**

Unlike كتب اللغة (where القسم was a broad library category), here it IS science-specific. This creates two tiers:

| Collection | القسم value | Useful for science? |
|-----------|------------|-------------------|
| كتب البلاغة | البلاغة | ✓ Yes — directly maps to `balagha` |
| كتب اللغة | كتب اللغة | ✗ No — broad category |

**This confirms the intake spec's tiered reliability model is correct.**

---

## 3. Editor Label Variants — Expanded

| Label | كتب اللغة | كتب البلاغة | Combined |
|-------|-----------|-------------|----------|
| المحقق | 33 | 20 | 53 |
| تحقيق | 8 | 21 | 29 |
| ضبط | 0 | 7 | 7 |
| إعداد | 0 | 2 | 2 |
| دراسة وتحقيق | 0 | 1 | 1 |
| تخريج | 0 | 1 | 1 |

**New finding:** `ضبط` appears in 7 بلاغة files. This is a third editor label variant not seen in كتب اللغة. Total known editor labels: **المحقق, تحقيق, ضبط, إعداد, دراسة وتحقيق, تخريج**.

---

## 4. Structural Heading Analysis

### 4.1 Heading density — much richer than كتب اللغة

| Metric | كتب اللغة | كتب البلاغة |
|--------|-----------|-------------|
| Zero-heading files | 7 (9%) | 1 (1%) |
| Median headings/page | 0.00 | 0.18 |
| Max headings/page | 0.40 | 1.84 |
| Total content headings | 9,111 | 6,190 |

البلاغة books are generally much better structured with HTML headings than كتب اللغة books.

### 4.2 Tagged keyword distribution

| Keyword | Count | Notes |
|---------|-------|-------|
| فصل | 338 | Most common |
| باب | 241 | |
| مبحث | 188 | Much more common here than in كتب اللغة (20) |
| ضرب | 148 | **NEW: Very common in بلاغة** (types of rhetorical devices) |
| نوع | 104 | Types/categories |
| تقسيم | 77 | Classifications |
| مدخل | 70 | |
| قسم | 67 | |
| تنبيه | 44 | |
| مقدمة | 44 | |
| فن | 25 | |
| كتاب | 21 | |
| خاتمة | 18 | |
| مطلب | 12 | |
| مسألة | 8 | |
| تمهيد | 8 | |
| قاعدة | 7 | |
| فائدة | 7 | |

### 4.3 Untagged keywords — critical finding: حاشية

**100% of بلاغة files have untagged divisions** (vs 82% in كتب اللغة).

| Keyword | Untagged | Tagged | % Untagged | Notes |
|---------|----------|--------|-----------|-------|
| **حاشية** | **2,359** | **0** | **100%** | **NEW: Massively common, NEVER tagged** |
| شرح | 531 | 4 | 99% | Commentary markers |
| قسم | 368 | 67 | 85% | |
| فصل | 266 | 338 | 44% | Significant untagged presence |
| كتاب | 208 | 21 | 91% | |
| نوع | 157 | 104 | 60% | |
| تنبيه | 154 | 44 | 78% | Confirms كتب اللغة finding |
| فن | 148 | 25 | 86% | |
| ضرب | 99 | 148 | 40% | |
| مبحث | 86 | 188 | 31% | |
| تقسيم | 80 | 77 | 51% | |
| فرع | 27 | 3 | 90% | |
| فائدة | 21 | 7 | 75% | |

**حاشية (marginal note/commentary)** is the single most common untagged keyword in the entire corpus so far — 2,359 instances, zero tagged. This is a genre-specific pattern: بلاغة books (especially شروح — commentaries) heavily use حاشية markers.

---

## 5. Multi-Volume Books

| Book | Vols | Pages | Notes |
|------|------|-------|-------|
| كتب البلاغة (main collection) | 28 | 8,562 | Contains 28 single-volume books |
| حاشية الدسوقي على مختصر المعاني | 4 | 2,334 | Largest — commentary genre |
| المنهاج الواضح للبلاغة | 5 | 1,115 | |
| الأطول شرح تلخيص مفتاح العلوم | 2 | 1,133 | Commentary genre |
| البلاغة العربية | 2 | 1,112 | |
| المثل السائر في أدب الكاتب والشاعر | 4 | 992 | |
| عروس الأفراح في شرح تلخيص المفتاح | 2 | 969 | Commentary genre |
| بغية الإيضاح لتلخيص المفتاح | 4 | 709 | |
| معاهد التنصيص على شواهد التلخيص | 2 | 694 | |
| دلائل الإعجاز ت شاكر | 2 | 688 | |
| الطراز لأسرار البلاغة | 3 | 682 | Richest heading density |
| الإيضاح في علوم البلاغة | 3 | 638 | |
| شرح مائة المعاني والبيان | 15 | 302 | 15 volumes! (very short each) |
| من قضايا البلاغة والنقد | 2 | 274 | |

**Notable:** شرح مائة المعاني والبيان has 15 volumes (~20 pages each). This is an extreme case for multi-volume handling.

---

## 6. Genre Pattern: Commentary Books (شروح)

A significant portion of بلاغة books are **commentaries** (شرح on an earlier text). These have distinctive structural patterns:

- **حاشية markers** (2,359 instances) — marginal notes commenting on specific passages
- **شرح markers** (531 untagged) — explanatory commentary sections
- Multi-layered structure: original text (متن) + commentary (شرح) + super-commentary (حاشية)
- The books حاشية الدسوقي, الأطول شرح تلخيص, عروس الأفراح, بغية الإيضاح are all commentary stacks

**Impact on Stage 3–4:** Commentary books present a unique challenge — the "atoms" are not just the author's teaching, but layers of commentary on earlier text. The excerpting stage must handle:
- Original text (متن) atoms vs commentary atoms
- Attributing content to the correct author layer
- حاشية notes that are often very short and highly specific

---

## 7. Books Already in Our Gold Data

**جواهر البلاغة في المعاني والبيان والبديع** (308 pages, 80 content headings) is in this collection AND is our gold baseline source. This validates that our gold data is representative of at least the well-structured end of the بلاغة spectrum.

---

## 8. Impact on Stage Specs

| Finding | Affected stages | Action needed |
|---------|----------------|---------------|
| حاشية: 2,359 untagged, 100% untagged | Stage 2 | Add to structural_patterns.yaml as new keyword. Critical for commentary books. |
| شرح: 531 untagged, 99% untagged | Stage 2 | Add as keyword. |
| Commentary book structure (متن/شرح/حاشية layers) | Stages 3–4 | New edge case: how to atomize/excerpt layered commentary. Not yet addressed in any spec. |
| ضرب as common tagged keyword (148) | Stage 2 | Already in patterns library; confirmed as important for بلاغة. |
| Editor labels: ضبط, إعداد, دراسة وتحقيق, تخريج | Stage 0 | Must check ALL six label variants. |
| 15-volume book | Stage 0, 1 | Multi-volume extreme case. |
| القسم = "البلاغة" | Stage 0 | Confirms tiered reliability model — بلاغة collection IS science-specific. |
