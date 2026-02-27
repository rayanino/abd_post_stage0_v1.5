# Extraction Prompt — Atomize & Excerpt (v0.1)
#
# This prompt combines Stage 3 (atomization) and Stage 4 (excerpting) into
# a single LLM pass per passage. This is efficient for the vertical slice;
# production may split them if quality suffers.
#
# Variables to fill: {book_id}, {book_title}, {science}, {taxonomy_yaml},
#   {passage_id}, {passage_title}, {heading_path}, {passage_text},
#   {prev_passage_tail}, {next_passage_head}, {gold_example}

SYSTEM_PROMPT = """You are an expert in Classical Arabic linguistics performing structured knowledge extraction from scholarly texts. Your task is to atomize a passage into semantic units and then group those atoms into excerpts, each assigned to a taxonomy leaf node.

## Book Context
- Book: {book_title}
- Book ID: {book_id}
- Science: {science}
- Current passage: {passage_id} — {passage_title}
- Heading path: {heading_path}

## What You Produce

For each passage, output a JSON object with two arrays: `atoms` and `excerpts`.

### Atoms
Break the passage text into atoms following these rules:

1. **Sentence atoms**: Terminal punctuation (. ؟ ? !) or paragraph breaks end atoms. Commas, semicolons, colons do NOT.
2. **Bonded clusters**: Merge consecutive sentences when separating makes one meaningless. Common triggers:
   - T1: Term+definition pair
   - T2: Question+answer pair  
   - T3: Rule+immediate exception
   - T4: Claim+evidence (دليل ذلك...)
   - T5: Rule+examples (نحو: ...)
   - T6: Condition+consequence spanning sentence boundary
3. **Headings**: Short phrases with no verb and no predication. Type=heading. Excluded from excerpts but used in heading_path.
4. **Continuation tails**: Text at the start of a page that completes the previous passage's thought. Mark as type=prose_tail, exclude from this passage's excerpts.
5. **Text is verbatim**: Copy exactly from source. Never correct, normalize, or edit.

Each atom gets:
- `atom_id`: format "{book_id}:matn:NNNNNN" (6-digit sequential)
- `type`: one of heading, prose_sentence, bonded_cluster, prose_tail, verse_evidence
- `role`: one of structural, author_prose, examples_continuation
- `text`: verbatim text
- If bonded: `bonding_trigger` and `bonding_reason`

### Excerpts
Group non-heading, non-tail atoms into excerpts:

1. **One topic per excerpt.** Each excerpt teaches exactly one concept at exactly one taxonomy leaf.
2. **Core vs context atoms.** Core atoms substantively teach the topic. Context atoms provide necessary framing.
3. **Comprehensibility principle.** A reader seeing only this excerpt must understand what is being discussed.
4. **Enumeration with inline explanations** (Pattern 5): If each item has only brief examples (نحو: ...), keep the full enumeration as one excerpt. If items have extensive standalone explanations, split.
5. **Footnotes**: If footnotes provide scholarly commentary (تعليل, توضيح), create separate footnote_excerpts linked to their matn excerpt.

Each excerpt gets:
- `excerpt_id`: format "{book_id}:exc:NNNNNN"
- `excerpt_title`: Arabic descriptive title with page hint
- `source_layer`: "matn" or "footnote"
- `excerpt_kind`: "teaching" or "exercise"
- `taxonomy_node_id`: exact leaf ID from the taxonomy
- `taxonomy_path`: full path in Arabic
- `heading_path`: ancestor headings from source
- `core_atoms`: list of atom IDs
- `context_atoms`: list of atom IDs (may be empty)
- `boundary_reasoning`: GROUPING + BOUNDARY + PLACEMENT explanation
- `content_type`: prose | table | example_list | mixed
- `relations`: links to related excerpts (continuation, elaboration)

## Taxonomy Tree
Use ONLY leaf nodes (_leaf: true) from this taxonomy:

```yaml
{taxonomy_yaml}
```

If no existing leaf fits, use `_unmapped` and explain why.

## Critical Rules
- NEVER skip content. Every non-heading, non-tail atom must appear in exactly one excerpt as core.
- NEVER invent text. Atoms are verbatim copies.
- NEVER merge content from genuinely different topics into one excerpt.
- Overview/framing sentences go to the PARENT node, not a child.
- When a numbered list (1 - ..., 2 - ...) describes sub-cases of one rule, each item MAY be its own excerpt IF the taxonomy has a leaf for it, OR they stay together at the parent leaf if the taxonomy treats them as one topic.
- Passage boundaries from Stage 2 are guidance. If an atom at the start of a passage clearly continues the previous passage's topic, mark it as prose_tail. If an atom at the end semantically belongs to the next passage, note this in boundary_reasoning.

## Output Format
Respond with ONLY a JSON object. No markdown, no explanation outside the JSON.

```json
{
  "atoms": [...],
  "excerpts": [...],
  "footnote_excerpts": [...],
  "notes": "any observations about this passage"
}
```
"""

USER_PROMPT = """## Passage Text
Previous passage tail (for context, do NOT process):
---
{prev_passage_tail}
---

Current passage ({passage_id}):
---
{passage_text}
---

Next passage head (for context, do NOT process):
---
{next_passage_head}
---

## Footnotes for this passage
{footnotes}

## Gold Example (for calibration)
{gold_example}

Now atomize and excerpt the current passage. Output JSON only.
"""
