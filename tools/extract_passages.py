#!/usr/bin/env python3
"""
Stage 3+4 Extraction Tool — Vertical Slice
============================================
Combines atomization (Stage 3) and excerpting (Stage 4) into a single
LLM pass per passage. Takes Stage 2 output (passages + normalized pages)
and produces structured excerpts ready for taxonomy placement.

Usage:
    python tools/extract_passages.py \
        --passages /tmp/imlaa_stage2_v3/qawaid_imlaa_passages.jsonl \
        --pages /tmp/imlaa_full.jsonl \
        --taxonomy taxonomy/imlaa_v0.1.yaml \
        --book-id qimlaa \
        --book-title "قواعد الإملاء" \
        --science imlaa \
        --gold 3_extraction/gold/P004_gold_excerpt.json \
        --output-dir /tmp/imlaa_extraction \
        --api-key sk-ant-... \
        [--passage-ids P004,P005]  # optional: only process these
        [--model claude-sonnet-4-5-20250929]
        [--dry-run]  # show prompts without calling API
"""

import argparse
import json
import os
import re
import sys
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Model provider registry (OpenRouter uses OpenAI-compatible format for all)
# ---------------------------------------------------------------------------

MODEL_PRICING = {
    # (input_per_1M, output_per_1M) in USD
    # Anthropic via OpenRouter
    "anthropic/claude-sonnet-4-5-20250929": (3.0, 15.0),
    "anthropic/claude-sonnet-4-20250514": (3.0, 15.0),
    "anthropic/claude-opus-4-20250514": (15.0, 75.0),
    # OpenAI via OpenRouter
    "openai/gpt-4o": (2.5, 10.0),
    "openai/gpt-4o-2024-08-06": (2.5, 10.0),
    "openai/gpt-4.1": (2.0, 8.0),
    "openai/gpt-4.1-mini": (0.4, 1.6),
    # Direct Anthropic (legacy single-model mode)
    "claude-sonnet-4-5-20250929": (3.0, 15.0),
    "claude-sonnet-4-20250514": (3.0, 15.0),
}


