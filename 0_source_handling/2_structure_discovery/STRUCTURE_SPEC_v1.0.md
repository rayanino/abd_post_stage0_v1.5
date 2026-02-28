# Stage 2: Structure Discovery — Specification v1.0

**Status:** Active
**Date:** 2026-02-26
**Supersedes:** STRUCTURE_SPEC.md (draft)
**Precision level:** High — every rule is deterministic or has a defined tier of certainty with a fallback.
**Dependencies:** Stage 0 (Intake) + Stage 1 (Normalization) must be complete.

---

## 1. Purpose

Discover the book's internal structural divisions and define passage boundaries. A **passage** is the unit of work for Stages 3–4 (atomization and excerpting). This stage transforms a flat sequence of normalized pages into a hierarchical tree of divisions, then cuts that tree into passage-sized units.

**This stage is book-agnostic.** The algorithm operates on Shamela HTML structure (one universal template, validated across 788 files) and Arabic structural vocabulary. No rule is specific to any single book.

---

## 2. Input

| Input | Source | Purpose |
|-------|--------|---------|
| Frozen source HTML | Stage 0 (`books/{book_id}/source/`) or corpus (`books/Other Books/`) | Pass 1: HTML-tagged heading extraction |
| `{book_id}_normalized.jsonl` | Stage 1 output | Pass 2: keyword scan of normalized matn_text |
| `{book_id}_normalization_report.json` | Stage 1 output | Sanity checks (page count, footnote stats) |
| `intake_metadata.json` | Stage 0 output | Book metadata, science classification, source file paths |
| `structural_patterns.yaml` | Shipped with app (in `2_structure_discovery/`) | Keyword vocabulary, hierarchy rules, ordinal patterns |

For multi-volume books, the frozen HTML consists of multiple files (`001.htm`, `002.htm`, ...) and Stage 1 JSONL spans all volumes with monotonic `seq_index`.

---

## 3. Four-Tier Certainty Architecture

Every structural decision belongs to exactly one tier. No decision is a guess.

| Tier | Source | Confidence | Action |
|------|--------|------------|--------|
| **Tier 1** | Pass 1: HTML-tagged headings | `confirmed` | Automatically accepted |
| **Tier 2** | Pass 2: Strict keyword heuristics | `high` or `medium` | Automatically accepted; LLM may refine in Pass 3 |
| **Tier 3** | Pass 3: LLM semantic judgment | `high`, `medium`, or `low` | `low` items flagged for human review |
| **Tier 4** | Human review gate | Override | Human confirms/rejects/modifies flagged items |

---

## 4. Pass 1: HTML-Tagged Headings (Deterministic, Tier 1)

### 4.1 Input

Raw frozen HTML from Stage 0. NOT from `pages.jsonl` (Stage 1 strips tags).

### 4.2 Method

Extract all `<span class="title">` elements (double-quote attribute style). This is the content heading marker, validated as 100% reliable across 788 files, 168K+ pages.

**Critical differentiator (corpus-validated invariant):**
- `class='title'` (single quotes) → metadata labels → SKIP (Stage 0 uses these)
- `class="title"` (double quotes) → content headings → EXTRACT (Stage 2 uses these)

### 4.3 Rules

**R1.1 — Skip metadata page.** The first `<div class='PageText'>` contains metadata labels (القسم, المؤلف, etc.), not content headings. Skip all spans in this div.

**R1.2 — Extract heading text.** For each `<span class="title">...</span>`:
1. Remove nested HTML tags (`<font>`, etc.)
2. Remove `&nbsp;` (non-breaking space)
3. Remove `&#8204;` (ZWNJ, zero-width non-joiner)
4. Collapse multiple whitespace to single space
5. Strip leading/trailing whitespace
6. Result is the heading title text.

**R1.3 — Associate with page.** For each heading, find the nearest preceding `<span class='PageNumber'>(ص: N)</span>` where N is in Arabic-Indic digits. Convert N to integer. If no preceding page number exists (very rare), assign page 1 with a warning.

**R1.4 — Associate with seq_index.** Map the (volume, page_number_int) to the corresponding `seq_index` from the Stage 1 JSONL. For multi-volume books, the volume is derived from the HTML file being processed.

