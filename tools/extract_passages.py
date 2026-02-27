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
import sys
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Prompt templates (inlined from extract_v0.1.py for self-containment)
# ---------------------------------------------------------------------------

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
- `atom_id`: format "{book_id}:matn:NNNNNN" (6-digit sequential, starting from {atom_start_seq})
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

Each excerpt gets:
- `excerpt_id`: format "{book_id}:exc:NNNNNN" (starting from {excerpt_start_seq})
- `excerpt_title`: Arabic descriptive title with page hint
- `source_layer`: "matn" or "footnote"
- `excerpt_kind`: "teaching" or "exercise"
- `taxonomy_node_id`: exact leaf ID from the taxonomy (must be a _leaf:true node)
- `taxonomy_path`: full path in Arabic
- `heading_path`: ancestor headings from source
- `core_atoms`: list of atom IDs
- `context_atoms`: list of atom IDs (may be empty)
- `boundary_reasoning`: GROUPING + BOUNDARY + PLACEMENT explanation
- `content_type`: prose | table | example_list | mixed
- `relations`: links to related excerpts if applicable (continuation, elaboration)

## Taxonomy Tree
Use ONLY leaf nodes (_leaf: true) from this taxonomy:

```yaml
{taxonomy_yaml}
```

If no existing leaf fits, set taxonomy_node_id to "_unmapped" and explain why in boundary_reasoning.

## Critical Rules
- NEVER skip content. Every non-heading, non-tail atom must appear in exactly one excerpt as core.
- NEVER invent text. Atoms are verbatim copies.
- NEVER merge content from genuinely different topics into one excerpt.
- Overview/framing sentences go to the PARENT node if one exists, not a child.
- When a numbered list (1 - ..., 2 - ...) describes sub-cases of one rule, each item MAY be its own excerpt IF the taxonomy has a leaf for it, OR they stay together at the parent leaf.
- Passage boundaries from Stage 2 are guidance. If text at the start clearly continues the previous passage, mark it as prose_tail.

## Output Format
Respond with ONLY a JSON object. No markdown fences, no preamble.
"""

USER_PROMPT = """## Passage Text
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

Now atomize and excerpt the current passage. Output JSON only."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def load_taxonomy_yaml(path: str) -> str:
    """Load taxonomy YAML as raw text for prompt injection."""
    with open(path) as f:
        return f.read()


def load_gold_example(path: str | None) -> str:
    """Load gold example and format as few-shot section."""
    if not path or not os.path.exists(path):
        return ""
    with open(path) as f:
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
            # Try closing open structures
            repair = text
            # Count open braces/brackets
            opens = repair.count("{") - repair.count("}")
            open_brackets = repair.count("[") - repair.count("]")
            # Close any open strings
            if repair.count('"') % 2 == 1:
                repair += '"'
            # Close brackets then braces
            repair += "]" * max(0, open_brackets)
            repair += "}" * max(0, opens)
            try:
                parsed = json.loads(repair)
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


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_extraction(result: dict, passage_id: str, taxonomy_leaves: set) -> list[str]:
    """Validate extracted atoms and excerpts. Returns list of issues."""
    issues = []
    atoms = result.get("atoms", [])
    excerpts = result.get("excerpts", [])

    atom_ids = {a["atom_id"] for a in atoms}
    non_excluded_ids = {
        a["atom_id"] for a in atoms
        if a.get("type") not in ("heading", "prose_tail")
    }

    # Check: all atoms have required fields
    for a in atoms:
        for field in ("atom_id", "type", "text"):
            if field not in a:
                issues.append(f"Atom missing field '{field}': {a.get('atom_id', '???')}")

    # Check: all excerpts reference valid atoms
    covered_atoms = set()
    for exc in excerpts:
        for aid in exc.get("core_atoms", []):
            if aid not in atom_ids:
                issues.append(f"Excerpt {exc.get('excerpt_id','???')} references unknown atom {aid}")
            covered_atoms.add(aid)
        for aid in exc.get("context_atoms", []):
            if aid not in atom_ids:
                issues.append(f"Excerpt {exc.get('excerpt_id','???')} context references unknown atom {aid}")

    # Check: every non-excluded atom is covered
    uncovered = non_excluded_ids - covered_atoms
    if uncovered:
        issues.append(f"Uncovered atoms (not in any excerpt): {sorted(uncovered)}")

    # Check: no atom in multiple excerpts as core
    core_seen = {}
    for exc in excerpts:
        for aid in exc.get("core_atoms", []):
            if aid in core_seen:
                issues.append(
                    f"Atom {aid} is core in both {core_seen[aid]} and {exc.get('excerpt_id','???')}"
                )
            core_seen[aid] = exc.get("excerpt_id", "???")

    # Check: taxonomy placement
    for exc in excerpts:
        node = exc.get("taxonomy_node_id", "")
        if node != "_unmapped" and node not in taxonomy_leaves:
            issues.append(
                f"Excerpt {exc.get('excerpt_id','???')} placed at non-leaf '{node}'"
            )

    # Check: required excerpt fields
    for exc in excerpts:
        for field in ("excerpt_id", "taxonomy_node_id", "core_atoms", "boundary_reasoning"):
            if field not in exc:
                issues.append(f"Excerpt missing field '{field}': {exc.get('excerpt_id', '???')}")

    return issues


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
# Review report generation
# ---------------------------------------------------------------------------

