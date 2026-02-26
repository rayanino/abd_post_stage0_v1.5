# Pass 3b — Deep Division Scan

You are analyzing a single section of a classical Arabic scholarly book to find internal sub-divisions that earlier passes missed.

## Section Information

- **Book:** {{book_title}} ({{book_science}})
- **Section title:** {{section_title}}
- **Section type:** {{section_type}}
- **Page range:** {{page_range}} ({{page_count}} pages)
- **Known sub-headings in this section:** {{known_subheadings_count}}

## Known Sub-Headings

These headings were already found within this section:

```json
{{known_subheadings_json}}
```

## Full Text of This Section

{{section_text}}

## Your Tasks

### Task 1: Find missed sub-divisions

Look for structural boundaries within this section that the deterministic passes missed:

1. **Keyword-based headings** that were embedded inline (e.g., `تنبيه - يتصرف الماضى...` where the keyword is followed by content on the same line)
2. **Implicit topic transitions** where the subject matter clearly changes but there is no keyword marker
3. **Enumerated items** that function as sub-sections (e.g., `الأول:`, `الثاني:` without a preceding keyword like مبحث)

### Task 2: Classify digestibility of sub-sections

For each sub-division (existing and new), classify:
- **true** — teaching content suitable for knowledge extraction
- **false** — non-content (exercise answers, editor notes, etc.)
- **uncertain** — needs human review

### Task 3: Identify content types

Classify each sub-division:
- **teaching** — definitions, explanations, rules, examples
- **exercise** — practice problems, تطبيق, أسئلة
- **mixed** — both teaching and exercise content

## Output Format

Respond with ONLY a JSON object (no markdown fences, no preamble):

```
{
  "new_subdivisions": [
    {
      "title": "تنبيه في حكم الأفعال",
      "type": "تنبيه",
      "start_line_hint": "تنبيه - يتصرف الماضى",
      "approximate_seq_index": 26,
      "confidence": "high",
      "digestible": "true",
      "content_type": "teaching",
      "inline_heading": true,
      "notes": "Inline heading at start of paragraph"
    }
  ],
  "existing_refinements": [
    {
      "known_index": 0,
      "digestible": "true",
      "content_type": "teaching",
      "notes": "Confirmed as teaching content"
    }
  ],
  "section_assessment": "Brief assessment of this section's internal structure"
}
```

Rules:
- `start_line_hint` is the first ~30 characters of the line where the sub-division starts
- `approximate_seq_index` is the page seq_index where the sub-division begins
- `known_index` refers to the zero-based index in the known_subheadings list
- If uncertain, include with confidence="low". Do NOT omit uncertain items.
- Only report genuinely new structural boundaries, not every paragraph break