**R1.5 — Detect TOC headings.** If a heading's text matches a TOC keyword (فهرس, فهرس الموضوعات, المحتويات), mark its page as a TOC page. Do not create a division from TOC page content headings — they reference other divisions, not define new ones.

### 4.4 Output

A list of tagged heading records:
```
{title, page_number_int, volume, seq_index, detection_method: "html_tagged", confidence: "confirmed"}
```

### 4.5 Known coverage

From corpus surveys: Pass 1 reliably captures باب (68% tagged), مبحث (62% tagged), مطلب (94% tagged), خاتمة (66% tagged). It captures almost nothing for حاشية (0% tagged), شرح (1% tagged), قاعدة (0% tagged), فائدة (16% tagged), تنبيه (20% tagged).

---

## 5. Pass 1.5: TOC Parsing (Deterministic)

### 5.1 Trigger

Runs only if Pass 1 detected a TOC page (R1.5).

### 5.2 Method

Parse each line on TOC pages for the dot-leader pattern:

```
TITLE_TEXT [.·…]{3,} PAGE_NUMBER
```

Where PAGE_NUMBER is Arabic-Indic digits (٠-٩) or Western digits (0-9) at the end of the line.

### 5.3 Rules

**R1.5.1 — Extract TOC entries.** For each dot-leader line:
1. Split at the dot/ellipsis run
2. Left side = division title (strip whitespace)
3. Right side = page number (parse as integer)
4. If indentation is present (leading whitespace), record indent level (heuristic for hierarchy)

**R1.5.2 — Multi-page TOC.** If TOC content spans multiple pages, concatenate all TOC-page lines.

**R1.5.3 — TOC is a cross-reference, not a source.** TOC entries do NOT create divisions directly. They are stored for cross-referencing against Pass 1/2/3 results to detect missed headings and false positives.

### 5.4 Output

A list of TOC entry records:
```
{title, page_number, indent_level}
```

---

## 6. Pass 2: Keyword Heuristic Detection (Deterministic, Tier 2)

### 6.1 Input

Stage 1 `pages.jsonl` — specifically the `matn_text` field of each page.

### 6.2 Principle

Pass 2 is CONSERVATIVE. Its job is to find headings it can be certain about — not to find all headings. False positives are far more damaging than false negatives (which Pass 3 will catch).

### 6.3 Line extraction

For each page in `pages.jsonl`, split `matn_text` into lines (by `\n`). Each line is evaluated independently.

### 6.4 Heading candidate identification

A line is a **heading candidate** if and only if ALL of the following conditions hold:

**C1 — Keyword at line start.** The line begins with a keyword from `structural_patterns.yaml` in its citation form. The keyword match must be followed by a word boundary (space, colon, dash, end of line). This prevents matching فصل inside فصلاً or باب inside بابًا.

**C2 — Not a TOC entry.** The line does NOT contain a dot-leader pattern (`\.{3,}` or `…{3,}` or `\.·` sequences) followed by digits.

**C3 — Not inside footnote text.** The page's `footnote_section_format` is checked; if the line appears in footnote content (below the footnote separator), it is excluded. In practice, Stage 1 separates matn from footnotes, so this is about checking the field correctly.

**C4 — Not a citation.** The line does NOT match a citation pattern. A line is a citation if the 40 characters preceding the keyword contain any of: `قال في`, `ذكر في`, `كما في`, `انظر`, `ارجع إلى`, `راجع`, `في كتاب`, `في باب` (where the keyword is the object of the preposition, not the start of a new section).

Note: Since we are checking lines, C4 applies only to lines where the keyword appears after position 0. If the keyword is at position 0, C4 does not apply.

**C5 — Structural pattern match.** The line matches one of the following structural patterns:

| Pattern | Description | Max line length | Confidence |
|---------|-------------|-----------------|------------|
| `KEYWORD ORDINAL: TITLE` | Keyword + Arabic ordinal + separator + title | 120 chars | `high` |
| `KEYWORD ORDINAL` | Keyword + Arabic ordinal, no title | 60 chars | `high` |
| `KEYWORD في TITLE` or `KEYWORD: TITLE` | Keyword + preposition/colon + title | 100 chars | `medium` |
| `KEYWORD` alone | Standalone keyword on its own line | 30 chars | `medium` |
| `KEYWORD - CONTENT` or `KEYWORD: CONTENT` | Inline heading: keyword + separator + running text | 400 chars | `medium` |

