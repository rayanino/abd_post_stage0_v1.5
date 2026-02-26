#!/usr/bin/env python3
"""Deterministic checkpoint_outputs index generator.

This module defines the canonical algorithm for producing:
  checkpoint_outputs/index.txt

Goals:
- Deterministic: no timestamps, no machine-specific absolute paths.
- Derived-only: must be regenerated; must not be hand-edited.
- Review-optimized: checkpoint commands + artifact presence + stable fingerprint.
- No hash cycles / write races:
  - fingerprint EXCLUDES:
      * baseline_manifest.json
      * checkpoint_state.json
      * checkpoint_outputs/index.txt (this file)
      * checkpoint_outputs/cp6_*.stdout.txt / cp6_*.stderr.txt (written during CP6)
      * validation_report.txt (written during CP6 validation)
      * excerpts_rendered/** (derived during CP6)

The validator (tools/validate_gold.py) recomputes the expected index text and requires
an exact match.

This is a PREP-PHASE component: it hardens gold baselines and human approval gates.
"""

from __future__ import annotations

import hashlib
import os
from typing import Dict, Any, List, Tuple

INDEX_REL_PATH = "checkpoint_outputs/index.txt"
INDEX_VERSION = "checkpoint_outputs_index_v0.1"

# Paths excluded from fingerprint hashing (NOT from being listed in inventory).
EXCLUDE_FROM_FINGERPRINT = {
    "baseline_manifest.json",
    "checkpoint_state.json",
    INDEX_REL_PATH,
    "validation_report.txt",
}

# Prefix exclusions (directory trees)
EXCLUDE_PREFIXES_FROM_FINGERPRINT = (
    "excerpts_rendered/",
)

# Pattern exclusions (simple startswith checks)
EXCLUDE_FINGERPRINT_STARTSWITH = (
    "checkpoint_outputs/cp6_",
)

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache"}


def _norm_relpath(rel: str) -> str:
    return rel.replace("\\", "/").lstrip("./")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_inventory_files(base_dir: str) -> List[str]:
    """Return all file relpaths under base_dir, sorted, using forward slashes."""
    out: List[str] = []
    for dirpath, dirnames, filenames in os.walk(base_dir):
        # prune noise dirs
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, base_dir)
            out.append(_norm_relpath(rel))
    return sorted(set(out))


def is_excluded_from_fingerprint(rel: str) -> bool:
    r = _norm_relpath(rel)
    if r in EXCLUDE_FROM_FINGERPRINT:
        return True
    for pfx in EXCLUDE_PREFIXES_FROM_FINGERPRINT:
        if r.startswith(pfx):
            return True
    for pfx in EXCLUDE_FINGERPRINT_STARTSWITH:
        if r.startswith(pfx) and (r.endswith(".stdout.txt") or r.endswith(".stderr.txt")):
            return True
    return False


def compute_fingerprint(base_dir: str, inventory: List[str]) -> str:
    """Compute a stable fingerprint over inventory excluding volatile/cyclic paths."""
    parts: List[str] = []
    for rel in inventory:
        if is_excluded_from_fingerprint(rel):
            continue
        fp = os.path.join(base_dir, rel)
        if not os.path.isfile(fp):
            continue
        parts.append(f"{rel}:{sha256_file(fp)}")
    joined = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()


def _load_checkpoint_state(base_dir: str) -> Dict[str, Any]:
    import json
    sp = os.path.join(base_dir, "checkpoint_state.json")
    with open(sp, encoding="utf-8") as f:
        return json.load(f)


def _fmt_cmd(cmd: str) -> str:
    cmd = (cmd or "").strip()
    if not cmd:
        return "(missing)"
    return cmd


def expected_index_text(base_dir: str) -> str:
    """Return the deterministic expected content of checkpoint_outputs/index.txt."""
    st = _load_checkpoint_state(base_dir)
    inventory = collect_inventory_files(base_dir)
    fp = compute_fingerprint(base_dir, inventory)

    # high-signal identifiers (avoid absolute paths)
    baseline_id = st.get("baseline_version") or os.path.basename(os.path.abspath(base_dir))
    passage_id = st.get("passage_id") or ""
    book_id = st.get("book_id") or ""
    pipeline_version = st.get("pipeline_version") or ""
    last = int(st.get("checkpoint_last_completed", 0) or 0)

    cps = st.get("checkpoints", {}) or {}

    lines: List[str] = []
    lines.append(f"ABD deterministic checkpoint index ({INDEX_VERSION})")
    lines.append("DO NOT EDIT BY HAND. Regenerate via: python tools/generate_checkpoint_index.py --baseline-dir <baseline_dir>")
    lines.append("")

    lines.append("=== Identity ===")
    lines.append(f"baseline_id: {baseline_id}")
    if passage_id:
        lines.append(f"passage_id: {passage_id}")
    if book_id:
        lines.append(f"book_id: {book_id}")
    if pipeline_version:
        lines.append(f"pipeline_version: {pipeline_version}")
    lines.append(f"checkpoint_last_completed: {last}")
    lines.append("")

    lines.append("=== Stable fingerprint ===")
    lines.append("algorithm: sha256(concat(relpath:sha256)) over inventory excluding volatile/cyclic paths")
    lines.append("excludes:")
    for x in sorted(EXCLUDE_FROM_FINGERPRINT):
        lines.append(f"  - {x}")
    for x in EXCLUDE_PREFIXES_FROM_FINGERPRINT:
        lines.append(f"  - {x}**")
    lines.append("  - checkpoint_outputs/cp6_*.stdout.txt")
    lines.append("  - checkpoint_outputs/cp6_*.stderr.txt")
    lines.append(f"value: {fp}")
    lines.append("")

    lines.append("=== Checkpoints (from checkpoint_state.json) ===")
    for i in range(1, 7):
        c = cps.get(str(i), {}) or {}
        status = (c.get("status") or "missing").strip()
        lines.append(f"-- CP{i}: {status} --")
        lines.append(f"command: {_fmt_cmd(c.get('command') or '')}")
        arts = [ _norm_relpath(a) for a in (c.get("artifacts") or []) ]
        if not arts:
            lines.append("artifacts: (none listed)")
            lines.append("")
            continue
        lines.append("artifacts:")
        for rel in arts:
            fp2 = os.path.join(base_dir, rel)
            ok = os.path.exists(fp2)
            mark = "OK" if ok else "MISSING"
            lines.append(f"  - {mark}  {rel}")
        lines.append("")

    lines.append("=== Inventory (relpaths) ===")
    lines.append(f"total_files: {len(inventory)}")
    for rel in inventory:
        lines.append(f"  - {rel}")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_index_file(base_dir: str) -> str:
    """Generate and write checkpoint_outputs/index.txt, returning the written text."""
    od = os.path.join(base_dir, "checkpoint_outputs")
    os.makedirs(od, exist_ok=True)
    idx_fp = os.path.join(base_dir, INDEX_REL_PATH)
    # Ensure file exists before computing expected content (artifact presence check).
    if not os.path.exists(idx_fp):
        open(idx_fp, "a", encoding="utf-8").close()
    txt = expected_index_text(base_dir)
    with open(idx_fp, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)
    return txt