def get_model_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost from token counts using MODEL_PRICING."""
    in_rate, out_rate = MODEL_PRICING.get(model, (3.0, 15.0))
    return input_tokens * in_rate / 1_000_000 + output_tokens * out_rate / 1_000_000


def _model_short(model: str) -> str:
    """Short name for filenames (max 25 chars, filesystem-safe)."""
    short = model.replace("/", "_").replace("-", "").replace(".", "")
    return short[:25]


# ---------------------------------------------------------------------------
# Constants — enum values from gold_standard_schema_v0.3.3.json
# ---------------------------------------------------------------------------

VALID_ATOM_TYPES = {"heading", "prose_sentence", "bonded_cluster",
                    "verse_evidence", "quran_quote_standalone", "list_item"}
VALID_TRIGGER_IDS = {"T1", "T2", "T3", "T4", "T5", "T6"}
VALID_CORE_ROLES = {"author_prose", "evidence", "exercise_content",
                    "exercise_answer_content"}
VALID_CONTEXT_ROLES = {"preceding_setup", "classification_frame",
                       "back_reference", "cross_science_background"}
VALID_CASE_TYPES = {
    "A1_pure_definition", "A2_division_classification",
    "A3_rule_with_conditions", "A4_shahid_with_commentary",
    "A5_scholarly_dispute", "A6_historical_bibliographical",
    "B1_clean_boundary", "B2_gradual_transition", "B3_interwoven",
    "B4_multipage_continuous", "B5_comprehensibility_dependency",
    "B6_definition_with_exception",
    "C1_scholarly_footnote", "C2_exercise_section", "C3_qa_review",
    "C4_embedded_verse_evidence", "C5_inline_list_in_prose",
    "D1_clean_single_node", "D2_new_node_discovery", "D3_leaf_granulation",
    "D4_cross_science", "D5_parent_level_content",
    "E1_split_discussion", "E2_editor_note_scholarly",
}
VALID_RELATION_TYPES = {
    "footnote_supports", "footnote_explains", "footnote_citation_only",
    "footnote_source", "has_overview", "shared_shahid", "exercise_tests",
    "belongs_to_exercise_set", "answers_exercise_item",
    "split_continues_in", "split_continued_from",
    "interwoven_sibling", "cross_layer",
}
VALID_EXCERPT_KINDS = {"teaching", "exercise", "apparatus"}
VALID_SOURCE_LAYERS = {"matn", "footnote", "sharh", "hashiya", "tahqiq_3ilmi"}
VALID_EXCLUSION_REASONS = {
    "heading_structural", "footnote_apparatus",
    "khutba_devotional_apparatus", "non_scholarly_apparatus",
    "page_header_artifact", "decorative_separator",
    "publishing_metadata", "duplicate_content", "exercise_prompt_only",
}

ATOM_ID_RE = re.compile(r"^[a-z0-9_]+:[a-z0-9_]+:[0-9]{6}$")
EXCERPT_ID_RE = re.compile(r"^[a-z0-9_]+:exc:[0-9]{6}$")

# ---------------------------------------------------------------------------
# Prompt templates — rebuilt from binding decisions, checklists, and schema
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert in Classical Arabic linguistics performing structured knowledge extraction from scholarly texts. Your task is to atomize a passage into semantic units and then group those atoms into excerpts, each assigned to a taxonomy leaf node.

## Book Context
- Book: {book_title}
- Book ID: {book_id}
- Science: {science}
- Current passage: {passage_id} — {passage_title}
- Heading path: {heading_path}

## Output Overview

Produce a JSON object with these top-level keys:
- `atoms` — array of atom records
- `excerpts` — array of excerpt records
- `footnote_excerpts` — array of footnote excerpt records (may be empty)
- `exclusions` — array of exclusion records for headings and continuation tails
- `notes` — optional string with observations about the passage

---

## 1. ATOMIZATION RULES

Break the passage text into atoms — the smallest indivisible semantic units.

### 1.1 Atom Types (`atom_type` field)

| atom_type | Description |
|-----------|-------------|
| `heading` | Section/chapter marker. Short phrase, no main verb, no complete predication. Typically باب، فصل، مسألة، تنبيه، فائدة, or numbered section headers. EXCLUDED from excerpts; referenced only in heading_path. |
| `prose_sentence` | Single complete Arabic sentence ending at terminal punctuation (. ؟ ? !) or paragraph break. The default type. |
| `bonded_cluster` | Two or more consecutive sentences merged because separating them makes one meaningless. MUST have `bonded_cluster_trigger`. |
| `verse_evidence` | Poetry cited as evidence/illustration — full bayt, single hemistich, or verse fragment, standing alone (not embedded in prose). |
| `quran_quote_standalone` | Quranic text appearing as its own standalone atom (not embedded within prose). |
| `list_item` | Numbered or bulleted item in the author's enumeration, including its inline explanation. |

### 1.2 Atom Boundary Rules

- **ATOM.A1**: Terminal punctuation (`.` `؟` `?` `!`) and paragraph breaks END atoms. These are absolute boundaries.
- **ATOM.A2**: Non-terminal punctuation (`،` `,` `؛` `;` `:` em-dashes) NEVER end atoms alone.
- **ATOM.A3**: Text is verbatim. Copy character-for-character from the passage. Never correct spelling, alter diacritics, insert editorial text, or reorder.
- **ATOM.A8**: Every atom must have non-empty text.
- **ATOM.A9**: Conservative merge principle. When unsure whether to merge or keep separate, prefer merging. A wrongly-split atom is worse than a slightly large one.

### 1.3 Bonded Cluster Triggers

Every `bonded_cluster` atom MUST have a `bonded_cluster_trigger` object. Non-bonded atoms must NOT.

| trigger_id | Name | Pattern |
|-----------|------|---------|
| `T1` | failed_independent_predication | One sentence has no independent subject/predicate without the other. E.g., "والقاعدة مطّردة. دليل ذلك قوله تعالى: ..." |
| `T2` | unmatched_quotation_brackets | Quote opens in one sentence, closes in the next. |
| `T3` | colon_definition_leadin | Sentence ends with colon or leadin marker (like نحو:); next completes the definition/examples. E.g., "1 - أنْ تُسَكَّنَ... نحوُ: يأمُرُ، آخِر..." |
| `T4` | short_fragment | Fragment under 15 characters — cannot stand alone as meaningful unit. |
| `T5` | verse_coupling | Two hemistichs of the same bayt (بيت شعري). |
| `T6` | attribution_then_quote | Attribution formula ("قال الشاعر") followed by the quoted content. |

Format: `"bonded_cluster_trigger": {{"trigger_id": "T3", "reason": "Rule statement ends with نحو: and examples follow as completion"}}`

### 1.4 Prose Tail (Continuation) Handling

If text at the START of this passage clearly continues the previous passage's thought, type it according to its actual form (`prose_sentence` or `bonded_cluster`) but add `"is_prose_tail": true`. Prose tail atoms are EXCLUDED from this passage's excerpts.

### 1.5 Atom Fields

Each atom record:
```json
{{
  "atom_id": "{book_id}:matn:NNNNNN",
  "atom_type": "prose_sentence",
  "source_layer": "matn",
  "text": "verbatim Arabic text",
  "is_prose_tail": false,
  "bonded_cluster_trigger": null
}}
```
- `atom_id`: 6-digit sequential starting from {atom_start_seq}. Never resets between passages.
- `atom_type`: one of the types in 1.1 above.
- `source_layer`: "matn" for main text, "footnote" for footnote atoms.
- `text`: verbatim from source.
- `is_prose_tail`: true only for continuation text from previous passage.
- `bonded_cluster_trigger`: null unless atom_type is bonded_cluster.

---

## 2. EXCERPTING RULES

Group atoms into excerpts. Each excerpt teaches one topic at one taxonomy leaf.

### 2.1 One Topic Per Excerpt (EXC.B1)

Each excerpt addresses exactly one granulated subtopic and maps to exactly one taxonomy leaf node.

### 2.2 Core Atoms — Objects with Roles

Core atoms substantively teach the excerpt's topic. Format as objects:
```json
"core_atoms": [{{"atom_id": "...", "role": "author_prose"}}]
```

Core roles (from schema):
| Role | Description |
|------|-------------|
| `author_prose` | Author's own teaching text: definitions, explanations, transitions, commentary. The default. |
| `evidence` | Material cited by the author as proof: verse, hadith, quotation from another scholar. **SACRED RULE (EXC.C2): evidence is ALWAYS core, NEVER context.** |
| `exercise_content` | Material presented as exercise items for the reader to analyze. |
| `exercise_answer_content` | Scholarly judgment in a footnote identifying the answer to an exercise item. |

### 2.3 Context Atoms — Objects with Roles

Context atoms provide framing needed for comprehensibility but are NOT part of the core teaching. Format as objects:
```json
"context_atoms": [{{"atom_id": "...", "role": "preceding_setup"}}]
```

Context roles (from schema):
| Role | Description |
|------|-------------|
| `preceding_setup` | Earlier prose establishing the broader topic, needed for comprehensibility (e.g., a sentence whose pronoun the first core atom refers to). |
| `classification_frame` | Item from an overview enumeration that identifies which category this excerpt falls under. |
| `back_reference` | Author's explicit reference to a prior discussion (e.g., "كما تقدم في باب..."). |
| `cross_science_background` | Prerequisite concept from another science needed to understand this excerpt. |

**EXC.C4**: Wrong context is worse than missing context. If unsure, leave it out.

### 2.4 Heading Exclusion (ATOM.H4, EXC.B2)

Heading atoms must NEVER appear in core_atoms or context_atoms. They are metadata only, referenced in heading_path.

### 2.5 Layer Isolation (EXC.L1)

All core and context atoms in one excerpt must share the excerpt's `source_layer`. Cross-layer relationships use relations, never mixed atoms.

### 2.6 Comprehensibility Principle (EXC.B5)

An excerpt must be understandable in isolation. Include context atoms only when genuinely needed for a reader to grasp the teaching.

### 2.7 Topic Scope Guard (EXC.B7)

When excerpt at node X contains material about topic Y:
- **(A) Incidental mention/bridge**: Keep in core — it's part of X's teaching.
- **(B) Supportive dependency**: Put in context_atoms with appropriate role. Max 2 prose atoms or 1 bonded_cluster unless justified.
- **(C) Sovereign teaching of Y**: Split into a separate excerpt at Y's node.

### 2.8 case_types (Required, min 1)

Assign ALL applicable pattern labels. Categories:
- **A-series (content)**: A1_pure_definition, A2_division_classification, A3_rule_with_conditions, A4_shahid_with_commentary, A5_scholarly_dispute, A6_historical_bibliographical
- **B-series (boundary)**: B1_clean_boundary, B2_gradual_transition, B3_interwoven, B4_multipage_continuous, B5_comprehensibility_dependency, B6_definition_with_exception
- **C-series (special)**: C1_scholarly_footnote, C2_exercise_section, C3_qa_review, C4_embedded_verse_evidence, C5_inline_list_in_prose
- **D-series (taxonomy)**: D1_clean_single_node, D2_new_node_discovery, D3_leaf_granulation, D4_cross_science, D5_parent_level_content
- **E-series (cross-excerpt)**: E1_split_discussion, E2_editor_note_scholarly

### 2.9 Relations

Link related excerpts using typed relations:
```json
"relations": [{{"type": "has_overview", "target_excerpt_id": "...", "target_hint": null}}]
```
Relation types: footnote_supports, footnote_explains, footnote_citation_only, footnote_source, has_overview, shared_shahid, exercise_tests, belongs_to_exercise_set, answers_exercise_item, split_continues_in, split_continued_from, interwoven_sibling, cross_layer.

When the target excerpt does not exist yet (e.g., in a future passage), set `target_excerpt_id: null` and provide `target_hint`.

### 2.10 Excerpt Fields

```json
{{
  "excerpt_id": "{book_id}:exc:NNNNNN",
  "excerpt_title": "Arabic title (ص NN; matn NNNNNN)",
  "excerpt_title_reason": "How title was formed",
  "source_layer": "matn",
  "excerpt_kind": "teaching",
  "taxonomy_node_id": "leaf_id_from_taxonomy",
  "taxonomy_path": "إملاء > الهمزة > ...",
  "heading_path": ["heading atom texts in order"],
  "core_atoms": [{{"atom_id": "...", "role": "author_prose"}}],
  "context_atoms": [],
  "boundary_reasoning": "GROUPING: ... BOUNDARY: ... PLACEMENT: ...",
  "content_type": "prose",
  "case_types": ["A3_rule_with_conditions", "B1_clean_boundary", "D1_clean_single_node"],
  "relations": []
}}
```
- `excerpt_id`: 6-digit sequential starting from {excerpt_start_seq}.
- `excerpt_title`: Arabic descriptive title + source anchor (page, atom range).
- `boundary_reasoning`: Must explain GROUPING (why these atoms together), BOUNDARY (where excerpt starts/ends and why), PLACEMENT (why this taxonomy leaf).
- `content_type`: prose | table | example_list | mixed.

### 2.11 Footnote Excerpts

Scholarly footnotes (تعليل, توضيح, analysis) become separate footnote excerpts. Word glosses and simple إعراب are apparatus — exclude them.
```json
{{
  "excerpt_id": "{book_id}:exc:fn:NNNNNN",
  "excerpt_title": "Arabic title",
  "source_layer": "footnote",
  "excerpt_kind": "teaching",
  "taxonomy_node_id": "same_leaf_as_matn_excerpt",
  "taxonomy_path": "...",
  "linked_matn_excerpt": "matn_excerpt_id",
  "text": "full footnote text",
  "note": "optional context"
}}
```

### 2.12 Exclusion Records

For heading atoms and prose_tail atoms, output exclusion records:
```json
{{
  "atom_id": "...",
  "exclusion_reason": "heading_structural"
}}
```
Valid reasons: heading_structural, footnote_apparatus, khutba_devotional_apparatus, non_scholarly_apparatus.

---

## 3. TAXONOMY

Use ONLY leaf nodes (`_leaf: true`) from this taxonomy:
```yaml
{taxonomy_yaml}
```

**PLACE.P2**: Excerpts go to leaf nodes only, never branch nodes.
**PLACE.P3**: Overview/framing content for a branch goes to its `__overview` leaf, not child detail leaves.
**PLACE.P5**: If no existing leaf fits, set taxonomy_node_id to `"_unmapped"` and explain in boundary_reasoning.

---

## 4. CRITICAL RULES (violations cause rejection)

1. **NEVER skip content.** Every non-heading, non-prose_tail atom must appear in exactly one excerpt as core. (ATOM.E1)
2. **NEVER invent text.** Atoms are verbatim copies from the passage. (ATOM.A3)
3. **NEVER merge different topics** into one excerpt. (EXC.B6)
4. **NEVER put headings in excerpts.** Headings go in exclusions + heading_path only. (ATOM.H4)
5. **NEVER put evidence in context.** Verses/hadith/quotations cited as proof are always core. (EXC.C2)
6. **Overview/framing → `__overview` leaf**, not child leaves. (PLACE.P3)
7. **Passage boundaries are guidance.** If text at start continues previous passage, mark is_prose_tail=true. (ATOM.A5)
8. **Numbered lists**: Each item MAY be its own excerpt IF the taxonomy has a leaf for it, OR they stay together at the parent leaf.

## 5. OUTPUT FORMAT

Respond with ONLY a JSON object. No markdown fences, no commentary, no preamble.\
"""

