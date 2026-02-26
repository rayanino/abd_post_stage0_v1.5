# Stage 2: Structure Discovery — Specification

**Status:** Draft — needs zoom-in review (least mature stage)
**Precision level:** Low-Medium (three-pass algorithm defined; passage rules partially catalogued; LLM pass underspecified)
**Dependencies:** Stage 1 (Normalization) must be complete. Requires `pages.jsonl`.

---

## 1. Purpose

Discover the book's internal structural divisions and define passage boundaries. A **passage** is the unit of work for Stages 3–4 (atomization and excerpting). This stage transforms a flat sequence of pages into a hierarchical tree of divisions, then cuts that tree into passage-sized units.

---

## 2. Input

| Input | Source |
|-------|--------|
| `pages.jsonl` | Stage 1 output (normalized, page-per-line) |
| `normalization_report.json` | Stage 1 output (page count, footnote stats) |
| `intake_metadata.json` | Stage 0 output (book metadata) |
| `structural_patterns.yaml` | Pattern library (shipped with app, evolves over time) |

---

## 3. Definitions

### 3.1 Structural Division

A named section of the book as intended by the author (or editor). Examples: باب, فصل, مبحث, تقسيم, خاتمة. A division has:

| Property | Description |
|----------|-------------|
| `id` | Auto-generated unique identifier |
| `type` | The keyword type (باب, فصل, مبحث, etc.) or `implicit` |
| `title` | The full heading text as it appears in the source |
| `level` | Hierarchy depth (0 = root, 1 = top-level, etc.) |
| `detection_method` | `html_tagged`, `keyword_heuristic`, `llm_discovered`, `toc_inferred` |
| `start_page` | First page of this division |
| `end_page` | Last page (exclusive: start of next division or end of book) |
| `parent_id` | ID of the enclosing division (null for top-level) |
| `confidence` | `high` (HTML-tagged), `medium` (keyword match), `low` (LLM-inferred) |
| `digestible` | Whether this division contains content suitable for atomization |

### 3.2 Passage

A contiguous segment of text assigned as one unit of work for Stages 3–4. A passage:
- Corresponds to one or more structural divisions at the **lowest level**
- Has a defined page range (start_page, end_page)
- Has a target size of 2–15 pages (soft guideline, not hard limit)
- Is the smallest independently meaningful unit of the book

### 3.3 Division Tree

The full hierarchical structure of the book. Example for شذا العرف:

```
ROOT: شذا العرف في فن الصرف
├── مقدمة المحقق                          [non-digestible]
├── خطبة الكتاب                           [non-digestible]
├── تقسيم الكلمة                          [passage]
├── الميزان الصرفي                        [passage]
├── الباب الأول: في الفعل
│   ├── التقسيم الأوَّل: إلى ماضٍ ومضارع وأمر
│   │   ├── الباب الأول: فَعَلَ يَفعُل    [passage — UNTAGGED]
│   │   ├── الباب الثاني: فَعَلَ يَفْعِل   [passage — UNTAGGED]
│   │   └── ...
│   ├── التقسيم الثاني للفعل              [passage]
│   └── ...
├── الباب الثاني: في الاسم
│   └── ...
├── الباب الثالث: في أحكام تعمّ الاسم والفعل
│   └── ...
├── مسائل التمرين                         [passage — exercises]
├── تقاريظ الكتاب                         [non-digestible]
└── فهرس الموضوعات                        [non-digestible, cross-reference]
```

---

## 4. The Three-Pass Algorithm

### Pass 1: HTML-Tagged Headings (Deterministic)

**Input:** Raw HTML (from frozen source, NOT from pages.jsonl)
**Method:** Extract all `<span class="title">` and `<span data-type="title">` elements.
**Output:** List of tagged headings with page numbers.

**Rules:**
1. Skip all headings in the metadata page (first `PageText` div before any `PageNumber` span).
2. Strip HTML tags, `&nbsp;`, `&#8204;` (ZWNJ) from heading text.
3. Normalize whitespace (collapse multiple spaces to one).
4. Record the page number from the nearest preceding `<span class='PageNumber'>` marker.
5. If a heading has no preceding page number (rare), assign page 1 with a warning.

**Known limitations:**
- Not all divisions are tagged (see شذا العرف: 6 untagged أبواب within التقسيم الأول).
- Some tags are decorative section names that don't introduce new divisions (e.g., "أنواع الجناس اللفظي" could be a sub-heading within a مبحث, not a new division).
- The TOC page may have headings that are references, not divisions.

### Pass 2: Keyword Heuristic Detection (Deterministic)

**Input:** `pages.jsonl` (normalized text)
**Method:** Scan all lines for division keywords at line-start positions.
**Output:** List of candidate untagged headings with confidence scores.

**Rules:**

**Step 2.1 — Line extraction:**
For each page in `pages.jsonl`, split content into lines. A "line" is text separated by newlines in the normalized output.

