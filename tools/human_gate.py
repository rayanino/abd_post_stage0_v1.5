#!/usr/bin/env python3
"""
Human Gate Infrastructure
=========================
Correction persistence, correction replay, pattern detection,
and gate checkpoints for human review of extraction results.

Usage:
    # Record a correction
    python tools/human_gate.py record-correction \\
        --extraction-dir output/imlaa_extraction \\
        --excerpt-id E001 \\
        --correction-type placement \\
        --correction '{"new_taxonomy_node_id": "hamzat_alwasl"}' \\
        --reason "Excerpt discusses wasl hamza, not hamza definition" \\
        --corrections-file corrections/imlaa_corrections.jsonl

    # Replay a correction (re-extract with correction as context)
    python tools/human_gate.py replay-correction \\
        --correction-id CORR-001 \\
        --corrections-file corrections/imlaa_corrections.jsonl \\
        --passages books/imla/stage2_output/passages.jsonl \\
        --pages books/imla/stage1_output/pages.jsonl \\
        --taxonomy taxonomy/imlaa/imlaa_v1_0.yaml \\
        --book-id qimlaa --science imlaa \\
        --output-dir output/imlaa_replay

    # Detect patterns in corrections
    python tools/human_gate.py detect-patterns \\
        --corrections-file corrections/imlaa_corrections.jsonl \\
        --output-dir output/imlaa_patterns

    # Manage gate checkpoints
    python tools/human_gate.py checkpoint \\
        --extraction-dir output/imlaa_extraction \\
        --action status|approve|reject|reset \\
        --excerpt-ids E001,E002
"""

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_CORRECTION_TYPES = {
    "placement",       # excerpt moved to different taxonomy node
    "boundary",        # excerpt atom boundaries changed
    "attribution",     # madhab/school/author attribution changed
    "rejection",       # excerpt rejected entirely
    "merge",           # two excerpts merged into one
    "split",           # one excerpt split into two
    "metadata",        # metadata fields corrected (title, etc.)
}

VALID_REVIEW_STATES = {
    "pending",         # not yet reviewed
    "approved",        # human approved
    "rejected",        # human rejected
    "corrected",       # human corrected (correction record exists)
}


# ---------------------------------------------------------------------------
# Correction cycle persistence
# ---------------------------------------------------------------------------

def create_correction_record(
    excerpt_id: str,
    correction_type: str,
    original_output: dict,
    human_correction: dict,
    reason: str = "",
    passage_id: str = "",
    book_id: str = "",
    science: str = "",
    model: str = "",
    correction_id: str = "",
) -> dict:
    """Create a structured correction record.

    Args:
        excerpt_id: ID of the affected excerpt.
        correction_type: One of VALID_CORRECTION_TYPES.
        original_output: What the system produced (excerpt dict or subset).
        human_correction: What the human corrected it to.
        reason: Optional human explanation of why the correction was made.
        passage_id: Source passage ID.
        book_id: Source book ID.
        science: Science name.
        model: Model that produced the original output.
        correction_id: Optional custom ID; auto-generated if empty.

    Returns:
        Structured correction record dict.
    """
    if correction_type not in VALID_CORRECTION_TYPES:
        raise ValueError(
            f"Invalid correction_type '{correction_type}'. "
            f"Must be one of: {sorted(VALID_CORRECTION_TYPES)}"
        )

    now = datetime.now(timezone.utc)
    if not correction_id:
        ts = now.strftime("%Y%m%d%H%M%S%f")
        correction_id = f"CORR-{ts}-{excerpt_id}"

    return {
        "correction_id": correction_id,
        "timestamp": now.isoformat(),
        "excerpt_id": excerpt_id,
        "passage_id": passage_id,
        "book_id": book_id,
        "science": science,
        "model": model,
        "correction_type": correction_type,
        "original_output": original_output,
        "human_correction": human_correction,
        "reason": reason,
    }


