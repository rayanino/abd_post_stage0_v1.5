#!/usr/bin/env python3
"""
Cross-Validation Layers
=======================
Content-aware validation that catches errors requiring understanding,
complementing existing algorithmic checks (schema, character counts).

Three validation types:
1. Placement cross-validation — independent LLM verifies excerpt placement
2. Self-containment validation — algorithmic + LLM check of assembled excerpts
3. Cross-book consistency — topic coherence at multi-book leaf nodes

Usage:
    # Placement cross-validation
    python tools/cross_validate.py placement \\
        --extraction-dir output/imlaa_extraction \\
        --taxonomy taxonomy/imlaa/imlaa_v1_0.yaml \\
        --science imlaa \\
        --output-dir output/imlaa_validation \\
        --model claude-sonnet-4-5-20250929

    # Self-containment validation
    python tools/cross_validate.py self-containment \\
        --assembly-dir output/imlaa_assembled \\
        --output-dir output/imlaa_validation \\
        [--model claude-sonnet-4-5-20250929]

    # Cross-book consistency
    python tools/cross_validate.py cross-book \\
        --assembly-dir output/imlaa_assembled \\
        --output-dir output/imlaa_validation \\
        --model claude-sonnet-4-5-20250929
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tools.assemble_excerpts import (
    TaxonomyNodeInfo,
    build_atoms_index,
    load_extraction_files,
    parse_taxonomy_yaml,
    resolve_atom_texts,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLACEMENT_SYSTEM_PROMPT = """\
You are a taxonomy placement expert for classical Arabic {science} texts.
You will be given an excerpt's Arabic text and a taxonomy tree structure.
Your task: independently determine which leaf node this excerpt belongs at.

IMPORTANT: You must choose from the EXISTING leaf nodes only.
Do not invent new nodes. If no leaf is a good fit, choose the closest one
and mark your confidence as "uncertain".

Respond in JSON:
{{
  "chosen_node_id": "the_leaf_node_id",
  "chosen_node_path": "path > to > leaf",
  "confidence": "certain" | "likely" | "uncertain",
  "reasoning": "Brief Arabic linguistic reasoning for your choice"
}}
"""

PLACEMENT_USER_PROMPT = """\
=== EXCERPT ===
Excerpt ID: {excerpt_id}
Title: {excerpt_title}
Text:
{excerpt_text}

=== TAXONOMY (leaf nodes) ===
{taxonomy_leaves}

Which leaf node does this excerpt belong at?
"""

SELF_CONTAINMENT_SYSTEM_PROMPT = """\
You are reviewing an assembled excerpt file for self-containment.
A self-contained excerpt must be independently understandable by a reader
who has no access to other files.

Check whether:
1. The Arabic text is present and non-trivial (not just a heading)
2. The author/book context is identifiable
3. The scholarly tradition context is present (where applicable)
4. The topic is clear from the taxonomy path and content
5. The text makes sense as a standalone teaching unit

Respond in JSON:
{{
  "is_self_contained": true | false,
  "issues": ["list of specific issues found"],
  "confidence": "certain" | "likely" | "uncertain"
}}
"""

SELF_CONTAINMENT_USER_PROMPT = """\
=== ASSEMBLED EXCERPT ===
{excerpt_json}

Is this excerpt self-contained and independently understandable?
"""

CROSS_BOOK_SYSTEM_PROMPT = """\
You are checking topic coherence for excerpts at a taxonomy leaf node.
All excerpts at the same leaf should discuss the same topic, even though
they come from different books by different authors.

You will see multiple excerpts placed at the same leaf node.
Determine if they are all about the same topic, or if any are misplaced.

Respond in JSON:
{{
  "is_coherent": true | false,
  "outlier_excerpt_ids": ["IDs of excerpts that seem misplaced"],
  "topic_description": "Brief description of what the leaf should cover",
  "reasoning": "Explanation of coherence assessment"
}}
"""

CROSS_BOOK_USER_PROMPT = """\
=== LEAF NODE ===
Node ID: {node_id}
Path: {node_path}

=== EXCERPTS AT THIS NODE ===
{excerpts_block}

Are all these excerpts about the same topic?
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_taxonomy_leaves(taxonomy_map: dict[str, TaxonomyNodeInfo]) -> str:
    """Format leaf nodes as a readable list for the LLM."""
    lines = []
    for nid, info in sorted(taxonomy_map.items()):
        if info.is_leaf:
            path = " > ".join(info.path_titles)
            lines.append(f"- {nid}: {path}")
    return "\n".join(lines)


