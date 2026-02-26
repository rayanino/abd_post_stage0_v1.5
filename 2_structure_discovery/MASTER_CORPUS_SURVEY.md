# Master Corpus Survey Report

**Date:** 2026-02-25
**Status:** Complete (all user-provided collections analyzed)

---

## Corpus Summary

| Collection | Files | Pages | Content headings | القسم |
|-----------|-------|-------|-----------------|-------|
| كتب اللغة | 79 | 18,981 | 9,505 | كتب اللغة |
| كتب البلاغة | 78 | 20,204 | 6,219 | البلاغة |
| جواهر البلاغة (gold baseline) | 1 | 308 | 80 | البلاغة |
| شذا العرف في فن الصرف | 1 | 187 | 65 | النحو والصرف |
| **TOTAL (deduplicated)** | **159** | **39,680** | **15,869** | — |

Note: The sarf/nahw uploads (parts 1–3) were subsets of كتب اللغة. All files were already counted in the main collection.

---

## Findings That Are Now Validated at Scale

### 1. Quote-Style Differentiator (159/159 files, 0 exceptions)

| Style | Purpose | Location |
|-------|---------|----------|
| `<span class='title'>` (single quote) | Metadata labels | ONLY in first PageText div |
| `<span class="title">` (double quote) | Content headings | ONLY in content pages |

**Verdict: Shamela-wide invariant.** Safe to hard-code in Pass 1.

### 2. القسم Reliability

| Value | Count | Useful for science? |
|-------|-------|-------------------|
| كتب اللغة | 79 | ✗ Broad category — not science-specific |
| البلاغة | 79 | ✓ Maps directly to `balagha` |
| النحو والصرف | 1 | ⚠ Maps to two sciences — user must clarify |

**Verdict:** Tiered reliability model confirmed. القسم is only useful when it directly names a science.

### 3. Metadata Card Structure

| Field | Prevalence | Notes |
|-------|-----------|-------|
| Title | 159/159 (100%) | Always first single-quote title span |
| المؤلف | 159/159 (100%) | |
| القسم | 159/159 (100%) | |
| الكتاب | 159/159 (100%) | |
| تاريخ النشر بالشاملة | 159/159 (100%) | Hijri date |
| الناشر | ~92% | Occasionally missing |
| عدد الصفحات | ~66% | **Often inaccurate** (69% mismatch rate) |
| Editor | ~52% | **6 known label variants** (see below) |

**Editor label variants:** المحقق, تحقيق, ضبط, إعداد, دراسة وتحقيق, تخريج, علق (7th variant found in part 3)

### 4. Structural Keywords — Tagged vs Untagged

Combined across all collections:

| Keyword | Tagged | Untagged | % Untagged | Classification |
|---------|--------|----------|-----------|----------------|
| حاشية | 0 | 2,379 | 100% | **Always** untagged |
| شرح | 7 | 1,500 | 100% | **Always** untagged |
| قاعدة | 7 | 102 | 94% | **Almost always** untagged |
| فائدة | 15 | 81 | 84% | **Mostly** untagged |
| تنبيه | 56 | 230 | 80% | **Mostly** untagged |
| مدخل | 128 | 1,795 | 93% | **Almost always** untagged (but high-volume in dictionaries) |
| إعراب | 91 | 294 | 76% | **Mostly** untagged (نحو-specific) |
| فصل | 594 | 1,724 | 74% | **Often** untagged |
| كتاب | 120 | 574 | 83% | **Mostly** untagged |
| فن | 33 | 266 | 89% | **Mostly** untagged |
| قسم | 190 | 545 | 74% | **Often** untagged |
| باب | 1,293 | 610 | 32% | **Mostly** tagged |
| مبحث | 228 | 138 | 38% | **Mostly** tagged |
| مقدمة | 104 | 122 | 54% | **Mixed** |
| خاتمة | 48 | 25 | 34% | **Mostly** tagged |
| مطلب | 62 | 4 | 6% | **Almost always** tagged |

**Key insight:** Pass 1 (HTML extraction) is sufficient only for باب, مبحث, مطلب, and خاتمة. For everything else, Pass 2 (keyword heuristics) is essential. For حاشية and شرح, Pass 1 catches literally nothing.

### 5. Heading Density Distribution

| Category | Files | % | Description |
|----------|-------|---|-------------|
| Zero headings | ~12 | 8% | Entirely unstructured (worst case) |
| Low (0.01–0.10 h/p) | ~25 | 16% | Sparse structure |
| Medium (0.10–0.50 h/p) | ~50 | 31% | Moderate structure |
| High (0.50–1.00 h/p) | ~35 | 22% | Well-structured |
| Very high (>1.00 h/p) | ~37 | 23% | Dictionary-style or extremely detailed |

### 6. Genre Patterns Identified

| Genre | Characteristics | Examples | Stage 2 impact |
|-------|----------------|----------|----------------|
| **Textbook** | Clear باب/فصل/مبحث hierarchy, exercises | جواهر البلاغة, شذا العرف | Standard 3-pass algorithm works well |
| **Commentary (شرح)** | متن/شرح/حاشية layers, حاشية markers | حاشية الدسوقي, الأطول شرح تلخيص | Needs layer-aware atomization |
| **Dictionary/Lexicon** | Very high heading density (>1 h/p), micro-entries | معجم تيمور (2.5 h/p) | Group entries into passage batches |
| **Unstructured** | Zero or near-zero tagged headings | إسفار الفصيح, تصحيفات المحدثين | Full reliance on Pass 2+3 |
| **Poetry/Verse collection** | شواهد (witnesses/citations) as structure | إيضاح شواهد الإيضاح | Verse-centric passaging |

### 7. Multi-Volume Books

| Size | Count | Notes |
|------|-------|-------|
| 2 volumes | 15+ | Most common |
| 3–4 volumes | 6 | |
| 5 volumes | 2 | |
| 15 volumes | 1 | شرح مائة المعاني والبيان (~20p each) |
| 28 files (collection) | 1 | كتب البلاغة sub-collection (not a single book) |

---

## Impact Summary on Stage Specs

| Stage | Findings incorporated | Still needed |
|-------|----------------------|-------------|
| **0 (Intake)** | القسم tiered reliability ✓, 7 editor labels ✓, page count unreliability ✓, quote-style differentiator ✓ | Testing with actual intake code |
| **1 (Normalization)** | Existing spec validated against jawahir; corpus confirms patterns | Run normalizer on 5+ diverse books |
| **2 (Structure Discovery)** | 17 keywords catalogued with tagged/untagged ratios ✓, 3 corpus surveys ✓, 17 edge cases ✓, genre patterns identified ✓ | LLM prompt design, TOC parsing, hierarchy inference testing |
| **3 (Atomization)** | Commentary layer challenge identified | Gold data for non-بلاغة sciences, table handling for صرف |
| **4 (Excerpting)** | Multi-topic framework (A/B/C categories) ✓, 20 edge cases ✓ | LLM prompt design, science classification testing |
| **5 (Taxonomy)** | Base tree for بلاغة exists | Trees for صرف, نحو, إملاء |
| **6 (Validation)** | Architecture defined | Judge prompts, calibration data |