def save_correction(
    record: dict,
    corrections_file: str,
) -> str:
    """Append a correction record to the corrections JSONL file.

    Creates the file and parent directories if they don't exist.
    Returns the path to the corrections file.
    """
    path = Path(corrections_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return str(path)


def load_corrections(corrections_file: str) -> list[dict]:
    """Load all corrections from a JSONL file.

    Returns empty list if file doesn't exist.
    """
    path = Path(corrections_file)
    if not path.exists():
        return []

    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  WARNING: Skipping malformed line {line_num} in "
                      f"{corrections_file}: {e}", file=sys.stderr)
    return records


def find_correction_by_id(
    corrections: list[dict],
    correction_id: str,
) -> dict | None:
    """Find a correction record by its ID."""
    for rec in corrections:
        if rec.get("correction_id") == correction_id:
            return rec
    return None


def find_corrections_for_excerpt(
    corrections: list[dict],
    excerpt_id: str,
) -> list[dict]:
    """Find all corrections for a given excerpt ID."""
    return [r for r in corrections if r.get("excerpt_id") == excerpt_id]


# ---------------------------------------------------------------------------
# Correction replay
# ---------------------------------------------------------------------------

def build_replay_context(correction: dict) -> str:
    """Build a context string from a correction record for re-extraction.

    This context is injected into the extraction prompt so the model
    knows about the human correction.
    """
    ctype = correction.get("correction_type", "unknown")
    excerpt_id = correction.get("excerpt_id", "unknown")
    reason = correction.get("reason", "")

    lines = [
        f"HUMAN CORRECTION for excerpt {excerpt_id}:",
        f"  Correction type: {ctype}",
    ]

    if reason:
        lines.append(f"  Reason: {reason}")

    hc = correction.get("human_correction", {})

    if ctype == "placement":
        new_node = hc.get("new_taxonomy_node_id", "")
        old_node = correction.get("original_output", {}).get("taxonomy_node_id", "")
        if old_node:
            lines.append(f"  Original placement: {old_node}")
        if new_node:
            lines.append(f"  Corrected placement: {new_node}")

    elif ctype == "boundary":
        new_core = hc.get("core_atoms", [])
        new_context = hc.get("context_atoms", [])
        if new_core:
            lines.append(f"  Corrected core atoms: {new_core}")
        if new_context:
            lines.append(f"  Corrected context atoms: {new_context}")

    elif ctype == "attribution":
        for key in ("madhab", "school", "author"):
            if key in hc:
                lines.append(f"  Corrected {key}: {hc[key]}")

    elif ctype == "rejection":
        lines.append("  This excerpt was REJECTED by the human reviewer.")
        if hc.get("rejection_reason"):
            lines.append(f"  Rejection reason: {hc['rejection_reason']}")

    elif ctype == "merge":
        merge_with = hc.get("merge_with_excerpt_id", "")
        if merge_with:
            lines.append(f"  Merged with: {merge_with}")

    elif ctype == "split":
        split_into = hc.get("split_excerpts", [])
        if split_into:
            lines.append(f"  Split into {len(split_into)} excerpts")

    return "\n".join(lines)