def _resolve_excerpt_text(
    excerpt: dict,
    atoms_index: dict[str, dict],
) -> str:
    """Resolve an excerpt's full Arabic text from atom references."""
    parts = []
    for atom_id in excerpt.get("context_atoms", []):
        atom = atoms_index.get(atom_id if isinstance(atom_id, str) else atom_id.get("atom_id", ""))
        if atom:
            parts.append(atom.get("text", ""))

    for atom_id in excerpt.get("core_atoms", []):
        atom = atoms_index.get(atom_id if isinstance(atom_id, str) else atom_id.get("atom_id", ""))
        if atom:
            parts.append(atom.get("text", ""))

    return "\n".join(parts)


def _call_llm_or_mock(
    system: str,
    user: str,
    model: str,
    api_key: str,
    openrouter_key: str | None,
    openai_key: str | None,
    call_llm_fn=None,
) -> dict | None:
    """Call LLM with fallback to mock for testing."""
    if call_llm_fn is not None:
        try:
            return call_llm_fn(system, user, model, api_key, openrouter_key, openai_key)
        except Exception as e:
            print(f"  ERROR: LLM call failed: {e}", file=sys.stderr)
            return None

    try:
        from tools.extract_passages import call_llm_dispatch
        return call_llm_dispatch(system, user, model, api_key, openrouter_key, openai_key)
    except Exception as e:
        print(f"  ERROR: LLM call failed: {e}", file=sys.stderr)
        return None


def _parse_llm_json(response: dict | None) -> dict | None:
    """Extract parsed JSON from an LLM response dict."""
    if response is None:
        return None
    parsed = response.get("parsed")
    if parsed is not None:
        return parsed
    raw = response.get("raw_text", "")
    if not raw:
        return None
    # Try to parse raw text as JSON
    raw = raw.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# 1. Placement cross-validation
# ---------------------------------------------------------------------------

def validate_placement(
    extraction_dir: str,
    taxonomy_path: str,
    science: str,
    output_dir: str,
    model: str = "claude-sonnet-4-5-20250929",
    api_key: str | None = None,
    openrouter_key: str | None = None,
    openai_key: str | None = None,
    call_llm_fn=None,
    excerpt_ids: list[str] | None = None,
) -> dict:
    """Run placement cross-validation on extraction output.

    For each excerpt, an independent LLM call reads the excerpt text and
    taxonomy, then determines where it should be placed. Disagreements
    with the extraction placement are flagged.

    Returns structured report dict.
    """
    # Load data
    taxonomy_map = parse_taxonomy_yaml(taxonomy_path, science)
    extraction_data = load_extraction_files(extraction_dir)
    if not extraction_data:
        return {"status": "no_data", "results": []}

    # Build atom indexes
    atoms_indexes: dict[str, dict[str, dict]] = {}
    for passage in extraction_data:
        pid = passage["passage_id"]
        atoms_indexes[pid] = build_atoms_index(passage["atoms"])

    # Format taxonomy leaves for prompt
    leaves_text = _format_taxonomy_leaves(taxonomy_map)

    effective_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    effective_openrouter = openrouter_key or os.environ.get("OPENROUTER_API_KEY")
    effective_openai = openai_key or os.environ.get("OPENAI_API_KEY")

    results = []
    agreements = 0
    disagreements = 0

    for passage in extraction_data:
        pid = passage["passage_id"]
        ai = atoms_indexes.get(pid, {})

        for excerpt in passage.get("excerpts", []) + passage.get("footnote_excerpts", []):
            eid = excerpt.get("excerpt_id", "")
            if excerpt_ids and eid not in excerpt_ids:
                continue

            original_node = excerpt.get("taxonomy_node_id", "")
            excerpt_text = _resolve_excerpt_text(excerpt, ai)
            if not excerpt_text.strip():
                continue

            system = PLACEMENT_SYSTEM_PROMPT.format(science=science)
            user = PLACEMENT_USER_PROMPT.format(
                excerpt_id=eid,
                excerpt_title=excerpt.get("excerpt_title", ""),
                excerpt_text=excerpt_text[:6000],
                taxonomy_leaves=leaves_text[:8000],
            )

            response = _call_llm_or_mock(
                system, user, model,
                effective_key, effective_openrouter, effective_openai,
                call_llm_fn=call_llm_fn,
            )
            parsed = _parse_llm_json(response)

            if parsed is None:
                results.append({
                    "excerpt_id": eid,
                    "passage_id": pid,
                    "original_node": original_node,
                    "validation_node": None,
                    "status": "llm_error",
                })
                continue

            validation_node = parsed.get("chosen_node_id", "")
            confidence = parsed.get("confidence", "uncertain")
            reasoning = parsed.get("reasoning", "")

            if validation_node == original_node:
                status = "agreement"
                agreements += 1
            else:
                status = "disagreement"
                disagreements += 1

            results.append({
                "excerpt_id": eid,
                "passage_id": pid,
                "original_node": original_node,
                "validation_node": validation_node,
                "confidence": confidence,
                "reasoning": reasoning,
                "status": status,
            })

    report = {
        "validation_type": "placement",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "science": science,
        "total_excerpts": len(results),
        "agreements": agreements,
        "disagreements": disagreements,
        "error_count": sum(1 for r in results if r["status"] == "llm_error"),
        "results": results,
    }

    # Save report
    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        report_path = out_path / "placement_validation.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    return report