For the inline pattern (last row): the heading title is the text from the keyword up to and including the separator. The content after the separator belongs to the division body. Record `inline_heading: true` and `heading_text_boundary` = character offset of the separator.

**C6 — Length filter.** The line length must not exceed the maximum specified in the pattern table above. Lines longer than the max for their matched pattern are rejected.

### 6.5 Ordinal recognition

Arabic ordinals are recognized from the list in `structural_patterns.yaml`. Both modern (الثاني) and classical (الثانى) orthography are accepted. The ordinal pattern is:

```
ال + ORDINAL_WORD
```

Where ORDINAL_WORD is one of: أوَّل/أول, ثاني/ثانى, ثالث, رابع, خامس, سادس, سابع, ثامن, تاسع, عاشر, حادي عشر/حادى عشر, ثاني عشر/ثانى عشر, ثالث عشر, ... (see `structural_patterns.yaml` for full list).

### 6.6 Deduplication with Pass 1

After collecting all Pass 2 candidates, remove any that match a Pass 1 heading on the same `seq_index` with similar text (fuzzy match: normalize Arabic, ignore diacritics, compare first 30 characters). Pass 1 already found these — do not double-count.

### 6.7 Output

New heading candidates not already found by Pass 1:
```
{title, seq_index, page_hint, detection_method: "keyword_heuristic", confidence, keyword_type, ordinal, inline_heading, heading_text_boundary}
```

---

## 7. Pass 3: LLM-Assisted Discovery (Tier 3)

### 7.1 Purpose

Fill gaps that Passes 1–2 missed. The LLM handles:
1. **Gap detection:** Implicit topic transitions with no keyword.
2. **False positive correction:** Flag Pass 1/2 candidates that are not real divisions.
3. **Hierarchy assignment:** Determine parent-child relationships between all divisions.
4. **Digestibility classification:** Mark each division as digestible / non-digestible / uncertain.
5. **TOC cross-reference:** Compare discovered divisions against TOC (if available).

### 7.2 Chunking strategy (book-agnostic)

The LLM cannot process an entire large book in one call. The chunking strategy is:

**Step 3a — Macro structure (one call).**
Input: book metadata + full Pass 1/2 heading list + TOC entries (if available) + the first 200 characters of content after each heading (for context).
Task: establish the top-level hierarchy, confirm/reject each Pass 1/2 heading, classify digestibility for top-level divisions, identify major structural gaps.
Output: confirmed/rejected/modified headings, hierarchy assignments, new top-level divisions.

**Step 3b — Per-division deep scan (one call per macro division >5 pages).**
Input: the full `matn_text` of one macro division (or a window of pages if no macro structure exists) + the heading list for that section + relevant Pass 1/2 candidates.
Task: find sub-divisions within this section, detect implicit topic transitions, classify digestibility for sub-divisions.
Output: new sub-divisions, refined hierarchy within this section.

**For books with no structure (zero Pass 1/2 headings):**
Process in fixed-size windows of 15–20 pages, overlapping by 2 pages. Each call includes the running state of discovered divisions from previous windows.

**For small books (<50 pages):**
Send the entire text in Step 3a. Skip Step 3b.

### 7.3 LLM prompt contract

Prompts are versioned and stored in `2_structure_discovery/prompts/`. Each prompt must include:

1. **Role definition:** "You are analyzing the structure of a classical Arabic book."
2. **Task specification:** Precisely which of the 5 tasks (§7.1) this call handles.
3. **Input data:** headings list, text content, TOC if available.
4. **Structural keyword vocabulary:** from `structural_patterns.yaml`.
5. **Hierarchy rules:** known patterns (باب>فصل>مبحث, باب>تقسيم) with explicit warning that hierarchy is book-specific.
6. **Digestibility rules:** precise criteria (§8).
7. **Output format:** strict JSON schema that the tool validates.
8. **Confidence instructions:** "If uncertain whether something is a division, include it with confidence='low'. Do not omit uncertain items."

### 7.4 LLM output validation (deterministic post-processing)

After each LLM call, the tool validates:
- Output parses as valid JSON
- Each division record has required fields
- `seq_index` values exist in the book's page range
- No duplicate division IDs
- Parent references point to existing divisions
- Child page ranges are contained within parent page ranges