def replay_correction(
    correction: dict,
    passages_file: str,
    pages_file: str,
    taxonomy_path: str,
    book_id: str,
    science: str,
    output_dir: str,
    model: str = "claude-sonnet-4-5-20250929",
    api_key: str | None = None,
    openai_key: str | None = None,
    openrouter_key: str | None = None,
    call_extract_fn=None,
) -> dict:
    """Re-extract the affected passage with correction context.

    This function calls the extraction pipeline on the specific passage
    that the correction applies to, injecting the correction as additional
    context in the extraction prompt.

    Args:
        correction: The correction record dict.
        passages_file: Path to passages.jsonl.
        pages_file: Path to pages.jsonl.
        taxonomy_path: Path to taxonomy YAML.
        book_id: Book ID.
        science: Science name.
        output_dir: Output directory for replay results.
        model: Model to use for re-extraction.
        api_key: Anthropic API key.
        openai_key: OpenAI API key.
        openrouter_key: OpenRouter API key.
        call_extract_fn: Injectable extraction function for testing.

    Returns:
        Dict with replay results.
    """
    passage_id = correction.get("passage_id", "")
    if not passage_id:
        return {
            "status": "error",
            "error": "Correction record has no passage_id",
        }

    # Build correction context
    context = build_replay_context(correction)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if call_extract_fn is not None:
        # Testing path: use injected function
        result = call_extract_fn(
            passage_id=passage_id,
            correction_context=context,
            model=model,
        )
    else:
        # Real path: call extract_passages
        # Import here to avoid circular imports
        try:
            from tools.extract_passages import run_extraction
        except ImportError:
            return {
                "status": "error",
                "error": "Could not import extract_passages",
            }

        effective_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        effective_openai = openai_key or os.environ.get("OPENAI_API_KEY")
        effective_openrouter = openrouter_key or os.environ.get("OPENROUTER_API_KEY")

        # run_extraction expects an argparse Namespace, not keyword args
        import argparse
        extraction_args = argparse.Namespace(
            passages=passages_file,
            pages=pages_file,
            taxonomy=taxonomy_path,
            book_id=book_id,
            book_title="",
            science=science,
            output_dir=str(out_path),
            model=model,
            api_key=effective_key,
            openai_key=effective_openai,
            openrouter_key=effective_openrouter,
            passage_ids=passage_id,  # comma-separated string, not list
            gold=None,
            dry_run=False,
            verbose=False,
            consensus_mode=False,
            model_list=[model],
            arbiter_model=None,
            correction_context=context,
        )
        result = run_extraction(extraction_args)

    # Save replay metadata
    replay_meta = {
        "correction_id": correction.get("correction_id"),
        "passage_id": passage_id,
        "correction_context": context,
        "model": model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result_status": result.get("status", "unknown") if isinstance(result, dict) else "completed",
    }
    meta_path = out_path / f"replay_{correction.get('correction_id', 'unknown')}.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(replay_meta, f, ensure_ascii=False, indent=2)

    return {
        "status": "completed",
        "correction_id": correction.get("correction_id"),
        "passage_id": passage_id,
        "replay_metadata_path": str(meta_path),
        "output_dir": str(out_path),
    }


# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------

def detect_patterns(
    corrections: list[dict],
    min_count: int = 2,
) -> dict:
    """Analyze corrections for recurring patterns.

    Args:
        corrections: List of correction records.
        min_count: Minimum occurrences to be reported as a pattern.

    Returns:
        Structured pattern report dict.
    """
    if not corrections:
        return {
            "total_corrections": 0,
            "patterns": [],
            "summary": "No corrections to analyze.",
        }

    # Count by type
    type_counts = Counter(r.get("correction_type", "unknown") for r in corrections)

    # Count by taxonomy node (for placement corrections)
    node_counts = Counter()
    for r in corrections:
        if r.get("correction_type") == "placement":
            orig_node = r.get("original_output", {}).get("taxonomy_node_id", "")
            if orig_node:
                node_counts[orig_node] += 1

    # Count by model
    model_counts = Counter(r.get("model", "unknown") for r in corrections)

    # Count by science
    science_counts = Counter(r.get("science", "unknown") for r in corrections)

    # Count by passage
    passage_counts = Counter(r.get("passage_id", "unknown") for r in corrections)

    # Build patterns list
    patterns = []

    # Type patterns
    for ctype, count in type_counts.most_common():
        if count >= min_count:
            patterns.append({
                "pattern_type": "correction_type_frequency",
                "key": ctype,
                "count": count,
                "percentage": round(count / len(corrections) * 100, 1),
                "description": (
                    f"'{ctype}' corrections appear {count} times "
                    f"({count}/{len(corrections)} = "
                    f"{count / len(corrections) * 100:.0f}%)"
                ),
            })

    # Node patterns (recurring misplacements)
    for node_id, count in node_counts.most_common():
        if count >= min_count and node_id:
            patterns.append({
                "pattern_type": "recurring_misplacement",
                "key": node_id,
                "count": count,
                "description": (
                    f"Node '{node_id}' has {count} placement corrections — "
                    f"may indicate ambiguous node definition"
                ),
            })

    # Model patterns
    for model_name, count in model_counts.most_common():
        if count >= min_count and model_name != "unknown":
            pct = round(count / len(corrections) * 100, 1)
            patterns.append({
                "pattern_type": "model_error_rate",
                "key": model_name,
                "count": count,
                "percentage": pct,
                "description": (
                    f"Model '{model_name}' responsible for {count} corrections ({pct}%)"
                ),
            })

    # Passage patterns (some passages harder than others)
    for pid, count in passage_counts.most_common():
        if count >= min_count and pid != "unknown":
            patterns.append({
                "pattern_type": "passage_difficulty",
                "key": pid,
                "count": count,
                "description": (
                    f"Passage '{pid}' required {count} corrections — "
                    f"may be difficult for extraction"
                ),
            })

    # Build summary
    summary_parts = [
        f"{len(corrections)} total corrections analyzed.",
    ]
    if type_counts:
        top_type = type_counts.most_common(1)[0]
        summary_parts.append(
            f"Most common: '{top_type[0]}' ({top_type[1]} occurrences)."
        )
    if node_counts:
        top_node = node_counts.most_common(1)[0]
        summary_parts.append(
            f"Most corrected node: '{top_node[0]}' ({top_node[1]} times)."
        )

    return {
        "total_corrections": len(corrections),
        "correction_types": dict(type_counts),
        "patterns": patterns,
        "summary": " ".join(summary_parts),
        "by_model": dict(model_counts),
        "by_science": dict(science_counts),
        "by_passage": dict(passage_counts),
        "by_node": dict(node_counts),
    }