# ---------------------------------------------------------------------------
# 2. Self-containment validation
# ---------------------------------------------------------------------------

def _check_fields_algorithmic(excerpt_data: dict) -> list[str]:
    """Algorithmic checks for self-containment: required fields non-empty."""
    issues = []

    # Check core text presence
    text = excerpt_data.get("full_text", "") or excerpt_data.get("core_text", "")
    if not text or len(text.strip()) < 20:
        issues.append("Missing or trivially short Arabic text")

    # Check author/book context
    if not excerpt_data.get("book_title"):
        issues.append("Missing book_title")
    if not excerpt_data.get("author_name") and not excerpt_data.get("book_title"):
        issues.append("Missing author identification")

    # Check taxonomy context
    if not excerpt_data.get("taxonomy_path"):
        issues.append("Missing taxonomy_path")
    if not excerpt_data.get("taxonomy_node_id"):
        issues.append("Missing taxonomy_node_id")

    # Check source reference
    if not excerpt_data.get("source_pages") and not excerpt_data.get("page_range"):
        issues.append("Missing source page reference")

    # Check excerpt ID
    if not excerpt_data.get("excerpt_id"):
        issues.append("Missing excerpt_id")

    return issues


def validate_self_containment(
    assembly_dir: str,
    output_dir: str,
    model: str | None = None,
    api_key: str | None = None,
    openrouter_key: str | None = None,
    openai_key: str | None = None,
    call_llm_fn=None,
) -> dict:
    """Run self-containment validation on assembled excerpt files.

    First runs algorithmic checks (required fields non-empty).
    If a model is specified, also runs LLM-based checks for standalone
    readability.

    Returns structured report dict.
    """
    assembly_path = Path(assembly_dir)
    if not assembly_path.exists():
        return {"status": "no_data", "results": []}

    effective_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    effective_openrouter = openrouter_key or os.environ.get("OPENROUTER_API_KEY")
    effective_openai = openai_key or os.environ.get("OPENAI_API_KEY")

    results = []
    pass_count = 0
    fail_count = 0

    # Find all excerpt JSON files in assembly directory (recursive)
    excerpt_files = sorted(assembly_path.rglob("*.json"))

    for excerpt_file in excerpt_files:
        # Skip non-excerpt files (manifests, metadata, etc.)
        try:
            with open(excerpt_file, "r", encoding="utf-8") as f:
                data = json.loads(f.read())
        except (json.JSONDecodeError, OSError):
            continue

        # Must have excerpt_id to be an excerpt file
        eid = data.get("excerpt_id", "")
        if not eid:
            continue

        # Algorithmic checks
        algo_issues = _check_fields_algorithmic(data)

        # LLM check (if model specified)
        llm_issues = []
        llm_self_contained = None
        if model and not algo_issues:
            # Only run LLM check if algorithmic checks pass
            system = SELF_CONTAINMENT_SYSTEM_PROMPT
            excerpt_json_str = json.dumps(data, ensure_ascii=False, indent=2)
            if len(excerpt_json_str) > 8000:
                excerpt_json_str = excerpt_json_str[:8000] + "\n... (truncated)"
            user = SELF_CONTAINMENT_USER_PROMPT.format(
                excerpt_json=excerpt_json_str,
            )

            response = _call_llm_or_mock(
                system, user, model,
                effective_key, effective_openrouter, effective_openai,
                call_llm_fn=call_llm_fn,
            )
            parsed = _parse_llm_json(response)
            if parsed:
                llm_self_contained = parsed.get("is_self_contained", True)
                llm_issues = parsed.get("issues", [])

        all_issues = algo_issues + llm_issues
        status = "fail" if all_issues else "pass"

        if status == "pass":
            pass_count += 1
        else:
            fail_count += 1

        results.append({
            "excerpt_id": eid,
            "file_path": str(excerpt_file),
            "algorithmic_issues": algo_issues,
            "llm_issues": llm_issues,
            "llm_self_contained": llm_self_contained,
            "status": status,
        })

    report = {
        "validation_type": "self_containment",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model or "algorithmic_only",
        "total_excerpts": len(results),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "results": results,
    }

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        report_path = out_path / "self_containment_validation.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    return report