USER_PROMPT = """\
## Passage Text

Previous passage tail (for context only — do NOT atomize or excerpt):
---
{prev_passage_tail}
---

Current passage ({passage_id}):
---
{passage_text}
---

Next passage head (for context only — do NOT atomize or excerpt):
---
{next_passage_head}
---

## Footnotes for this passage
{footnotes}

{gold_section}

Atomize and excerpt the current passage. Return a JSON object with keys: atoms, excerpts, footnote_excerpts, exclusions, notes.\
"""

CORRECTION_PROMPT = """\
Your previous extraction for {passage_id} had validation issues. Fix ONLY the listed problems and return the complete corrected JSON (all keys: atoms, excerpts, footnote_excerpts, exclusions, notes).

## Validation Issues Found
{issues_text}

## Your Previous Output
{previous_output}

## Key Rules Reminder
- Every non-heading, non-prose_tail atom must be core in exactly one excerpt.
- Heading atoms go in exclusions (reason=heading_structural) and heading_path, never in core/context.
- core_atoms entries must be objects: {{"atom_id": "...", "role": "author_prose|evidence|..."}}.
- context_atoms entries must be objects: {{"atom_id": "...", "role": "preceding_setup|..."}}.
- case_types must be a non-empty list of valid labels (A1-E2).
- bonded_cluster atoms must have bonded_cluster_trigger; others must not.

Return corrected JSON only. Do not change anything that was not flagged.\
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_taxonomy_yaml(path: str) -> str:
    """Load taxonomy YAML as raw text for prompt injection."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_gold_example(path: str | None) -> str:
    """Load gold example and format as few-shot section."""
    if not path or not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        gold = json.load(f)
    # Extract just the atoms and excerpts for the prompt
    compact = {
        "atoms": gold.get("atoms", []),
        "excerpts": gold.get("excerpts", []),
        "footnote_excerpts": gold.get("footnote_excerpts", []),
    }
    return json.dumps(compact, ensure_ascii=False, indent=2)


def get_passage_text(passage: dict, page_by_seq: dict) -> str:
    """Assemble passage text from pages."""
    parts = []
    for seq in range(passage["start_seq_index"], passage["end_seq_index"] + 1):
        pg = page_by_seq.get(seq)
        if pg:
            matn = pg.get("matn_text", "")
            if matn:
                parts.append(matn)
    return "\n\n".join(parts)


def get_passage_footnotes(passage: dict, page_by_seq: dict) -> str:
    """Collect footnotes from passage pages."""
    fns = []
    for seq in range(passage["start_seq_index"], passage["end_seq_index"] + 1):
        pg = page_by_seq.get(seq)
        if pg:
            for fn in pg.get("footnotes", []):
                num = fn.get("number", "?")
                text = fn.get("text", "")
                fns.append(f"[{num}] {text}")
    return "\n".join(fns) if fns else "(none)"


def get_context_tail(passages: list, idx: int, page_by_seq: dict, chars: int = 300) -> str:
    """Get the last N chars of the previous passage for context."""
    if idx == 0:
        return "(start of book)"
    prev = passages[idx - 1]
    text = get_passage_text(prev, page_by_seq)
    return text[-chars:] if len(text) > chars else text


def get_context_head(passages: list, idx: int, page_by_seq: dict, chars: int = 300) -> str:
    """Get the first N chars of the next passage for context."""
    if idx >= len(passages) - 1:
        return "(end of book)"
    nxt = passages[idx + 1]
    text = get_passage_text(nxt, page_by_seq)
    return text[:chars] if len(text) > chars else text


def repair_truncated_json(text: str) -> str:
    """Attempt to repair truncated JSON by closing unclosed strings, brackets, and braces.

    Uses a state machine that tracks whether we are inside a string value,
    so brackets inside JSON strings (e.g., Arabic text containing [1])
    are not counted as structural brackets. This prevents the naive
    bracket-counting bug that could produce structurally corrupt output.
    """
    # Walk the text tracking JSON structural state
    in_string = False
    escaped = False
    stack = []  # tracks open [ and { outside strings

    for ch in text:
        if escaped:
            escaped = False
            continue
        if ch == '\\' and in_string:
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        # Outside string — track structural brackets
        if ch in ('{', '['):
            stack.append(ch)
        elif ch == '}':
            if stack and stack[-1] == '{':
                stack.pop()
        elif ch == ']':
            if stack and stack[-1] == '[':
                stack.pop()

    # Build repair suffix
    repair = text
    # If we ended inside a string, close it
    if in_string:
        repair += '"'
    # Close stack in reverse order
    for opener in reversed(stack):
        if opener == '{':
            repair += '}'
        else:
            repair += ']'
    return repair


def call_llm(system: str, user: str, model: str, api_key: str) -> dict:
    """Call Claude API and return parsed JSON response."""
    import httpx

    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 16384,
            "temperature": 0,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=180.0,
    )

    if resp.status_code != 200:
        raise RuntimeError(
            f"API error {resp.status_code}: {resp.text[:500]}"
        )

    data = resp.json()
    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block["text"]

    # Strip markdown fences if present
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    usage = data.get("usage", {})
    stop_reason = data.get("stop_reason", "unknown")

    # Try to parse JSON, with repair for truncated output
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        # If truncated (hit max_tokens), try to repair
        if stop_reason == "max_tokens" or "Unterminated" in str(e):
            try:
                parsed = json.loads(repair_truncated_json(text))
            except json.JSONDecodeError:
                raise RuntimeError(
                    f"JSON parse failed even after repair (stop_reason={stop_reason}). "
                    f"First 200 chars: {text[:200]}... Last 200 chars: ...{text[-200:]}"
                )
        else:
            raise

    return {
        "parsed": parsed,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "stop_reason": stop_reason,
    }


_TRANSIENT_STATUS_CODES = {429, 502, 503, 504}
_OPENROUTER_MAX_RETRIES = 3
_OPENROUTER_RETRY_BACKOFF = (2, 5, 10)  # seconds


def call_llm_openrouter(system: str, user: str, model: str,
                         api_key: str) -> dict:
    """Call OpenRouter API (OpenAI-compatible) and return parsed JSON response.

    Works with any model available on OpenRouter (Anthropic, OpenAI, etc.).
    Returns same format as call_llm: {parsed, input_tokens, output_tokens, stop_reason}.

    Retries up to 3 times on transient failures (429, 502, 503, 504) with
    exponential backoff.
    """
    import httpx
    import time

    last_error = None
    for attempt in range(_OPENROUTER_MAX_RETRIES + 1):
        try:
            resp = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 16384,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=240.0,
            )
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
            last_error = e
            if attempt < _OPENROUTER_MAX_RETRIES:
                wait = _OPENROUTER_RETRY_BACKOFF[min(attempt, len(_OPENROUTER_RETRY_BACKOFF) - 1)]
                print(f"  OpenRouter connection error (attempt {attempt + 1}): {e}. "
                      f"Retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise RuntimeError(
                f"OpenRouter connection failed after {_OPENROUTER_MAX_RETRIES + 1} attempts: {e}"
            )

        if resp.status_code in _TRANSIENT_STATUS_CODES and attempt < _OPENROUTER_MAX_RETRIES:
            wait = _OPENROUTER_RETRY_BACKOFF[min(attempt, len(_OPENROUTER_RETRY_BACKOFF) - 1)]
            print(f"  OpenRouter {resp.status_code} (attempt {attempt + 1}). "
                  f"Retrying in {wait}s...")
            time.sleep(wait)
            continue

        if resp.status_code != 200:
            raise RuntimeError(
                f"OpenRouter API error {resp.status_code}: {resp.text[:500]}"
            )
        break  # success

    data = resp.json()
    choice = data["choices"][0]
    text = choice["message"]["content"]

    # Strip markdown fences if present
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    usage = data.get("usage", {})
    stop_reason = choice.get("finish_reason", "unknown")

    # Parse JSON with truncation repair
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        if stop_reason == "length" or "Unterminated" in str(e):
            try:
                parsed = json.loads(repair_truncated_json(text))
            except json.JSONDecodeError:
                raise RuntimeError(
                    f"JSON parse failed even after repair (stop_reason={stop_reason}). "
                    f"First 200 chars: {text[:200]}... Last 200 chars: ...{text[-200:]}"
                )
        else:
            raise

    return {
        "parsed": parsed,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "stop_reason": stop_reason,
    }