def save_pattern_report(
    report: dict,
    output_dir: str,
) -> str:
    """Save pattern report as JSON and human-readable markdown.

    Returns path to the JSON report.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # JSON report
    json_path = out_path / "correction_patterns.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Markdown report
    md_lines = [
        "# Correction Pattern Report",
        "",
        f"**Total corrections:** {report['total_corrections']}",
        "",
        f"**Summary:** {report.get('summary', '')}",
        "",
    ]

    patterns = report.get("patterns", [])
    if patterns:
        md_lines.append("## Detected Patterns")
        md_lines.append("")
        for i, p in enumerate(patterns, 1):
            md_lines.append(f"### Pattern {i}: {p['pattern_type']}")
            md_lines.append(f"- **Key:** {p['key']}")
            md_lines.append(f"- **Count:** {p['count']}")
            md_lines.append(f"- **Description:** {p['description']}")
            md_lines.append("")
    else:
        md_lines.append("No recurring patterns detected.")
        md_lines.append("")

    # Type breakdown
    type_counts = report.get("correction_types", {})
    if type_counts:
        md_lines.append("## Correction Type Breakdown")
        md_lines.append("")
        md_lines.append("| Type | Count |")
        md_lines.append("|------|-------|")
        for ctype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            md_lines.append(f"| {ctype} | {count} |")
        md_lines.append("")

    md_path = out_path / "correction_patterns.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    return str(json_path)


# ---------------------------------------------------------------------------
# Gate checkpoints
# ---------------------------------------------------------------------------

def load_checkpoint(extraction_dir: str) -> dict:
    """Load the gate checkpoint state for an extraction directory.

    The checkpoint file lives at {extraction_dir}/gate_checkpoint.json.
    Returns empty state if no checkpoint exists.
    """
    cp_path = Path(extraction_dir) / "gate_checkpoint.json"
    default = {"version": "0.1", "excerpts": {}}
    if not cp_path.exists():
        return default
    with open(cp_path, "r", encoding="utf-8") as f:
        data = json.loads(f.read())
    if not isinstance(data, dict) or not isinstance(data.get("excerpts"), dict):
        print(f"  WARNING: corrupt gate_checkpoint.json — resetting to default",
              file=sys.stderr)
        return default
    return data


def save_checkpoint(extraction_dir: str, checkpoint: dict) -> str:
    """Save the gate checkpoint state.

    Returns path to the checkpoint file.
    """
    cp_path = Path(extraction_dir) / "gate_checkpoint.json"
    Path(extraction_dir).mkdir(parents=True, exist_ok=True)
    with open(cp_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    return str(cp_path)


def update_checkpoint(
    checkpoint: dict,
    excerpt_ids: list[str],
    state: str,
    reviewer: str = "",
) -> dict:
    """Update the review state of specific excerpts in the checkpoint.

    Args:
        checkpoint: Current checkpoint dict.
        excerpt_ids: Excerpt IDs to update.
        state: New state (one of VALID_REVIEW_STATES).
        reviewer: Optional reviewer identifier.

    Returns:
        Updated checkpoint dict.
    """
    if state not in VALID_REVIEW_STATES:
        raise ValueError(
            f"Invalid review state '{state}'. "
            f"Must be one of: {sorted(VALID_REVIEW_STATES)}"
        )

    for eid in excerpt_ids:
        checkpoint["excerpts"][eid] = {
            "state": state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reviewer": reviewer,
        }

    return checkpoint


def get_checkpoint_summary(checkpoint: dict) -> dict:
    """Get a summary of checkpoint states.

    Returns counts by state and list of pending excerpt IDs.
    """
    state_counts = Counter()
    pending_ids = []

    for eid, info in checkpoint.get("excerpts", {}).items():
        st = info.get("state", "pending")
        state_counts[st] += 1
        if st == "pending":
            pending_ids.append(eid)

    return {
        "total": sum(state_counts.values()),
        "by_state": dict(state_counts),
        "pending_ids": sorted(pending_ids),
        "pending_count": len(pending_ids),
    }


def initialize_checkpoint_from_extraction(extraction_dir: str) -> dict:
    """Scan extraction output files and create a checkpoint with all
    excerpts marked as 'pending'.

    Returns the initialized checkpoint dict (also saved to disk).
    """
    ext_path = Path(extraction_dir)
    checkpoint = {
        "version": "0.1",
        "excerpts": {},
    }

    # Scan for extraction JSON files
    for json_file in sorted(ext_path.glob("*_extraction.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.loads(f.read())
        except (json.JSONDecodeError, OSError):
            continue

        for excerpt in data.get("excerpts", []):
            eid = excerpt.get("excerpt_id", "")
            if eid:
                checkpoint["excerpts"][eid] = {
                    "state": "pending",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reviewer": "",
                }

        for excerpt in data.get("footnote_excerpts", []):
            eid = excerpt.get("excerpt_id", "")
            if eid:
                checkpoint["excerpts"][eid] = {
                    "state": "pending",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reviewer": "",
                }

    save_checkpoint(extraction_dir, checkpoint)
    return checkpoint


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Human gate infrastructure: corrections, replay, patterns, checkpoints.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-command")

    # --- record-correction ---
    rec_parser = subparsers.add_parser(
        "record-correction", help="Record a human correction",
    )
    rec_parser.add_argument("--excerpt-id", required=True)
    rec_parser.add_argument(
        "--correction-type", required=True,
        choices=sorted(VALID_CORRECTION_TYPES),
    )
    rec_parser.add_argument(
        "--correction", required=True,
        help="JSON string with the human correction",
    )
    rec_parser.add_argument("--reason", default="")
    rec_parser.add_argument("--passage-id", default="")
    rec_parser.add_argument("--book-id", default="")
    rec_parser.add_argument("--science", default="")
    rec_parser.add_argument("--model", default="")
    rec_parser.add_argument(
        "--original", default="{}",
        help="JSON string with the original system output",
    )
    rec_parser.add_argument(
        "--corrections-file", required=True,
        help="Path to corrections JSONL file",
    )

    # --- replay-correction ---
    rep_parser = subparsers.add_parser(
        "replay-correction", help="Re-extract with correction as context",
    )
    rep_parser.add_argument("--correction-id", required=True)
    rep_parser.add_argument("--corrections-file", required=True)
    rep_parser.add_argument("--passages", required=True)
    rep_parser.add_argument("--pages", required=True)
    rep_parser.add_argument("--taxonomy", required=True)
    rep_parser.add_argument("--book-id", required=True)
    rep_parser.add_argument("--science", required=True)
    rep_parser.add_argument("--output-dir", required=True)
    rep_parser.add_argument("--model", default="claude-sonnet-4-5-20250929")

    # --- detect-patterns ---
    pat_parser = subparsers.add_parser(
        "detect-patterns", help="Detect patterns in corrections",
    )
    pat_parser.add_argument("--corrections-file", required=True)
    pat_parser.add_argument("--output-dir", required=True)
    pat_parser.add_argument("--min-count", type=int, default=2)

    # --- checkpoint ---
    cp_parser = subparsers.add_parser(
        "checkpoint", help="Manage gate checkpoints",
    )
    cp_parser.add_argument("--extraction-dir", required=True)
    cp_parser.add_argument(
        "--action", required=True,
        choices=["status", "init", "approve", "reject", "reset"],
    )
    cp_parser.add_argument("--excerpt-ids", default="")
    cp_parser.add_argument("--reviewer", default="")

    args = parser.parse_args()

    if args.command == "record-correction":
        try:
            correction_data = json.loads(args.correction)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in --correction: {e}", file=sys.stderr)
            sys.exit(1)
        try:
            original_data = json.loads(args.original)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in --original: {e}", file=sys.stderr)
            sys.exit(1)

        record = create_correction_record(
            excerpt_id=args.excerpt_id,
            correction_type=args.correction_type,
            original_output=original_data,
            human_correction=correction_data,
            reason=args.reason,
            passage_id=args.passage_id,
            book_id=args.book_id,
            science=args.science,
            model=args.model,
        )
        path = save_correction(record, args.corrections_file)
        print(f"Correction {record['correction_id']} saved to {path}")

    elif args.command == "replay-correction":
        corrections = load_corrections(args.corrections_file)
        correction = find_correction_by_id(corrections, args.correction_id)
        if not correction:
            print(f"ERROR: Correction '{args.correction_id}' not found",
                  file=sys.stderr)
            sys.exit(1)

        result = replay_correction(
            correction=correction,
            passages_file=args.passages,
            pages_file=args.pages,
            taxonomy_path=args.taxonomy,
            book_id=args.book_id,
            science=args.science,
            output_dir=args.output_dir,
            model=args.model,
        )
        print(f"Replay result: {result['status']}")
        if result.get("replay_metadata_path"):
            print(f"  Metadata: {result['replay_metadata_path']}")

    elif args.command == "detect-patterns":
        corrections = load_corrections(args.corrections_file)
        report = detect_patterns(corrections, min_count=args.min_count)
        path = save_pattern_report(report, args.output_dir)
        print(f"Pattern report: {path}")
        print(f"  Total corrections: {report['total_corrections']}")
        print(f"  Patterns found: {len(report['patterns'])}")
        print(f"  Summary: {report['summary']}")

    elif args.command == "checkpoint":
        if args.action == "init":
            cp = initialize_checkpoint_from_extraction(args.extraction_dir)
            summary = get_checkpoint_summary(cp)
            print(f"Initialized checkpoint: {summary['total']} excerpts (all pending)")

        elif args.action == "status":
            cp = load_checkpoint(args.extraction_dir)
            summary = get_checkpoint_summary(cp)
            print(f"Checkpoint status:")
            for state, count in sorted(summary["by_state"].items()):
                print(f"  {state}: {count}")
            if summary["pending_ids"]:
                print(f"  Pending: {', '.join(summary['pending_ids'][:20])}"
                      + ("..." if len(summary["pending_ids"]) > 20 else ""))

        elif args.action in ("approve", "reject", "reset"):
            cp = load_checkpoint(args.extraction_dir)
            if not args.excerpt_ids:
                print("ERROR: --excerpt-ids required for approve/reject/reset",
                      file=sys.stderr)
                sys.exit(1)
            eids = [e.strip() for e in args.excerpt_ids.split(",") if e.strip()]
            state_map = {
                "approve": "approved",
                "reject": "rejected",
                "reset": "pending",
            }
            cp = update_checkpoint(cp, eids, state_map[args.action], args.reviewer)
            save_checkpoint(args.extraction_dir, cp)
            print(f"Updated {len(eids)} excerpts to '{state_map[args.action]}'")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