# ---------------------------------------------------------------------------
# 3. Cross-book consistency
# ---------------------------------------------------------------------------

def validate_cross_book_consistency(
    assembly_dir: str,
    output_dir: str,
    model: str = "claude-sonnet-4-5-20250929",
    api_key: str | None = None,
    openrouter_key: str | None = None,
    openai_key: str | None = None,
    call_llm_fn=None,
) -> dict:
    """Check topic coherence at leaf nodes with excerpts from multiple books.

    For each leaf node that has 2+ excerpts from different books,
    an LLM checks whether they're all about the same topic.

    Returns structured report dict.
    """
    assembly_path = Path(assembly_dir)
    if not assembly_path.exists():
        return {"status": "no_data", "results": []}

    effective_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    effective_openrouter = openrouter_key or os.environ.get("OPENROUTER_API_KEY")
    effective_openai = openai_key or os.environ.get("OPENAI_API_KEY")

    # Collect excerpts by leaf node
    node_excerpts: dict[str, list[dict]] = defaultdict(list)

    for excerpt_file in sorted(assembly_path.rglob("*.json")):
        try:
            with open(excerpt_file, "r", encoding="utf-8") as f:
                data = json.loads(f.read())
        except (json.JSONDecodeError, OSError):
            continue

        eid = data.get("excerpt_id", "")
        node_id = data.get("taxonomy_node_id", "")
        if eid and node_id:
            data["_file_path"] = str(excerpt_file)
            node_excerpts[node_id].append(data)

    # Filter to nodes with 2+ excerpts from different books
    multi_book_nodes = {}
    for node_id, excerpts in node_excerpts.items():
        book_ids = set(e.get("book_id", "") for e in excerpts)
        if len(book_ids) >= 2:
            multi_book_nodes[node_id] = excerpts

    results = []
    coherent_count = 0
    incoherent_count = 0

    for node_id, excerpts in multi_book_nodes.items():
        # Build excerpts block for prompt
        excerpts_block_parts = []
        for e in excerpts:
            text = e.get("full_text", "") or e.get("core_text", "")
            if not text:
                text = "(no text available)"
            excerpts_block_parts.append(
                f"--- Excerpt {e.get('excerpt_id', '?')} "
                f"(Book: {e.get('book_title', '?')}) ---\n{text[:2000]}"
            )
        excerpts_block = "\n\n".join(excerpts_block_parts)

        # Get node path
        node_path = excerpts[0].get("taxonomy_path", node_id)

        system = CROSS_BOOK_SYSTEM_PROMPT
        user = CROSS_BOOK_USER_PROMPT.format(
            node_id=node_id,
            node_path=node_path,
            excerpts_block=excerpts_block[:8000],
        )

        response = _call_llm_or_mock(
            system, user, model,
            effective_key, effective_openrouter, effective_openai,
            call_llm_fn=call_llm_fn,
        )
        parsed = _parse_llm_json(response)

        if parsed is None:
            results.append({
                "node_id": node_id,
                "excerpt_count": len(excerpts),
                "book_count": len(set(e.get("book_id", "") for e in excerpts)),
                "status": "llm_error",
            })
            continue

        is_coherent = parsed.get("is_coherent", True)
        outliers = parsed.get("outlier_excerpt_ids", [])

        if is_coherent:
            coherent_count += 1
            status = "coherent"
        else:
            incoherent_count += 1
            status = "incoherent"

        results.append({
            "node_id": node_id,
            "node_path": node_path,
            "excerpt_count": len(excerpts),
            "book_count": len(set(e.get("book_id", "") for e in excerpts)),
            "excerpt_ids": [e.get("excerpt_id", "") for e in excerpts],
            "is_coherent": is_coherent,
            "outlier_excerpt_ids": outliers,
            "topic_description": parsed.get("topic_description", ""),
            "reasoning": parsed.get("reasoning", ""),
            "status": status,
        })

    report = {
        "validation_type": "cross_book_consistency",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "total_nodes_checked": len(results),
        "coherent_count": coherent_count,
        "incoherent_count": incoherent_count,
        "error_count": sum(1 for r in results if r["status"] == "llm_error"),
        "results": results,
    }

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        report_path = out_path / "cross_book_validation.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Cross-validation layers: placement, self-containment, cross-book.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Validation type")

    # --- placement ---
    pl_parser = subparsers.add_parser(
        "placement", help="Placement cross-validation",
    )
    pl_parser.add_argument("--extraction-dir", required=True)
    pl_parser.add_argument("--taxonomy", required=True)
    pl_parser.add_argument("--science", required=True)
    pl_parser.add_argument("--output-dir", required=True)
    pl_parser.add_argument("--model", default="claude-sonnet-4-5-20250929")
    pl_parser.add_argument("--api-key", default=None)
    pl_parser.add_argument("--openai-key", default=None)
    pl_parser.add_argument("--openrouter-key", default=None)
    pl_parser.add_argument("--excerpt-ids", default=None,
                           help="Comma-separated excerpt IDs to validate")

    # --- self-containment ---
    sc_parser = subparsers.add_parser(
        "self-containment", help="Self-containment validation",
    )
    sc_parser.add_argument("--assembly-dir", required=True)
    sc_parser.add_argument("--output-dir", required=True)
    sc_parser.add_argument("--model", default=None,
                           help="Model for LLM-based check (optional, algorithmic-only if omitted)")
    sc_parser.add_argument("--api-key", default=None)
    sc_parser.add_argument("--openai-key", default=None)
    sc_parser.add_argument("--openrouter-key", default=None)

    # --- cross-book ---
    cb_parser = subparsers.add_parser(
        "cross-book", help="Cross-book consistency validation",
    )
    cb_parser.add_argument("--assembly-dir", required=True)
    cb_parser.add_argument("--output-dir", required=True)
    cb_parser.add_argument("--model", default="claude-sonnet-4-5-20250929")
    cb_parser.add_argument("--api-key", default=None)
    cb_parser.add_argument("--openai-key", default=None)
    cb_parser.add_argument("--openrouter-key", default=None)

    args = parser.parse_args()

    if args.command == "placement":
        excerpt_ids = None
        if args.excerpt_ids:
            excerpt_ids = [e.strip() for e in args.excerpt_ids.split(",")]
        report = validate_placement(
            extraction_dir=args.extraction_dir,
            taxonomy_path=args.taxonomy,
            science=args.science,
            output_dir=args.output_dir,
            model=args.model,
            api_key=args.api_key,
            openrouter_key=args.openrouter_key,
            openai_key=args.openai_key,
            excerpt_ids=excerpt_ids,
        )
        if report.get("status") == "no_data":
            print("Placement validation: no extraction data found")
        else:
            print(f"Placement validation: {report['agreements']} agreements, "
                  f"{report['disagreements']} disagreements out of "
                  f"{report['total_excerpts']} excerpts")

    elif args.command == "self-containment":
        report = validate_self_containment(
            assembly_dir=args.assembly_dir,
            output_dir=args.output_dir,
            model=args.model,
            api_key=args.api_key,
            openrouter_key=args.openrouter_key,
            openai_key=args.openai_key,
        )
        if report.get("status") == "no_data":
            print("Self-containment: no assembled excerpts found")
        else:
            print(f"Self-containment: {report['pass_count']} pass, "
                  f"{report['fail_count']} fail out of "
                  f"{report['total_excerpts']} excerpts")

    elif args.command == "cross-book":
        report = validate_cross_book_consistency(
            assembly_dir=args.assembly_dir,
            output_dir=args.output_dir,
            model=args.model,
            api_key=args.api_key,
            openrouter_key=args.openrouter_key,
            openai_key=args.openai_key,
        )
        if report.get("status") == "no_data":
            print("Cross-book consistency: no assembled excerpts found")
        else:
            print(f"Cross-book consistency: {report['coherent_count']} coherent, "
                  f"{report['incoherent_count']} incoherent out of "
                  f"{report['total_nodes_checked']} nodes")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