On validation failure: auto-retry with error feedback (up to 3 retries). If still failing, log the error and proceed with what was valid. Flag the section for human review.

### 7.5 Hierarchy construction (deterministic, post-LLM)

After all Pass 3 calls complete, build the final tree:

1. Start with the LLM's hierarchy assignment from Step 3a.
2. Integrate sub-divisions from Step 3b calls.
3. Validate ordinal sequence continuity: siblings with the same keyword must have sequential ordinals.
4. Validate page containment: child `[start_seq_index, end_seq_index]` must be within parent range.
5. Cross-reference with TOC indentation if available: TOC indent levels should be consistent with tree depth.
6. Flag inconsistencies (e.g., ordinal gap, containment violation) with `review_flags`.

### 7.6 Output

Updated division list with:
- All Pass 1/2 candidates confirmed, rejected, or modified
- New LLM-discovered divisions
- Hierarchy assignments (parent_id for every division)
- Digestibility classifications
- Confidence levels for every division

---

## 8. Digestibility Rules

A division's digestibility is determined by the following rules, applied in order:

| Condition | Classification | Confidence |
|-----------|---------------|------------|
| Division type is `فهرس` or `المحتويات` | `false` | Deterministic |
| Division type is `تقاريظ` | `false` | Deterministic |
| Division title contains `مقدمة المحقق` or `مقدمة المعلق` or `كلمة المحقق` | `false` | Deterministic |
| Division title contains `خطبة الكتاب` | `false` | Deterministic |
| Division type is `تمارين` or `تطبيق` or `مسائل التمرين` or `أسئلة` | `true` (exercise) | Deterministic |
| Division title is `مقدمة` or `مقدمة الكتاب` or `المقدمة` (author's intro) | `uncertain` | Needs LLM or human |
| All other divisions | LLM classifies | Tier 3 |

For `uncertain` divisions: the LLM evaluates whether the content contains substantive definitions or teaching content (→ `true`) or purely rhetorical praise and biographical information (→ `false`). If the LLM cannot decide, it remains `uncertain` and is flagged for human review.

---

## 9. Passage Construction

Once the division tree is built and reviewed, passages are cut from it.

### 9.1 Core rule

**A passage corresponds to one leaf-level digestible division.**

- If a division has children → NOT a passage (its children are).
- If a division has no children AND `digestible == "true"` → IS a passage.
- If a division has no children AND `digestible == "false"` → SKIPPED.
- If a division has no children AND `digestible == "uncertain"` → flagged for human review; tentatively treated as a passage.

### 9.2 Sizing rules (deterministic)

| Condition | Action | Flag |
|-----------|--------|------|
| Leaf division is 2–15 pages | Standard passage. No action needed. | None |
| Leaf division is 16–20 pages | Acceptable but noted. | None |
| Leaf division is 21–30 pages | Flag for review. | `long_passage` |
| Leaf division is >30 pages | Attempt LLM split (§9.4). If LLM finds no split point, keep as single passage. | `long_passage` |
| Leaf division is <1 page | Attempt merge with adjacent sibling (§9.3). If no merge possible, keep as standalone. | `short_passage` |
| Leaf division is 1–2 pages | Acceptable as standalone. | None |

### 9.3 Merge rules

A short division (<1 page) is merged according to:

| Situation | Rule |
|-----------|------|
| تنبيه / فرع / فائدة < 1 page, has an adjacent sibling | Merge into adjacent sibling passage if combined ≤ 15 pages |
| خاتمة at end of a باب | Merge into the last passage of that باب |
| Standalone heading with no content | Merge into next division |
| Multiple tiny siblings (<1 page each) under same parent | Merge together if combined ≤ 15 pages |

**Merge produces a passage with `sizing_action: "merged"` and `merge_info` recording what was combined.**

### 9.4 Split rules

A long division is split when:

| Situation | Rule |
|-----------|------|
| LLM identifies internal topic boundaries | Split at those boundaries. Each segment becomes a passage. `sizing_action: "split"`. |
| No internal boundaries found but >30 pages | Split at natural paragraph breaks, targeting ~10 pages per passage. `split_method: "fixed_size"`. |
| Exercise section >15 pages | Split into groups of ~10 pages. |

### 9.5 Never-merge constraints

| Constraint | Reason |
|------------|--------|
| Never merge across different top-level divisions (باب, كتاب) | Sovereign topic boundaries |
| Never merge across different علم sections in multi-science books | Science boundary |
| Never merge مقدمة with content chapters | Different function |
| Never merge exercise divisions with teaching divisions | Different excerpt roles |

### 9.6 Never-split constraints

| Constraint | Reason |
|------------|--------|
| Never split an exercise set that refers to the same examples | Breaks cross-references |
| Never split a proof/argument mid-reasoning (if detectable) | Destroys logical coherence |
| Never split a verse + its commentary if combined < 5 pages | Bonded content |

### 9.7 Passage ID assignment

Passages are numbered sequentially in document order: `P001`, `P002`, ..., `P999`. Zero-padded to 3 digits (or more for very large books).

### 9.8 Passage linking

Each passage records `predecessor_passage_id` and `successor_passage_id` to allow downstream stages to navigate passage order without re-reading the division tree.

---

## 10. Output Artifacts

### 10.1 `{book_id}_divisions.json`

Complete division tree. Schema: `schemas/divisions_schema_v0.1.json`.

### 10.2 `{book_id}_passages.jsonl`

One passage per line. Schema: `schemas/passages_schema_v0.1.json`.

### 10.3 `{book_id}_structure_report.json`

Summary statistics and flags. Schema: `schemas/structure_report_schema_v0.1.json`.

### 10.4 `{book_id}_structure_review.md`

Human-readable Markdown showing:
- The full division tree with page numbers and confidence indicators
- Passage assignments with sizing actions
- All flagged items highlighted for review
- TOC cross-reference results (if applicable)

This file is a derived view (regeneratable from divisions.json + passages.jsonl).

### 10.5 `{book_id}_structure_overrides.json`

Initially empty. Populated by the human reviewer after reading `structure_review.md`. Format:

```json
{
  "overrides": [
    {
      "item_type": "division",
      "item_id": "div_0012",
      "action": "rejected",
      "notes": "This is not a real heading, it's part of a quotation."
    },
    {
      "item_type": "passage",
      "item_id": "P003",
      "action": "split",
      "split_at_seq_index": 45,
      "notes": "Topic clearly changes at page 45."
    }
  ]
}
```

The tool can re-run with `--apply-overrides {book_id}_structure_overrides.json` to produce updated output.

---

## 11. Human Review Gate

After Stage 2 produces output, the human reviews `structure_review.md` and:
1. Confirms or rejects flagged divisions (low confidence, uncertain digestibility)
2. Approves or adjusts passage boundaries
3. Records decisions in `{book_id}_structure_overrides.json`

The review is a SKIM, not a detailed audit. The review file highlights only items that need human attention.

---

## 12. Multi-Volume Books

For multi-volume books:
- Each volume file is processed independently in Pass 1.
- Pass 1 headings are tagged with the volume number.
- The division tree may include `type: "volume"` nodes at level 1 if the book's volumes are explicit structural divisions.
- `seq_index` from Stage 1 provides a monotonic, cross-volume page reference.
- Passages never cross volume boundaries (added to never-merge constraints).

---

## 13. Multi-Science Books

For books with `book_category: "multi_science"` (e.g., مفتاح العلوم):
- The `science_parts` field in `intake_metadata.json` lists which sections correspond to which science.
- Top-level divisions are annotated with `science_id`.
- Passages inherit their `science_id` from their ancestor division.
- Never-merge constraint: never merge across science boundaries.

---

## 14. Edge Cases

→ See `edge_cases.md` in this folder (updated alongside this spec).

---

## 15. Resolved Open Questions

| # | Question | Resolution |
|---|----------|------------|
| 1 | LLM prompt design for Pass 3 | Chunked approach: macro structure call + per-division deep scans. Prompts versioned in `prompts/`. See §7. |
| 2 | TOC parsing specifics | Dot-leader pattern extraction with indent-level tracking. See §5. |
| 3 | Multi-volume structure | Each volume optionally a level-1 node. seq_index handles cross-volume references. See §12. |
| 4 | Books with no structure | Fixed-size windowed LLM scans. `structure_confidence: "minimal"`. See §7.2. |
| 5 | Editor-inserted divisions | Detected by bracket patterns. Tagged `editor_inserted: true`. Still used as divisions. |
| 6 | Confidence threshold | All divisions above `low` are automatically accepted. `low` items are included but flagged for human review. See §3. |