def call_llm_dispatch(system: str, user: str, model: str,
                       api_key: str, openrouter_key: str | None = None) -> dict:
    """Dispatch LLM call to the appropriate provider.

    If openrouter_key is provided and model contains '/', routes to OpenRouter.
    Otherwise uses direct Anthropic API via call_llm.
    """
    if openrouter_key and "/" in model:
        return call_llm_openrouter(system, user, model, openrouter_key)
    else:
        return call_llm(system, user, model, api_key)


# ---------------------------------------------------------------------------
# Post-processing — mechanical enrichment after LLM returns
# ---------------------------------------------------------------------------

def _extract_atom_id(entry) -> str:
    """Get atom_id from either a string or an object entry."""
    if isinstance(entry, dict):
        return entry.get("atom_id", "")
    return str(entry)


def _normalize_atom_entries(entries, default_role: str) -> list[dict]:
    """Convert bare string IDs to {atom_id, role} objects if needed."""
    normalized = []
    for entry in entries:
        if isinstance(entry, str):
            normalized.append({"atom_id": entry, "role": default_role})
        elif isinstance(entry, dict):
            entry.setdefault("role", default_role)
            normalized.append(entry)
        else:
            normalized.append({"atom_id": str(entry), "role": default_role})
    return normalized


def post_process_extraction(result: dict, book_id: str, science: str,
                            taxonomy_filename: str = "") -> dict:
    """Mechanically enrich LLM output with fields it shouldn't waste tokens on."""
    atoms = result.get("atoms", [])
    excerpts = result.get("excerpts", [])
    footnote_excerpts = result.get("footnote_excerpts", [])

    # Derive taxonomy version from filename (e.g., "imlaa_v0.1.yaml" -> "imlaa_v0_1")
    tax_version = ""
    if taxonomy_filename:
        base = Path(taxonomy_filename).stem  # e.g., "imlaa_v0.1"
        tax_version = base.replace(".", "_")  # "imlaa_v0_1"

    # --- Atoms ---
    for atom in atoms:
        # Fix field name: type -> atom_type
        if "type" in atom and "atom_type" not in atom:
            atom["atom_type"] = atom.pop("type")
        # Add mechanical fields
        atom.setdefault("record_type", "atom")
        atom.setdefault("book_id", book_id)
        atom.setdefault("source_layer", "matn")
        atom.setdefault("is_prose_tail", False)
        # Normalize bonded_cluster_trigger
        # Accept both "bonding_trigger" (old prompt) and "bonded_cluster_trigger" (schema)
        trigger = atom.pop("bonding_trigger", None) or atom.get("bonded_cluster_trigger")
        if trigger is not None:
            if isinstance(trigger, str):
                # e.g., "T3" or "T5_rule_then_examples"
                tid = trigger[:2] if len(trigger) >= 2 else trigger
                atom["bonded_cluster_trigger"] = {
                    "trigger_id": tid, "reason": trigger
                }
            elif isinstance(trigger, dict):
                atom["bonded_cluster_trigger"] = trigger
            else:
                atom["bonded_cluster_trigger"] = None
        else:
            atom.setdefault("bonded_cluster_trigger", None)
        # Remove old role field from atoms (role belongs on excerpt entries, not atoms)
        atom.pop("role", None)
        # Remove old bonding_reason if present (now inside trigger object)
        atom.pop("bonding_reason", None)

    # --- Excerpts ---
    for exc in excerpts:
        exc.setdefault("record_type", "excerpt")
        exc.setdefault("book_id", book_id)
        if tax_version:
            exc.setdefault("taxonomy_version", tax_version)
        exc.setdefault("status", "auto")
        exc.setdefault("source_layer", "matn")
        exc.setdefault("cross_science_context", False)
        exc.setdefault("related_science", None)
        exc.setdefault("interwoven_group_id", None)
        exc.setdefault("content_type", "prose")
        exc.setdefault("relations", [])
        exc.setdefault("case_types", [])
        exc.setdefault("heading_path", [])
        exc.setdefault("context_atoms", [])
        # Normalize core/context atoms to objects with roles
        exc["core_atoms"] = _normalize_atom_entries(
            exc.get("core_atoms", []), "author_prose"
        )
        exc["context_atoms"] = _normalize_atom_entries(
            exc.get("context_atoms", []), "preceding_setup"
        )

    # --- Footnote Excerpts ---
    for fex in footnote_excerpts:
        fex.setdefault("record_type", "excerpt")
        fex.setdefault("book_id", book_id)
        fex.setdefault("source_layer", "footnote")
        if tax_version:
            fex.setdefault("taxonomy_version", tax_version)

    # --- Generate exclusion records ---
    exclusions = result.get("exclusions", [])
    excluded_ids = {e.get("atom_id") for e in exclusions}
    for atom in atoms:
        aid = atom.get("atom_id", "")
        if aid in excluded_ids:
            continue
        atype = atom.get("atom_type", "")
        if atype == "heading":
            exclusions.append({
                "record_type": "exclusion",
                "atom_id": aid,
                "book_id": book_id,
                "exclusion_reason": "heading_structural",
            })
        elif atom.get("is_prose_tail"):
            exclusions.append({
                "record_type": "exclusion",
                "atom_id": aid,
                "book_id": book_id,
                "exclusion_reason": "non_scholarly_apparatus",
                "exclusion_note": "Continuation from previous passage",
            })
    result["exclusions"] = exclusions
    result.setdefault("footnote_excerpts", [])
    result.setdefault("notes", "")

    return result


# ---------------------------------------------------------------------------
# Validation — 16 checks with severity levels
# ---------------------------------------------------------------------------

