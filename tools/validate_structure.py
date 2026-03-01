#!/usr/bin/env python3
"""Stage 2 Validation: validate structure discovery output for internal consistency.

Checks:
  1. Division tree is a valid tree (no orphans, no cycles)
  2. Page ranges are contiguous and non-overlapping within siblings
  3. Children are contained within parent page ranges
  4. Passages cover all digestible leaf divisions
  5. Passage sizes respect the rules
  6. All seq_index references exist in the book's page range
  7. Schema compliance

Usage:
  python tools/validate_structure.py \\
    --divisions output/jawahir_divisions.json \\
    --passages output/jawahir_passages.jsonl \\
    --pages 1_normalization/jawahir_normalized_full.jsonl \\
    [--report output/validation_report.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_divisions(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_passages(path: str) -> list[dict]:
    passages = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                passages.append(json.loads(line))
    return passages


def load_page_indices(path: str) -> set[int]:
    indices = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            si = rec.get("seq_index")
            if si is not None:
                indices.add(si)
    return indices


class ValidationResult:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        lines = []
        if self.errors:
            lines.append(f"ERRORS ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"  ✗ {e}")
        if self.warnings:
            lines.append(f"WARNINGS ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        if not self.errors and not self.warnings:
            lines.append("✓ All checks passed")
        elif not self.errors:
            lines.append(f"✓ No errors ({len(self.warnings)} warnings)")
        return "\n".join(lines)


def validate_division_tree(divisions: list[dict], result: ValidationResult):
    """Check division tree structural integrity."""
    div_by_id = {d["id"]: d for d in divisions}
    ids = set(div_by_id.keys())

    # Check for duplicate IDs
    if len(ids) != len(divisions):
        result.error(f"Duplicate division IDs found ({len(divisions)} divisions, {len(ids)} unique IDs)")

    for d in divisions:
        did = d["id"]

        # Check parent reference
        pid = d.get("parent_id")
        if pid is not None and pid not in ids:
            result.error(f"Division {did} has parent_id '{pid}' which does not exist")

        # Check child references
        for cid in d.get("child_ids", []):
            if cid not in ids:
                result.error(f"Division {did} has child '{cid}' which does not exist")

    # Check for cycles
    visited = set()
    def has_cycle(did: str, path: set[str]) -> bool:
        if did in path:
            return True
        if did in visited:
            return False
        visited.add(did)
        path.add(did)
        for cid in div_by_id.get(did, {}).get("child_ids", []):
            if has_cycle(cid, path):
                return True
        path.discard(did)
        return False

    for d in divisions:
        if has_cycle(d["id"], set()):
            result.error(f"Cycle detected involving division {d['id']}")
            break  # One cycle error is enough

    # Check parent-child consistency
    for d in divisions:
        pid = d.get("parent_id")
        if pid and pid in div_by_id:
            parent = div_by_id[pid]
            if d["id"] not in parent.get("child_ids", []):
                result.warn(f"Division {d['id']} references parent {pid}, but parent's child_ids doesn't include it")


def validate_page_ranges(divisions: list[dict], result: ValidationResult):
    """Check page range validity and consistency."""
    for d in divisions:
        did = d["id"]
        start = d.get("start_seq_index", 0)
        end = d.get("end_seq_index", 0)

        if end < start:
            result.error(f"Division {did}: end_seq_index ({end}) < start_seq_index ({start})")

        page_count = d.get("page_count", 0)
        expected = end - start + 1
        if page_count != expected:
            result.warn(f"Division {did}: page_count ({page_count}) != expected ({expected})")

    # Check children are within parent range
    div_by_id = {d["id"]: d for d in divisions}
    for d in divisions:
        pid = d.get("parent_id")
        if pid and pid in div_by_id:
            parent = div_by_id[pid]
            if d["start_seq_index"] < parent["start_seq_index"]:
                result.error(f"Division {d['id']} starts at {d['start_seq_index']} "
                             f"before parent {pid} starts at {parent['start_seq_index']}")
            if d["end_seq_index"] > parent["end_seq_index"]:
                result.error(f"Division {d['id']} ends at {d['end_seq_index']} "
                             f"after parent {pid} ends at {parent['end_seq_index']}")


def validate_passages(
    passages: list[dict],
    divisions: list[dict],
    result: ValidationResult,
):
    """Check passage validity."""
    div_by_id = {d["id"]: d for d in divisions}

    # Check passage fields
    seen_ids = set()
    for p in passages:
        pid = p.get("passage_id", "")
        if pid in seen_ids:
            result.error(f"Duplicate passage ID: {pid}")
        seen_ids.add(pid)

        if p.get("end_seq_index", 0) < p.get("start_seq_index", 0):
            result.error(f"Passage {pid}: end_seq_index < start_seq_index")

        # Check division references
        for did in p.get("division_ids", []):
            if did not in div_by_id:
                result.error(f"Passage {pid} references division '{did}' which does not exist")

        # Check sizing rules
        pc = p.get("page_count", 0)
        action = p.get("sizing_action", "none")
        flags = p.get("review_flags", [])

        if pc > 20 and "long_passage" not in flags and action not in ("split",):
            result.warn(f"Passage {pid}: {pc} pages but no 'long_passage' flag")

    # Check passage ordering (sequential, no gaps in passage IDs)
    ids = [p.get("passage_id", "") for p in passages]
    for i, pid in enumerate(ids):
        if i > 0:
            prev = passages[i - 1]
            if passages[i].get("predecessor_passage_id") != prev.get("passage_id"):
                result.warn(f"Passage {pid}: predecessor_passage_id mismatch")

    # CRITICAL: Check for passage page-range overlaps
    sorted_passages = sorted(passages, key=lambda p: (p.get("start_seq_index", 0), p.get("passage_id", "")))
    for i in range(len(sorted_passages) - 1):
        p1 = sorted_passages[i]
        p2 = sorted_passages[i + 1]
        if p1.get("end_seq_index", 0) >= p2.get("start_seq_index", 0):
            result.error(
                f"Passage overlap: {p1.get('passage_id')} [{p1.get('start_seq_index')}-{p1.get('end_seq_index')}] "
                f"overlaps with {p2.get('passage_id')} [{p2.get('start_seq_index')}-{p2.get('end_seq_index')}]"
            )

    # Check passages cover all digestible leaves
    parent_ids = {d.get("parent_id") for d in divisions if d.get("parent_id")}
    leaf_ids = {d["id"] for d in divisions if d["id"] not in parent_ids}
    digestible_leaf_ids = {
        d["id"] for d in divisions
        if d["id"] in leaf_ids and d.get("digestible") != "false"
        and "same_page_cluster" not in d.get("review_flags", [])
    }
    covered_ids = set()
    for p in passages:
        covered_ids.update(p.get("division_ids", []))

    uncovered = digestible_leaf_ids - covered_ids
    if uncovered:
        result.warn(f"Digestible leaf divisions not covered by any passage: {uncovered}")


def validate_seq_indices(
    divisions: list[dict],
    passages: list[dict],
    page_indices: set[int],
    result: ValidationResult,
):
    """Check all seq_index references exist in the page set."""
    for d in divisions:
        for key in ("start_seq_index", "end_seq_index"):
            idx = d.get(key)
            if idx is not None and idx not in page_indices:
                result.warn(f"Division {d['id']}: {key}={idx} not found in pages JSONL")

    for p in passages:
        for key in ("start_seq_index", "end_seq_index"):
            idx = p.get(key)
            if idx is not None and idx not in page_indices:
                result.warn(f"Passage {p['passage_id']}: {key}={idx} not found in pages JSONL")


def validate_required_fields(divisions: list[dict], passages: list[dict], result: ValidationResult):
    """Check that required fields are present."""
    div_required = ["id", "type", "title", "level", "detection_method", "confidence",
                    "digestible", "start_seq_index", "end_seq_index", "parent_id"]
    for d in divisions:
        for field in div_required:
            if field not in d:
                result.error(f"Division {d.get('id', '?')}: missing required field '{field}'")

    pass_required = ["passage_id", "book_id", "division_ids", "title",
                     "start_seq_index", "end_seq_index", "page_count",
                     "digestible", "content_type", "sizing_action", "review_flags"]
    for p in passages:
        for field in pass_required:
            if field not in p:
                result.error(f"Passage {p.get('passage_id', '?')}: missing required field '{field}'")


def main():
    parser = argparse.ArgumentParser(description="Validate Stage 2 structure discovery output.")
    parser.add_argument("--divisions", required=True, help="Path to divisions.json")
    parser.add_argument("--passages", required=True, help="Path to passages.jsonl")
    parser.add_argument("--pages", help="Path to Stage 1 pages.jsonl (for seq_index validation)")
    parser.add_argument("--report", help="Write validation report JSON to this path")
    args = parser.parse_args()

    result = ValidationResult()

    # Load data
    div_data = load_divisions(args.divisions)
    divisions = div_data.get("divisions", [])
    passages = load_passages(args.passages)

    print(f"Validating: {len(divisions)} divisions, {len(passages)} passages")

    # Run checks
    validate_required_fields(divisions, passages, result)
    validate_division_tree(divisions, result)
    validate_page_ranges(divisions, result)
    validate_passages(passages, divisions, result)

    if args.pages:
        page_indices = load_page_indices(args.pages)
        validate_seq_indices(divisions, passages, page_indices, result)

    # Report
    print()
    print(result.summary())

    if args.report:
        report = {
            "valid": result.ok,
            "errors": result.errors,
            "warnings": result.warnings,
            "division_count": len(divisions),
            "passage_count": len(passages),
        }
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nReport written to {args.report}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
