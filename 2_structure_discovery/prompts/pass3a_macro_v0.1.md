# Pass 3a — Macro Structure Discovery

You are analyzing the structure of a classical Arabic scholarly book exported from the Shamela digital library. Your task is to establish the book's top-level hierarchy, confirm or reject heading candidates from earlier passes, and classify each division's digestibility.

## Book Information

- **Title:** {{book_title}}
- **Author:** {{book_author}}
- **Science:** {{book_science}}
- **Total pages:** {{total_pages}}
- **Total heading candidates (from Passes 1-2):** {{candidate_count}}

## Heading Candidates

The following headings were found by deterministic passes. Each has a detection method and confidence level:
- `html_tagged / confirmed` — found in HTML markup (very reliable)
- `keyword_heuristic / high` — keyword + ordinal pattern match
- `keyword_heuristic / medium` — keyword pattern match

```json
{{candidates_json}}
```

{{#if toc_entries}}
## Table of Contents

The book has a table of contents with these entries:

```json
{{toc_entries_json}}
```
{{/if}}

## Context Samples

For each candidate heading, here is the first ~200 characters of content following it:

{{context_samples}}

## Your Tasks

### Task 1: Confirm or reject each candidate

For each heading in the candidates list, decide:
- **confirm** — this is a real structural division
- **reject** — this is NOT a real heading (e.g., the keyword appears in running text, a citation, or a quotation)
- **modify** — the heading is real but the title or type should be adjusted

### Task 2: Identify the hierarchy

Assign a `level` (depth) and `parent_ref` (reference to the parent heading's index) for each confirmed heading. Level 1 = top-level divisions. The root is implicit.

Known hierarchy patterns in Arabic scholarly texts (book-specific — verify against the actual content):
- باب > فصل > مبحث (common)
- باب > تقسيم > باب (in morphology texts — same keyword at different levels!)
- كتاب > باب > فصل (in comprehensive works)

The same keyword can appear at different hierarchy levels within the same book. Use the content and ordinal sequences to determine the actual hierarchy.

### Task 3: Identify major gaps

Are there structural divisions between the candidates that were missed? Look for:
- Topic transitions with no heading keyword
- Sections that the TOC mentions but no candidate covers
- Unnumbered sub-sections within large divisions

For each gap, provide the approximate page location and a suggested title.

### Task 4: Classify digestibility

For each confirmed division, classify:
- **true** — contains teaching content, definitions, explanations, examples, or exercises suitable for knowledge extraction
- **false** — contains non-content material: editor's introduction (مقدمة المحقق), table of contents (فهرس), endorsements (تقاريظ), bibliography, publisher notes
- **uncertain** — could be either (e.g., author's مقدمة that may contain both praise and substantive definitions)

## Output Format

Respond with ONLY a JSON object (no markdown fences, no preamble):

```
{
  "decisions": [
    {
      "candidate_index": 0,
      "action": "confirm",
      "level": 1,
      "parent_ref": null,
      "digestible": "true",
      "content_type": "teaching",
      "notes": "Clear top-level division with ordinal sequence"
    }
  ],
  "new_divisions": [
    {
      "title": "مقدمة المؤلف",
      "type": "مقدمة",
      "approximate_seq_index": 5,
      "level": 1,
      "parent_ref": null,
      "digestible": "uncertain",
      "content_type": null,
      "confidence": "medium",
      "notes": "Author introduction before first باب, not covered by any candidate"
    }
  ],
  "structure_notes": "Brief overall assessment of the book's structure"
}
```

Rules:
- `candidate_index` refers to the zero-based index in the candidates list
- `parent_ref` is the `candidate_index` of the parent heading, or null for top-level divisions
- For `new_divisions`, `parent_ref` can reference either a candidate_index or another new_division by using "new_N" format (e.g., "new_0" for the first new division)
- If uncertain about a decision, include it with confidence="low" and explain in notes. Do NOT omit uncertain items.
- Every candidate must have a decision (confirm, reject, or modify)