def validate_extraction(result: dict, passage_id: str,
                        taxonomy_leaves: set) -> dict:
    """Validate extracted atoms and excerpts.

    Returns {"errors": [...], "warnings": [...], "info": [...]}.
    Errors block acceptance and trigger retry.
    Warnings trigger retry if no errors exist.
    Info is logged only.
    """
    errors = []
    warnings = []
    info = []

    atoms = result.get("atoms", [])
    excerpts = result.get("excerpts", [])

    # Build atom lookup
    atom_by_id = {}
    for a in atoms:
        aid = a.get("atom_id", "")
        if aid:
            atom_by_id[aid] = a
    atom_ids = set(atom_by_id.keys())

    # Determine which atoms are excluded (headings, prose_tails, footnote-layer)
    heading_ids = set()
    prose_tail_ids = set()
    footnote_atom_ids = set()
    for a in atoms:
        aid = a.get("atom_id", "")
        atype = a.get("atom_type", a.get("type", ""))
        if atype == "heading":
            heading_ids.add(aid)
        if a.get("is_prose_tail"):
            prose_tail_ids.add(aid)
        if a.get("source_layer") == "footnote":
            footnote_atom_ids.add(aid)
    excluded_ids = heading_ids | prose_tail_ids | footnote_atom_ids

    # --- Check 1: Atom required fields ---
    for a in atoms:
        aid = a.get("atom_id", "???")
        atype_key = "atom_type" if "atom_type" in a else "type"
        for field in ("atom_id", "text"):
            if field not in a:
                errors.append(f"Atom missing field '{field}': {aid}")
        if atype_key not in a:
            errors.append(f"Atom missing atom_type: {aid}")

    # --- Check 2: Atom text non-empty (ATOM.A8) ---
    for a in atoms:
        if not a.get("text", "").strip():
            errors.append(
                f"Atom has empty text: {a.get('atom_id', '???')}"
            )

    # --- Check 3: Atom type valid ---
    for a in atoms:
        atype = a.get("atom_type", a.get("type", ""))
        if atype and atype not in VALID_ATOM_TYPES:
            warnings.append(
                f"Atom {a.get('atom_id','???')} has invalid atom_type '{atype}'"
            )

    # --- Check 4: Bonded cluster trigger (ATOM.B) ---
    for a in atoms:
        atype = a.get("atom_type", a.get("type", ""))
        trigger = a.get("bonded_cluster_trigger")
        if atype == "bonded_cluster":
            if not trigger:
                warnings.append(
                    f"bonded_cluster atom {a.get('atom_id','???')} missing "
                    f"bonded_cluster_trigger"
                )
            elif isinstance(trigger, dict):
                tid = trigger.get("trigger_id", "")
                if tid not in VALID_TRIGGER_IDS:
                    warnings.append(
                        f"Atom {a.get('atom_id','???')} has invalid "
                        f"trigger_id '{tid}'"
                    )
                if not trigger.get("reason", "").strip():
                    warnings.append(
                        f"Atom {a.get('atom_id','???')} bonded_cluster_trigger "
                        f"missing reason"
                    )
        elif trigger and trigger is not None:
            info.append(
                f"Non-bonded atom {a.get('atom_id','???')} has "
                f"bonded_cluster_trigger (should be null)"
            )

    # --- Check 5: Excerpt required fields ---
    for exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        for field in ("excerpt_id", "taxonomy_node_id", "core_atoms",
                       "boundary_reasoning", "source_layer", "excerpt_title"):
            if field not in exc:
                errors.append(f"Excerpt missing field '{field}': {eid}")
        if "case_types" not in exc or not exc.get("case_types"):
            warnings.append(f"Excerpt {eid} missing or empty case_types")

    # --- Check 6: Excerpt reference integrity ---
    covered_atoms = set()
    for exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        for entry in exc.get("core_atoms", []):
            aid = _extract_atom_id(entry)
            if aid and aid not in atom_ids:
                errors.append(
                    f"Excerpt {eid} references unknown atom {aid}"
                )
            covered_atoms.add(aid)
        for entry in exc.get("context_atoms", []):
            aid = _extract_atom_id(entry)
            if aid and aid not in atom_ids:
                errors.append(
                    f"Excerpt {eid} context references unknown atom {aid}"
                )

    # --- Check 7: Coverage (ATOM.E1) ---
    non_excluded_ids = atom_ids - excluded_ids
    uncovered = non_excluded_ids - covered_atoms
    if uncovered:
        errors.append(
            f"Uncovered atoms (not in any excerpt): {sorted(uncovered)}"
        )

    # --- Check 8: No multi-core assignment (EXC.C5) ---
    core_seen = {}
    for exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        for entry in exc.get("core_atoms", []):
            aid = _extract_atom_id(entry)
            if aid in core_seen:
                errors.append(
                    f"Atom {aid} is core in both {core_seen[aid]} and {eid}"
                )
            core_seen[aid] = eid

    # --- Check 9: Heading never in excerpt (ATOM.H4, EXC.B2) ---
    for exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        for entry in exc.get("core_atoms", []):
            aid = _extract_atom_id(entry)
            if aid in heading_ids:
                errors.append(
                    f"Heading atom {aid} appears as core in excerpt {eid}"
                )
        for entry in exc.get("context_atoms", []):
            aid = _extract_atom_id(entry)
            if aid in heading_ids:
                errors.append(
                    f"Heading atom {aid} appears as context in excerpt {eid}"
                )

    # --- Check 10: Leaf-only placement (PLACE.P2) ---
    for exc in excerpts:
        node = exc.get("taxonomy_node_id", "")
        if node and node != "_unmapped" and node not in taxonomy_leaves:
            warnings.append(
                f"Excerpt {exc.get('excerpt_id','???')} placed at "
                f"non-leaf '{node}'"
            )

    # --- Check 11: Core atom role validation ---
    for exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        for entry in exc.get("core_atoms", []):
            if isinstance(entry, dict):
                role = entry.get("role", "")
                if role and role not in VALID_CORE_ROLES:
                    warnings.append(
                        f"Excerpt {eid} core atom "
                        f"{entry.get('atom_id','???')} has invalid "
                        f"role '{role}'"
                    )
                if not role:
                    warnings.append(
                        f"Excerpt {eid} core atom "
                        f"{entry.get('atom_id','???')} missing role"
                    )

    # --- Check 12: Context atom role validation ---
    for exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        for entry in exc.get("context_atoms", []):
            if isinstance(entry, dict):
                role = entry.get("role", "")
                if role and role not in VALID_CONTEXT_ROLES:
                    warnings.append(
                        f"Excerpt {eid} context atom "
                        f"{entry.get('atom_id','???')} has invalid "
                        f"role '{role}'"
                    )

    # --- Check 13: case_types valid ---
    for exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        for ct in exc.get("case_types", []):
            if ct not in VALID_CASE_TYPES:
                warnings.append(
                    f"Excerpt {eid} has invalid case_type '{ct}'"
                )

    # --- Check 14: Layer isolation (EXC.L1) ---
    for exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        exc_layer = exc.get("source_layer", "matn")
        for entry in exc.get("core_atoms", []) + exc.get("context_atoms", []):
            aid = _extract_atom_id(entry)
            atom = atom_by_id.get(aid)
            if atom and atom.get("source_layer", "matn") != exc_layer:
                warnings.append(
                    f"Excerpt {eid} (layer={exc_layer}) contains "
                    f"atom {aid} from different layer "
                    f"'{atom.get('source_layer')}'"
                )

    # --- Check 15: Atom ID format ---
    for a in atoms:
        aid = a.get("atom_id", "")
        if aid and not ATOM_ID_RE.match(aid):
            info.append(f"Atom ID '{aid}' doesn't match expected format")

    # --- Check 16: Excerpt ID format ---
    for exc in excerpts:
        eid = exc.get("excerpt_id", "")
        if eid and not EXCERPT_ID_RE.match(eid):
            info.append(f"Excerpt ID '{eid}' doesn't match expected format")

    # --- Check 17: Relation type validation ---
    for exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        for rel in exc.get("relations", []):
            rtype = rel.get("type", "")
            if rtype and rtype not in VALID_RELATION_TYPES:
                info.append(
                    f"Excerpt {eid} has unknown relation type '{rtype}'"
                )

    # --- Check 18: Footnote atom coverage (F21) ---
    # Footnote-layer atoms are excluded from Check 7, but they should
    # appear in at least one footnote_excerpt. Silently lost footnotes
    # are a data integrity issue.
    if footnote_atom_ids:
        fn_covered = set()
        for fn_exc in result.get("footnote_excerpts", []):
            fn_text = fn_exc.get("text", "")
            # Footnote excerpts carry inline text, not atom refs.
            # Check if any footnote atom's text appears in a footnote excerpt.
            for aid in footnote_atom_ids:
                atom = atom_by_id.get(aid)
                if atom:
                    atom_text = atom.get("text", "").strip()
                    if atom_text and atom_text in fn_text:
                        fn_covered.add(aid)
        # Also check if footnote atoms appear in exclusions
        excl_ids = {e.get("atom_id", "") for e in result.get("exclusions", [])}
        fn_uncovered = footnote_atom_ids - fn_covered - excl_ids
        if fn_uncovered:
            warnings.append(
                f"Footnote atoms not in any footnote_excerpt or exclusion: "
                f"{sorted(fn_uncovered)}"
            )

    return {"errors": errors, "warnings": warnings, "info": info}


def extract_taxonomy_leaves(yaml_text: str) -> set[str]:
    """Quick extraction of leaf node IDs from YAML taxonomy."""
    leaves = set()
    lines = yaml_text.split("\n")
    for i, line in enumerate(lines):
        # Strip comments and whitespace
        stripped = line.split("#")[0].strip()
        if stripped == "_leaf: true" and i > 0:
            # The leaf ID is the key on the previous non-blank, non-_leaf line
            for j in range(i - 1, -1, -1):
                prev = lines[j].split("#")[0].strip().rstrip(":")
                if prev and not prev.startswith("_") and not prev.startswith("#"):
                    leaves.add(prev)
                    break
    return leaves


# ---------------------------------------------------------------------------
# Correction pass — retry with feedback
# ---------------------------------------------------------------------------