**Step 2.2 — Keyword matching:**
For each line, check if it starts with a division keyword (from `structural_patterns.yaml`):

| Match type | Example | Confidence |
|------------|---------|------------|
| Keyword + ordinal + title | `الباب الأول: فَعَلَ يَفعُل` | Medium-High |
| Keyword + ordinal only | `المبحث الثاني عشر` | Medium |
| Keyword + title (no ordinal) | `فصل في معاني صيغ الزوائد` | Medium |
| Keyword alone | `تنبيهات` | Medium-Low |
| Keyword + dash + content | `تنبيه -قد عَلِمت...` | Low (inline) |

**Step 2.3 — False positive filtering:**

A keyword match is REJECTED if:
- The line is longer than 300 characters (likely a sentence that happens to start with the keyword, not a heading)
- The keyword is part of a quote or citation (`قال في باب كذا`, `ذكر في فصل كذا`)
- The keyword appears mid-sentence (preceded by a conjunction: و, ف, ثم + keyword)
- The line is within a footnote (if footnotes are separated by Stage 1)
- The keyword is `ضرب` used in its verbal meaning ("struck"), not its division meaning ("type") — heuristic: check if followed by an ordinal or title

**Step 2.4 — Deduplication with Pass 1:**
If a keyword candidate matches a Pass 1 heading (same page, similar text), discard the duplicate — Pass 1 already found it.

### Pass 3: LLM-Assisted Discovery

**Input:** Full normalized text, Pass 1 + Pass 2 results, structural_patterns.yaml
**Method:** LLM reads the text with the existing heading list and identifies gaps.
**Output:** Additional divisions, corrections, hierarchy assignments, digestibility flags.

**What the LLM does:**

1. **Gap detection:** Identify divisions that Pass 1 and Pass 2 missed — especially implicit transitions where no keyword is used but the topic clearly changes.

2. **False positive correction:** Flag any Pass 1 or Pass 2 headings that are NOT real structural divisions (e.g., a line that starts with "باب" but is actually part of a sentence).

3. **Hierarchy assignment:** Determine parent-child relationships between all divisions. This is critical because:
   - In شذا العرف, `الباب الأول: فَعَلَ يَفعُل` is a CHILD of `التقسيم الأوَّل`, which is a CHILD of `الباب الأول: في الفعل`. The nesting is: باب > تقسيم > باب (same keyword at different levels!).
   - In جواهر البلاغة, the hierarchy is: علم > باب > مبحث (clean 3-level).
   - The LLM must infer the correct nesting from context, not from keywords alone.