def generate_review_md(
    passage: dict,
    result: dict,
    issues: list[str],
    cost: dict,
) -> str:
    """Generate a human-reviewable markdown report."""
    lines = []
    pid = passage["passage_id"]
    lines.append(f"# Extraction Review: {pid} — {passage['title']}")
    lines.append(f"")
    lines.append(f"- Pages: {passage['start_seq_index']}–{passage['end_seq_index']} ({passage['page_count']}p)")
    lines.append(f"- Atoms: {len(result.get('atoms', []))}")
    lines.append(f"- Excerpts: {len(result.get('excerpts', []))}")
    lines.append(f"- Footnote excerpts: {len(result.get('footnote_excerpts', []))}")
    lines.append(f"- Cost: ~${cost.get('total_cost', 0):.4f} ({cost.get('input_tokens',0)} in, {cost.get('output_tokens',0)} out)")
    lines.append(f"")

    if issues:
        lines.append(f"## ⚠️ Validation Issues ({len(issues)})")
        for issue in issues:
            lines.append(f"- {issue}")
        lines.append(f"")
    else:
        lines.append(f"## ✅ Validation: All checks passed")
        lines.append(f"")

    # Atoms
    lines.append(f"## Atoms")
    for a in result.get("atoms", []):
        typ = a.get("type", "?")
        marker = {"heading": "📌", "prose_tail": "⏮", "bonded_cluster": "🔗", "prose_sentence": "📝", "verse_evidence": "📜"}.get(typ, "❓")
        text_preview = a.get("text", "")[:120]
        lines.append(f"- {marker} `{a['atom_id']}` [{typ}] {text_preview}")
        if a.get("bonding_trigger"):
            lines.append(f"  - Bonded: {a['bonding_trigger']} — {a.get('bonding_reason', '')}")
    lines.append(f"")

    # Excerpts
    lines.append(f"## Excerpts")
    for exc in result.get("excerpts", []):
        lines.append(f"### {exc.get('excerpt_id', '???')}: {exc.get('excerpt_title', '???')}")
        lines.append(f"- **Node:** `{exc.get('taxonomy_node_id', '?')}` → {exc.get('taxonomy_path', '?')}")
        lines.append(f"- **Kind:** {exc.get('excerpt_kind', '?')} | **Type:** {exc.get('content_type', '?')}")
        lines.append(f"- **Core atoms:** {', '.join(exc.get('core_atoms', []))}")
        if exc.get("context_atoms"):
            lines.append(f"- **Context atoms:** {', '.join(exc['context_atoms'])}")
        lines.append(f"- **Boundary reasoning:** {exc.get('boundary_reasoning', '(none)')}")
        if exc.get("relations"):
            for rel in exc["relations"]:
                lines.append(f"- **Relation:** {rel.get('type', '?')} → {rel.get('target_excerpt', '?')}")
        lines.append(f"")

        # Show full text
        lines.append(f"**Full text:**")
        for aid in exc.get("core_atoms", []) + exc.get("context_atoms", []):
            atom = next((a for a in result["atoms"] if a["atom_id"] == aid), None)
            if atom:
                prefix = "[CORE]" if aid in exc.get("core_atoms", []) else "[CTX]"
                lines.append(f"> {prefix} {atom['text']}")
        lines.append(f"")

    # Footnote excerpts
    if result.get("footnote_excerpts"):
        lines.append(f"## Footnote Excerpts")
        for fex in result["footnote_excerpts"]:
            lines.append(f"- `{fex.get('excerpt_id', '?')}`: {fex.get('excerpt_title', '?')}")
            lines.append(f"  - Linked to: {fex.get('linked_matn_excerpt', '?')}")
            lines.append(f"  - Text: {fex.get('text', '')[:200]}")
        lines.append(f"")

    # Notes
    if result.get("notes"):
        lines.append(f"## LLM Notes")
        lines.append(result["notes"])
        lines.append(f"")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_extraction(args):
    """Main extraction pipeline."""
    # Load inputs
    passages = load_jsonl(args.passages)
    pages = load_jsonl(args.pages)
    page_by_seq = {p["seq_index"]: p for p in pages}
    taxonomy_yaml = load_taxonomy_yaml(args.taxonomy)
    taxonomy_leaves = extract_taxonomy_leaves(taxonomy_yaml)
    gold_text = load_gold_example(args.gold)

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

    # Sequence tracking
    atom_seq = 1
    excerpt_seq = 1

    # Results accumulator
    all_results = []
    total_cost = {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0}

    print(f"=== Extraction Pipeline ===")
    print(f"Book: {args.book_title} ({args.book_id})")
    print(f"Science: {args.science}")
    print(f"Passages to process: {len(passage_indices)}")
    print(f"Taxonomy leaves: {len(taxonomy_leaves)}")
    print(f"Output: {outdir}")
    print(f"Model: {args.model}")
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
            gold_section = f"## Gold Example (for calibration — study the style and decisions)\n{gold_text}"

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
            with open(prompt_path, "w") as f:
                f.write(f"# SYSTEM\n\n{system}\n\n# USER\n\n{user}")
            print(f"  DRY RUN: prompt saved to {prompt_path}")
            print(f"  System prompt: {len(system)} chars")
            print(f"  User prompt: {len(user)} chars")
            continue

        # Call LLM
        try:
            t0 = time.time()
            response = call_llm(system, user, args.model, args.api_key)
            elapsed = time.time() - t0
            result = response["parsed"]
            in_tok = response["input_tokens"]
            out_tok = response["output_tokens"]

            # Cost estimate (Claude Sonnet pricing)
            cost = in_tok * 3 / 1_000_000 + out_tok * 15 / 1_000_000
            total_cost["input_tokens"] += in_tok
            total_cost["output_tokens"] += out_tok
            total_cost["total_cost"] += cost

            print(f"  LLM: {elapsed:.1f}s, {in_tok} in + {out_tok} out = ${cost:.4f}")

        except Exception as e:
            print(f"  ERROR: {e}")
            # Save error info
            err_path = outdir / f"{pid}_error.txt"
            with open(err_path, "w") as f:
                f.write(str(e))
            continue

        # Validate
        issues = validate_extraction(result, pid, taxonomy_leaves)
        status = "✅" if not issues else f"⚠️ {len(issues)} issues"
        print(f"  Atoms: {len(result.get('atoms', []))}, Excerpts: {len(result.get('excerpts', []))}, Validation: {status}")

        if issues:
            for iss in issues[:5]:
                print(f"    - {iss}")

        # Update sequence counters
        atom_seq += len(result.get("atoms", []))
        excerpt_seq += len(result.get("excerpts", []))
        excerpt_seq += len(result.get("footnote_excerpts", []))

        # Save raw result
        raw_path = outdir / f"{pid}_extraction.json"
        with open(raw_path, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # Generate review report
        review = generate_review_md(
            passage, result, issues,
            {"input_tokens": in_tok, "output_tokens": out_tok, "total_cost": cost},
        )
        review_path = outdir / f"{pid}_review.md"
        with open(review_path, "w") as f:
            f.write(review)

        all_results.append({
            "passage_id": pid,
            "atoms": len(result.get("atoms", [])),
            "excerpts": len(result.get("excerpts", [])),
            "footnote_excerpts": len(result.get("footnote_excerpts", [])),
            "issues": len(issues),
            "cost": cost,
        })

        # Rate limit courtesy
        time.sleep(1)

    # Summary
    print(f"\n=== Summary ===")
    total_atoms = sum(r["atoms"] for r in all_results)
    total_excerpts = sum(r["excerpts"] for r in all_results)
    total_issues = sum(r["issues"] for r in all_results)
    print(f"Passages processed: {len(all_results)}")
    print(f"Total atoms: {total_atoms}")
    print(f"Total excerpts: {total_excerpts}")
    print(f"Total issues: {total_issues}")
    print(f"Total cost: ${total_cost['total_cost']:.4f}")

    # Save summary
    summary_path = outdir / "extraction_summary.json"
    with open(summary_path, "w") as f:
        json.dump({
            "book_id": args.book_id,
            "book_title": args.book_title,
            "science": args.science,
            "model": args.model,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "passages": all_results,
            "totals": {
                "atoms": total_atoms,
                "excerpts": total_excerpts,
                "issues": total_issues,
                "cost": total_cost,
            },
        }, f, ensure_ascii=False, indent=2)

    print(f"\nResults saved to {outdir}/")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract atoms and excerpts from Stage 2 passages"
    )
    parser.add_argument("--passages", required=True, help="Path to passages.jsonl from Stage 2")
    parser.add_argument("--pages", required=True, help="Path to normalized pages.jsonl from Stage 1")
    parser.add_argument("--taxonomy", required=True, help="Path to taxonomy YAML")
    parser.add_argument("--book-id", required=True, help="Book identifier (e.g., qimlaa)")
    parser.add_argument("--book-title", required=True, help="Book title in Arabic")
    parser.add_argument("--science", required=True, help="Science: imlaa|sarf|nahw|balagha")
    parser.add_argument("--gold", default=None, help="Path to gold example JSON")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--api-key", default=None, help="Anthropic API key (or set ANTHROPIC_API_KEY)")
    parser.add_argument("--model", default="claude-sonnet-4-5-20250929", help="Model to use")
    parser.add_argument("--passage-ids", default=None, help="Comma-separated passage IDs to process")
    parser.add_argument("--dry-run", action="store_true", help="Save prompts without calling API")

    args = parser.parse_args()

    # Resolve API key
    if not args.api_key:
        args.api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not args.api_key and not args.dry_run:
        print("ERROR: No API key provided. Use --api-key or set ANTHROPIC_API_KEY")
        sys.exit(1)

    run_extraction(args)


if __name__ == "__main__":
    main()