def attempt_correction(result: dict, issues: dict, passage_id: str,
                       system: str, model: str, api_key: str,
                       openrouter_key: str | None = None) -> dict | None:
    """Send a correction prompt and return the corrected result, or None."""
    # Format issues
    all_issues = []
    for severity, items in [("ERROR", issues["errors"]),
                            ("WARNING", issues["warnings"])]:
        for item in items:
            all_issues.append(f"[{severity}] {item}")
    issues_text = "\n".join(all_issues)

    previous_output = json.dumps(result, ensure_ascii=False, indent=2)
    # Truncate if very long to stay within token budget
    if len(previous_output) > 30000:
        previous_output = previous_output[:30000] + "\n... (truncated)"

    user_msg = CORRECTION_PROMPT.format(
        passage_id=passage_id,
        issues_text=issues_text,
        previous_output=previous_output,
    )

    try:
        response = call_llm_dispatch(system, user_msg, model, api_key,
                                     openrouter_key)
        return response
    except Exception as e:
        print(f"    Correction call failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Review report generation
# ---------------------------------------------------------------------------

def generate_review_md(
    passage: dict,
    result: dict,
    issues: dict,
    cost: dict,
    retries: int = 0,
) -> str:
    """Generate a human-reviewable markdown report."""
    lines = []
    pid = passage["passage_id"]
    lines.append(f"# Extraction Review: {pid} — {passage['title']}")
    lines.append("")
    lines.append(f"- Pages: {passage['start_seq_index']}–{passage['end_seq_index']} ({passage['page_count']}p)")
    lines.append(f"- Atoms: {len(result.get('atoms', []))}")
    lines.append(f"- Excerpts: {len(result.get('excerpts', []))}")
    lines.append(f"- Footnote excerpts: {len(result.get('footnote_excerpts', []))}")
    lines.append(f"- Cost: ~${cost.get('total_cost', 0):.4f} ({cost.get('input_tokens',0)} in, {cost.get('output_tokens',0)} out)")
    if retries > 0:
        lines.append(f"- Correction retries: {retries}")
    lines.append("")

    n_errors = len(issues.get("errors", []))
    n_warnings = len(issues.get("warnings", []))
    n_info = len(issues.get("info", []))
    total_issues = n_errors + n_warnings

    if total_issues == 0:
        lines.append("## Validation: All checks passed")
    else:
        lines.append(f"## Validation Issues ({n_errors} errors, {n_warnings} warnings)")
        if issues.get("errors"):
            for item in issues["errors"]:
                lines.append(f"- [ERROR] {item}")
        if issues.get("warnings"):
            for item in issues["warnings"]:
                lines.append(f"- [WARN] {item}")
    if issues.get("info"):
        lines.append("")
        lines.append(f"## Info ({n_info})")
        for item in issues["info"]:
            lines.append(f"- [INFO] {item}")
    lines.append("")

    # Atoms
    type_markers = {
        "heading": "H", "prose_sentence": "S",
        "bonded_cluster": "BC", "verse_evidence": "V",
        "quran_quote_standalone": "Q", "list_item": "LI",
    }
    lines.append("## Atoms")
    for a in result.get("atoms", []):
        atype = a.get("atom_type", a.get("type", "?"))
        marker = type_markers.get(atype, "?")
        tail = " [TAIL]" if a.get("is_prose_tail") else ""
        text_preview = a.get("text", "")[:120]
        lines.append(f"- `{a.get('atom_id','???')}` [{marker}]{tail} {text_preview}")
        trigger = a.get("bonded_cluster_trigger")
        if trigger and isinstance(trigger, dict):
            lines.append(f"  - Trigger: {trigger.get('trigger_id','')} — {trigger.get('reason','')}")
    lines.append("")

    # Excerpts
    lines.append("## Excerpts")
    for exc in result.get("excerpts", []):
        eid = exc.get("excerpt_id", "???")
        lines.append(f"### {eid}: {exc.get('excerpt_title', '???')}")
        lines.append(f"- **Node:** `{exc.get('taxonomy_node_id', '?')}` → {exc.get('taxonomy_path', '?')}")
        lines.append(f"- **Kind:** {exc.get('excerpt_kind', '?')} | **Type:** {exc.get('content_type', '?')}")
        lines.append(f"- **case_types:** {', '.join(exc.get('case_types', []))}")
        # Format core/context atoms
        core_ids = [_extract_atom_id(e) for e in exc.get("core_atoms", [])]
        ctx_ids = [_extract_atom_id(e) for e in exc.get("context_atoms", [])]
        lines.append(f"- **Core atoms:** {', '.join(core_ids)}")
        if ctx_ids:
            lines.append(f"- **Context atoms:** {', '.join(ctx_ids)}")
        lines.append(f"- **Boundary reasoning:** {exc.get('boundary_reasoning', '(none)')}")
        for rel in exc.get("relations", []):
            target = rel.get("target_excerpt_id") or rel.get("target_hint", "?")
            lines.append(f"- **Relation:** {rel.get('type', '?')} → {target}")
        lines.append("")

        # Show full text
        lines.append("**Full text:**")
        core_id_set = set(core_ids)
        for aid in core_ids + ctx_ids:
            atom = next((a for a in result["atoms"] if a.get("atom_id") == aid), None)
            if atom:
                prefix = "[CORE]" if aid in core_id_set else "[CTX]"
                lines.append(f"> {prefix} {atom['text']}")
        lines.append("")

    # Footnote excerpts
    if result.get("footnote_excerpts"):
        lines.append("## Footnote Excerpts")
        for fex in result["footnote_excerpts"]:
            lines.append(f"- `{fex.get('excerpt_id', '?')}`: {fex.get('excerpt_title', '?')}")
            lines.append(f"  - Linked to: {fex.get('linked_matn_excerpt', '?')}")
            lines.append(f"  - Text: {fex.get('text', '')[:200]}")
        lines.append("")

    # Exclusions
    if result.get("exclusions"):
        lines.append("## Exclusions")
        for exc in result["exclusions"]:
            lines.append(f"- `{exc.get('atom_id', '?')}` — {exc.get('exclusion_reason', '?')}")
        lines.append("")

    # Notes
    if result.get("notes"):
        lines.append("## LLM Notes")
        lines.append(result["notes"])
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Single-model extraction helper
# ---------------------------------------------------------------------------

def extract_single_model(
    system: str,
    user: str,
    model: str,
    api_key: str,
    book_id: str,
    science: str,
    taxonomy_filename: str,
    pid: str,
    taxonomy_leaves: set,
    max_retries: int,
    openrouter_key: str | None = None,
) -> tuple[dict, dict, dict, int]:
    """Run extraction with one model, including correction retries.

    Returns: (result, issues, cost_info, retries_used)
    where cost_info = {"model": str, "input_tokens": int,
                       "output_tokens": int, "total_cost": float}
    """
    t0 = time.time()
    response = call_llm_dispatch(system, user, model, api_key, openrouter_key)
    elapsed = time.time() - t0

    result = response["parsed"]
    in_tok = response["input_tokens"]
    out_tok = response["output_tokens"]
    cost = get_model_cost(model, in_tok, out_tok)

    print(f"  [{model}] {elapsed:.1f}s, {in_tok} in + {out_tok} out = ${cost:.4f}")

    # Post-process
    result = post_process_extraction(result, book_id, science, taxonomy_filename)

    # Validate
    issues = validate_extraction(result, pid, taxonomy_leaves)
    n_issues = len(issues["errors"]) + len(issues["warnings"])
    status = "pass" if n_issues == 0 else f"{len(issues['errors'])}E {len(issues['warnings'])}W"
    print(f"  [{model}] Atoms: {len(result.get('atoms', []))}, "
          f"Excerpts: {len(result.get('excerpts', []))}, "
          f"Validation: {status}")

    if issues["errors"]:
        for iss in issues["errors"][:3]:
            print(f"    - [ERROR] {iss}")
    if issues["warnings"]:
        for iss in issues["warnings"][:3]:
            print(f"    - [WARN] {iss}")

    # Correction retry loop
    retries_used = 0
    if n_issues > 0 and max_retries > 0:
        for retry in range(max_retries):
            print(f"  [{model}] Correction attempt {retry + 1}/{max_retries}...")
            correction = attempt_correction(
                result, issues, pid, system, model, api_key, openrouter_key
            )
            if correction is None:
                break

            retries_used += 1
            r_in = correction["input_tokens"]
            r_out = correction["output_tokens"]
            r_cost = get_model_cost(model, r_in, r_out)
            in_tok += r_in
            out_tok += r_out
            cost += r_cost

            result = correction["parsed"]
            result = post_process_extraction(
                result, book_id, science, taxonomy_filename
            )
            issues = validate_extraction(result, pid, taxonomy_leaves)
            n_issues = len(issues["errors"]) + len(issues["warnings"])
            status = "pass" if n_issues == 0 else f"{len(issues['errors'])}E {len(issues['warnings'])}W"
            print(f"    After correction: {status} (+${r_cost:.4f})")

            if n_issues == 0:
                break

    cost_info = {
        "model": model,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "total_cost": cost,
    }
    return result, issues, cost_info, retries_used


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_extraction(args):
    """Main extraction pipeline. Supports single-model and consensus modes."""
    # Load inputs
    passages = load_jsonl(args.passages)
    pages = load_jsonl(args.pages)
    page_by_seq = {p["seq_index"]: p for p in pages}
    taxonomy_yaml = load_taxonomy_yaml(args.taxonomy)
    taxonomy_leaves = extract_taxonomy_leaves(taxonomy_yaml)
    gold_text = load_gold_example(args.gold)

    # Derive taxonomy filename for version string
    taxonomy_filename = Path(args.taxonomy).name

    # Consensus mode detection
    consensus_mode = getattr(args, "consensus_mode", False)
    model_list = getattr(args, "model_list", [args.model])
    openrouter_key = getattr(args, "openrouter_key", None)

    # Filter passages if specified
    if args.passage_ids:
        target_ids = set(args.passage_ids.split(","))
        passage_indices = [
            (i, p) for i, p in enumerate(passages) if p["passage_id"] in target_ids
        ]
    else:
        passage_indices = list(enumerate(passages))

    # Output directory
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Sequence tracking.
    # When processing a subset of passages (--passage-ids), we derive the
    # starting sequence from the passage index * a large stride (1000) to
    # ensure IDs don't collide across passages on re-runs. Without this,
    # re-processing P005 alone would restart at 1, colliding with P004's atoms.
    if args.passage_ids and passage_indices:
        first_passage_idx = passage_indices[0][0]
        atom_seq = first_passage_idx * 1000 + 1
        excerpt_seq = first_passage_idx * 1000 + 1
    else:
        atom_seq = 1
        excerpt_seq = 1

    # Results accumulator
    all_results = []
    total_cost = {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0}

    max_retries = getattr(args, "max_retries", 2)

    print(f"=== Extraction Pipeline ===")
    print(f"Book: {args.book_title} ({args.book_id})")
    print(f"Science: {args.science}")
    print(f"Passages to process: {len(passage_indices)}")
    print(f"Taxonomy leaves: {len(taxonomy_leaves)}")
    print(f"Output: {outdir}")
    if consensus_mode:
        print(f"Mode: CONSENSUS ({len(model_list)} models)")
        print(f"Models: {', '.join(model_list)}")
        arbiter_model = getattr(args, "arbiter_model", None)
        if arbiter_model:
            print(f"Arbiter: {arbiter_model}")
    else:
        print(f"Model: {args.model}")
    print(f"Max retries: {max_retries}")
    print(f"")

    for idx, passage in passage_indices:
        pid = passage["passage_id"]
        print(f"--- {pid}: {passage['title']} ({passage['page_count']}p) ---")

        # Assemble passage text
        passage_text = get_passage_text(passage, page_by_seq)
        if not passage_text.strip():
            print(f"  SKIP: empty passage text")
            continue

        footnotes = get_passage_footnotes(passage, page_by_seq)
        prev_tail = get_context_tail(passages, idx, page_by_seq)
        next_head = get_context_head(passages, idx, page_by_seq)

        # Build heading path from passage metadata
        heading_path = passage.get("heading_path", passage.get("title", ""))

        # Build gold section
        gold_section = ""
        if gold_text:
            gold_section = (
                "## Gold Example (for calibration — study the style and "
                "decisions)\n" + gold_text
            )

        # Fill prompt templates
        system = SYSTEM_PROMPT.format(
            book_title=args.book_title,
            book_id=args.book_id,
            science=args.science,
            passage_id=pid,
            passage_title=passage["title"],
            heading_path=heading_path,
            taxonomy_yaml=taxonomy_yaml,
            atom_start_seq=atom_seq,
            excerpt_start_seq=excerpt_seq,
        )

        user = USER_PROMPT.format(
            prev_passage_tail=prev_tail,
            passage_id=pid,
            passage_text=passage_text,
            next_passage_head=next_head,
            footnotes=footnotes,
            gold_section=gold_section,
        )

        if args.dry_run:
            # Save prompt for inspection
            prompt_path = outdir / f"{pid}_prompt.md"
            with open(prompt_path, "w", encoding="utf-8") as f:
                f.write(f"# SYSTEM\n\n{system}\n\n# USER\n\n{user}")
                if consensus_mode:
                    f.write(f"\n\n# CONSENSUS MODE\n")
                    f.write(f"Models: {', '.join(model_list)}\n")
            print(f"  DRY RUN: prompt saved to {prompt_path}")
            print(f"  System prompt: {len(system)} chars")
            print(f"  User prompt: {len(user)} chars")
            continue

        # ---------------------------------------------------------------
        # SINGLE MODEL MODE (backward compatible)
        # ---------------------------------------------------------------
        if not consensus_mode:
            try:
                result, issues, cost_info, retries_used = extract_single_model(
                    system, user, args.model, args.api_key,
                    args.book_id, args.science, taxonomy_filename,
                    pid, taxonomy_leaves, max_retries, openrouter_key,
                )
            except Exception as e:
                print(f"  ERROR: {e}")
                err_path = outdir / f"{pid}_error.txt"
                with open(err_path, "w", encoding="utf-8") as f:
                    f.write(str(e))
                continue

            in_tok = cost_info["input_tokens"]
            out_tok = cost_info["output_tokens"]
            cost = cost_info["total_cost"]
            total_cost["input_tokens"] += in_tok
            total_cost["output_tokens"] += out_tok
            total_cost["total_cost"] += cost

        # ---------------------------------------------------------------
        # CONSENSUS MODE
        # ---------------------------------------------------------------
        else:
            from tools.consensus import build_consensus, generate_consensus_review_section

            per_model_results = {}
            per_model_issues = {}
            per_model_costs = {}
            per_model_retries = {}

            for model in model_list:
                try:
                    m_result, m_issues, m_cost, m_retries = extract_single_model(
                        system, user, model, args.api_key,
                        args.book_id, args.science, taxonomy_filename,
                        pid, taxonomy_leaves, max_retries, openrouter_key,
                    )
                    per_model_results[model] = m_result
                    per_model_issues[model] = m_issues
                    per_model_costs[model] = m_cost
                    per_model_retries[model] = m_retries
                except Exception as e:
                    print(f"  [{model}] ERROR: {e}")
                    err_path = outdir / f"{pid}_{_model_short(model)}_error.txt"
                    with open(err_path, "w", encoding="utf-8") as f:
                        f.write(str(e))

            if len(per_model_results) < 2:
                # Fallback: fewer than 2 models succeeded
                if per_model_results:
                    fallback_model = list(per_model_results.keys())[0]
                    result = per_model_results[fallback_model]
                    issues = per_model_issues[fallback_model]
                    cost_info = per_model_costs[fallback_model]
                    retries_used = per_model_retries[fallback_model]
                    print(f"  CONSENSUS FALLBACK: only {fallback_model} succeeded")
                else:
                    print(f"  ALL MODELS FAILED for {pid}")
                    continue
            else:
                # Save per-model raw outputs for auditability
                for model in per_model_results:
                    raw_path = outdir / f"{pid}_{_model_short(model)}_raw.json"
                    with open(raw_path, "w", encoding="utf-8") as f:
                        json.dump(per_model_results[model], f,
                                  ensure_ascii=False, indent=2)

                # Build arbiter call function if arbiter model configured
                arbiter_model = getattr(args, "arbiter_model", None)
                call_llm_fn = None
                if arbiter_model:
                    def call_llm_fn(sys_p, usr_p, mdl, key):
                        return call_llm_dispatch(sys_p, usr_p, mdl, key,
                                                 openrouter_key)

                models = list(per_model_results.keys())
                if len(models) > 2:
                    print(f"  WARNING: {len(models)} models succeeded but "
                          f"consensus only uses first 2: {models[0]}, {models[1]}. "
                          f"Ignoring: {', '.join(models[2:])}")

                # Get arbiter pricing from MODEL_PRICING if arbiter model known
                arbiter_pricing = None
                if arbiter_model:
                    arbiter_pricing = MODEL_PRICING.get(arbiter_model)

                consensus = build_consensus(
                    passage_id=pid,
                    result_a=per_model_results[models[0]],
                    result_b=per_model_results[models[1]],
                    model_a=models[0],
                    model_b=models[1],
                    issues_a=per_model_issues[models[0]],
                    issues_b=per_model_issues[models[1]],
                    prefer_model=getattr(args, "consensus_prefer", None),
                    threshold=getattr(args, "consensus_threshold", 0.5),
                    call_llm_fn=call_llm_fn,
                    arbiter_model=arbiter_model,
                    arbiter_api_key=openrouter_key or args.api_key,
                    taxonomy_yaml=taxonomy_yaml,
                    passage_text=passage_text,
                    arbiter_pricing=arbiter_pricing,
                )

                # Use consensus result
                result = {
                    "atoms": consensus["atoms"],
                    "excerpts": consensus["excerpts"],
                    "footnote_excerpts": consensus["footnote_excerpts"],
                    "exclusions": consensus["exclusions"],
                    "notes": consensus["notes"],
                    "consensus_meta": consensus["consensus_meta"],
                }

                # F11: Post-process consensus output to ensure footnote
                # excerpts from the losing model have standard metadata
                # (record_type, book_id, taxonomy_version).
                result = post_process_extraction(
                    result, args.book_id, args.science, taxonomy_filename,
                )

                issues = validate_extraction(result, pid, taxonomy_leaves)
                retries_used = sum(per_model_retries.values())

                # Aggregate costs across models + arbiter
                cost_info = {"model": "consensus", "input_tokens": 0,
                             "output_tokens": 0, "total_cost": 0.0}
                for mc in per_model_costs.values():
                    cost_info["input_tokens"] += mc["input_tokens"]
                    cost_info["output_tokens"] += mc["output_tokens"]
                    cost_info["total_cost"] += mc["total_cost"]
                arbiter_cost = consensus["consensus_meta"].get("arbiter_cost", {})
                cost_info["input_tokens"] += arbiter_cost.get("input_tokens", 0)
                cost_info["output_tokens"] += arbiter_cost.get("output_tokens", 0)
                cost_info["total_cost"] += arbiter_cost.get("total_cost", 0.0)

                # Print consensus summary
                meta = consensus["consensus_meta"]
                print(f"  CONSENSUS: {meta['full_agreement_count']} agreed, "
                      f"{meta['placement_disagreement_count']} placement disagreements, "
                      f"{meta['unmatched_a_count']+meta['unmatched_b_count']} unmatched")

            in_tok = cost_info["input_tokens"]
            out_tok = cost_info["output_tokens"]
            cost = cost_info["total_cost"]
            total_cost["input_tokens"] += in_tok
            total_cost["output_tokens"] += out_tok
            total_cost["total_cost"] += cost

        # Update sequence counters.
        # In consensus mode, result["atoms"] is a filtered merge of both models.
        # We advance by the count of atoms/excerpts actually in the output,
        # not the per-model counts, to keep IDs contiguous across passages.
        atom_seq += len(result.get("atoms", []))
        excerpt_seq += len(result.get("excerpts", []))
        excerpt_seq += len(result.get("footnote_excerpts", []))

        # Save extraction result
        raw_path = outdir / f"{pid}_extraction.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # Generate review report
        review = generate_review_md(
            passage, result, issues,
            {"input_tokens": in_tok, "output_tokens": out_tok,
             "total_cost": cost},
            retries=retries_used,
        )

        # Append consensus review section if applicable
        if consensus_mode and "consensus_meta" in result:
            from tools.consensus import generate_consensus_review_section
            review += "\n" + generate_consensus_review_section(
                result["consensus_meta"]
            )

        review_path = outdir / f"{pid}_review.md"
        with open(review_path, "w", encoding="utf-8") as f:
            f.write(review)

        total_issue_count = len(issues["errors"]) + len(issues["warnings"])
        passage_result = {
            "passage_id": pid,
            "atoms": len(result.get("atoms", [])),
            "excerpts": len(result.get("excerpts", [])),
            "footnote_excerpts": len(result.get("footnote_excerpts", [])),
            "issues": total_issue_count,
            "retries": retries_used,
            "cost": cost,
        }
        if consensus_mode and "consensus_meta" in result:
            meta = result["consensus_meta"]
            passage_result["consensus"] = {
                "full_agreement": meta.get("full_agreement_count", 0),
                "placement_disagreements": meta.get("placement_disagreement_count", 0),
                "unmatched": meta.get("unmatched_a_count", 0) + meta.get("unmatched_b_count", 0),
                "coverage_agreement": meta.get("coverage_agreement", {}).get(
                    "coverage_agreement_ratio", 0),
            }
        all_results.append(passage_result)

        # Rate limit courtesy
        time.sleep(1)

    # Summary
    print(f"\n=== Summary ===")
    total_atoms = sum(r["atoms"] for r in all_results)
    total_excerpts = sum(r["excerpts"] for r in all_results)
    total_issues = sum(r["issues"] for r in all_results)
    total_retries = sum(r.get("retries", 0) for r in all_results)
    print(f"Passages processed: {len(all_results)}")
    print(f"Total atoms: {total_atoms}")
    print(f"Total excerpts: {total_excerpts}")
    print(f"Total issues: {total_issues}")
    print(f"Total retries: {total_retries}")
    print(f"Total cost: ${total_cost['total_cost']:.4f}")

    # Save summary
    summary = {
        "book_id": args.book_id,
        "book_title": args.book_title,
        "science": args.science,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "passages": all_results,
        "totals": {
            "atoms": total_atoms,
            "excerpts": total_excerpts,
            "issues": total_issues,
            "retries": total_retries,
            "cost": total_cost,
        },
    }
    if consensus_mode:
        summary["consensus_mode"] = True
        summary["models"] = model_list
    else:
        summary["model"] = args.model

    summary_path = outdir / "extraction_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nResults saved to {outdir}/")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract atoms and excerpts from Stage 2 passages"
    )
    parser.add_argument("--passages", required=True,
                        help="Path to passages.jsonl from Stage 2")
    parser.add_argument("--pages", required=True,
                        help="Path to normalized pages.jsonl from Stage 1")
    parser.add_argument("--taxonomy", required=True,
                        help="Path to taxonomy YAML")
    parser.add_argument("--book-id", required=True,
                        help="Book identifier (e.g., qimlaa)")
    parser.add_argument("--book-title", required=True,
                        help="Book title in Arabic")
    parser.add_argument("--science", required=True,
                        help="Science: imlaa|sarf|nahw|balagha")
    parser.add_argument("--gold", default=None,
                        help="Path to gold example JSON")
    parser.add_argument("--output-dir", required=True,
                        help="Output directory")
    parser.add_argument("--api-key", default=None,
                        help="Anthropic API key (or set ANTHROPIC_API_KEY)")
    parser.add_argument("--model", default="claude-sonnet-4-5-20250929",
                        help="Model to use (single-model mode)")
    parser.add_argument("--passage-ids", default=None,
                        help="Comma-separated passage IDs to process")
    parser.add_argument("--dry-run", action="store_true",
                        help="Save prompts without calling API")
    parser.add_argument("--max-retries", type=int, default=2,
                        help="Max correction retries per passage (default: 2)")

    # Multi-model consensus arguments
    parser.add_argument("--models", default=None,
                        help="Comma-separated OpenRouter model IDs for consensus "
                             "(e.g., 'anthropic/claude-sonnet-4-5-20250929,"
                             "openai/gpt-4o'). Enables consensus when 2+ models.")
    parser.add_argument("--openrouter-key", default=None,
                        help="OpenRouter API key (or set OPENROUTER_API_KEY)")
    parser.add_argument("--consensus-prefer", default=None,
                        help="Model to prefer when breaking ties in consensus")
    parser.add_argument("--consensus-threshold", type=float, default=0.5,
                        help="Minimum text overlap for excerpt matching "
                             "(default: 0.5)")
    parser.add_argument("--arbiter-model", default=None,
                        help="Model to use for resolving disagreements "
                             "(e.g., 'anthropic/claude-sonnet-4-5-20250929'). "
                             "If not set, disagreements are flagged only.")

    args = parser.parse_args()

    # Resolve OpenRouter key
    if not args.openrouter_key:
        args.openrouter_key = os.environ.get("OPENROUTER_API_KEY")

    # Resolve Anthropic API key (for single-model legacy mode)
    if not args.api_key:
        args.api_key = os.environ.get("ANTHROPIC_API_KEY")

    # Build model list and detect consensus mode
    if args.models:
        args.model_list = [m.strip() for m in args.models.split(",")]
        args.consensus_mode = len(args.model_list) >= 2
        # Consensus mode requires OpenRouter key
        if not args.openrouter_key and not args.dry_run:
            print("ERROR: Consensus mode requires --openrouter-key or "
                  "OPENROUTER_API_KEY")
            sys.exit(1)
    else:
        args.model_list = [args.model]
        args.consensus_mode = False

    # Single-model mode requires either direct API key or OpenRouter key
    if not args.consensus_mode and not args.api_key and not args.openrouter_key \
       and not args.dry_run:
        print("ERROR: No API key provided. Use --api-key or set "
              "ANTHROPIC_API_KEY (or use --openrouter-key for OpenRouter)")
        sys.exit(1)

    run_extraction(args)


if __name__ == "__main__":
    main()