4. **Digestibility classification:** Mark each division as digestible or non-digestible:
   - `digestible`: Contains teaching or exercise content in one of our sciences
   - `non_digestible`: Editor introduction, table of contents, endorsements, bibliography, colophon
   - `uncertain`: Needs human review (e.g., author's مقدمة which may contain both praise and substantive content)

5. **TOC cross-reference:** If a TOC page exists, compare the TOC entries against the discovered divisions. Flag any TOC entries with no matching division (missed heading) and any divisions with no TOC entry (possible false positive or sub-section not in TOC).

**LLM prompt design:** [TO BE SPECIFIED — needs zoom-in. The prompt must include: the full list of Pass 1+2 headings, relevant pages of text for context, structural_patterns.yaml excerpt, and clear instructions for each task above.]

**LLM output format:** [TO BE SPECIFIED — structured JSON with division list, hierarchy, corrections, digestibility.]

---

## 5. Hierarchy Inference

After all three passes, the system has a flat list of divisions. The hierarchy must be built.

### 5.1 Inference rules (in priority order)

1. **Explicit nesting from keywords:** If keywords follow a known hierarchy (e.g., باب > مبحث), use it. But ONLY within the same book — hierarchy is book-specific.

2. **Ordinal sequence continuity:** If consecutive divisions share the same keyword with sequential ordinals (المبحث الأول, المبحث الثاني, المبحث الثالث), they are siblings.

3. **Page containment:** If division A spans pages 10–50 and division B spans pages 15–20, B is likely a child of A. But only if A's keyword is at a higher hierarchy level.

4. **LLM judgment:** For ambiguous cases, the LLM's hierarchy assignment from Pass 3 is the tiebreaker.

5. **TOC indentation:** If a TOC exists and uses indentation or dot-leaders, the indentation pattern implies hierarchy.

### 5.2 Known ambiguities

| Ambiguity | Example | Resolution |
|-----------|---------|------------|
| Same keyword at different levels | شذا العرف: الباب الأول (top) vs الباب الأول: فَعَلَ يَفعُل (nested) | Context: the nested باب has a verb-paradigm title, appears within a تقسيم. LLM must detect this. |
| Unnumbered divisions | `تنبيهات` with no ordinal | Treat as a child of the nearest preceding numbered division |
| Multiple تنبيه blocks | Several `تنبيه` sections within one مبحث | Each is a separate division, sibling to each other, child of the مبحث |
| Implicit topic change | Author shifts from one grammatical topic to another without any heading | LLM Pass 3 must detect. Marked as `implicit` type with `low` confidence. |

---

## 6. Passage Construction

Once the division tree is built, passages are cut from it.

### 6.1 Core rule

**A passage corresponds to one leaf-level division** (a division with no children).

If a division has children, it is NOT a passage — its children are.
If a division has no children AND is digestible, it IS a passage.
If a division has no children AND is non-digestible, it is SKIPPED.

### 6.2 Sizing rules

| Condition | Action |
|-----------|--------|
| Leaf division is 2–15 pages | Standard passage. No action needed. |
| Leaf division is > 20 pages | Flag for review: "This division is unusually long. Consider whether the author has implicit sub-divisions that were missed." |
| Leaf division is > 30 pages | Strongly recommend splitting. LLM should attempt to find internal topic boundaries. |
| Leaf division is < 1 page | Consider merging with adjacent sibling (see merge rules). |
| Leaf division is 1–2 pages | Acceptable as standalone if it's a self-contained topic. |

### 6.3 Merge rules

A short division (<1 page) is merged with its context according to:

| Situation | Rule |
|-----------|------|
| تنبيه / فرع < 1 page | Merge into parent division's passage |
| خاتمة at end of a باب | Merge into the last passage of that باب |
| Standalone heading with no content | Merge into next division |
| Multiple tiny siblings (<1 page each) | Merge together into one passage if total < 15 pages |

### 6.4 Split rules

A long division is split when:

| Situation | Rule |
|-----------|------|
| LLM identifies internal topic boundaries | Split at those boundaries |
| No internal boundaries found but >30 pages | Split at natural paragraph breaks, targeting ~10 pages per passage |
| Exercise section >15 pages | Split into groups of related exercises |

### 6.5 Never-merge rules

| Rule | Reason |
|------|--------|
| Never merge across different باب | Each باب is a sovereign topic |
| Never merge across different علم (e.g., المعاني → البيان) | Science boundary |
| Never merge a مقدمة with content chapters | Different function |
| Never merge exercises with teaching content | Different excerpt roles |

### 6.6 Never-split rules

| Rule | Reason |
|------|--------|
| Never split an exercise set that refers to the same examples | Breaks cross-references |
| Never split a proof/argument mid-reasoning | Destroys logical coherence |
| Never split a verse + its commentary if < 5 pages | Bonded content |

---

## 7. Output Artifacts

### 7.1 `divisions.json`

Complete division tree in JSON. Each node:

```json
{
  "id": "div_007",
  "type": "باب",
  "title": "الباب الأول: فَعَلَ يَفعُل",
  "level": 3,
  "parent_id": "div_003",
  "detection_method": "keyword_heuristic",
  "confidence": "medium",
  "start_page": 23,
  "end_page": 24,
  "digestible": true,
  "page_count": 2,
  "children": []
}
```

### 7.2 `passages.jsonl`

One passage per line:

```json
{
  "passage_id": "P001",
  "division_ids": ["div_007"],
  "title": "الباب الأول: فَعَلَ يَفعُل",
  "start_page": 23,
  "end_page": 24,
  "page_count": 2,
  "sizing_action": "none",
  "sizing_notes": null,
  "digestible": true,
  "content_type": "teaching",
  "review_flags": []
}
```

### 7.3 `structure_report.json`

Summary statistics and flags for human review.

### 7.4 `structure_review.md`

Human-readable Markdown for VSCode review. Shows the full division tree with page numbers, passage assignments, and any flags.

---

## 8. Human Review Gate

After this stage, the user reviews `structure_review.md` and:
- Confirms or corrects the division tree
- Approves or adjusts passage boundaries
- Marks any flagged passages as approved / needs-split / needs-merge

The user's decisions are recorded in `structure_overrides.json` and applied before Stage 3 begins.

---

## 9. Edge Cases

→ See `edge_cases.md` in this folder.

---

## 10. Open Questions (To Resolve During Zoom-In)

1. **LLM prompt design for Pass 3:** How much text does the LLM see? Full book? Chapter-by-chapter? What few-shot examples do we provide?
2. **TOC parsing specifics:** Dot-leader pattern extraction, page number matching, handling of TOC pages that span multiple pages.
3. **Multi-volume structure:** How do volumes affect the division tree? Is each volume a top-level node?
4. **Books with no structure at all:** Some old manuscripts may have zero headings, zero keywords. Pure LLM discovery? Or refuse to process?
5. **Editor-inserted divisions vs author's original:** Some editors add section headings that the author didn't write. Should these be treated differently?
6. **Confidence threshold for passage creation:** At what confidence level does an LLM-discovered division become a passage boundary? Or do all divisions above `low` qualify?
