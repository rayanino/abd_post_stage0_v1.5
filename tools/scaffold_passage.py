#!/usr/bin/env python3
"""Scaffold a new passage baseline folder.

Why this exists
--------------
Baseline folders are the spec-by-example contract for a future builder. A scaffold tool must
therefore *never* bake obsolete governance, schema, or checklist versions into a newly created
baseline.

This script creates a new passage folder with required placeholders and copies **current
canonical** governance/tooling snapshots from the repo:
  - Binding decisions (latest 00_BINDING_DECISIONS_v*.md)
  - Extraction protocol (latest extraction_protocol_v*.md)
  - Support schemas (schemas/*.json)
  - Tool snapshots (validate_gold.py, render_excerpts_md.py)

It also resolves `book_id/title/author` from `books/books_registry.yaml` when possible.

Usage:
  python tools/scaffold_passage.py \
    --book-dir 2_atoms_and_excerpts/1_jawahir_al_balagha \
    --new-passage passage4 \
    --version v0.3.13 \
    --from-passage passage3_v0.3.14

Notes:
  - Creates checkpoint_state.json (CP0) so the pipeline has an authoritative state file.
  - Copies support schemas into baseline-local schemas/ for standalone validation.
  - Does **not** attempt to guess page ranges or taxonomy_version; those are authored later.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from typing import Any, Dict, Optional, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


def copy_if_exists(src: str, dst: str):
    if os.path.exists(src):
        shutil.copy2(src, dst)


def _parse_version_tuple(v: str) -> Tuple[int, ...]:
    """Parse version strings like 'v0.3.16' or '2.4' into a sortable tuple."""
    v = v.strip()
    if v.startswith("v"):
        v = v[1:]
    parts = re.split(r"[^0-9]+", v)
    nums = [int(p) for p in parts if p.isdigit()]
    return tuple(nums) if nums else (0,)


def _find_latest_versioned_file(dirpath: str, prefix: str, ext: str) -> Optional[str]:
    """Find latest file matching '{prefix}_v*.{ext}' in dirpath."""
    best = None
    best_ver = (0,)
    for fn in os.listdir(dirpath):
        if not (fn.startswith(prefix + "_v") and fn.endswith(ext)):
            continue
        m = re.search(r"_v([^/]+)" + re.escape(ext) + r"$", fn)
        if not m:
            continue
        ver = _parse_version_tuple(m.group(1))
        if ver > best_ver:
            best_ver = ver
            best = os.path.join(dirpath, fn)
    return best


def _extract_validator_version(validate_gold_py: str) -> str:
    try:
        txt = open(validate_gold_py, encoding="utf-8").read()
    except Exception:
        return "unknown"
    # Common forms: "Gold Standard Validator v0.3.13" or "v0.3.13"
    m = re.search(r"Validator\s+v(\d+(?:\.\d+)+)", txt)
    if m:
        return f"v{m.group(1)}"
    m = re.search(r"\bv(\d+(?:\.\d+)+)\b", txt)
    return f"v{m.group(1)}" if m else "unknown"


def _extract_pipeline_version(pipeline_gold_py: str) -> str:
    try:
        txt = open(pipeline_gold_py, encoding="utf-8").read()
    except Exception:
        return "gold_pipeline_v0.3"
    m = re.search(r"PIPELINE_VERSION\s*=\s*\"([^\"]+)\"", txt)
    return m.group(1) if m else "gold_pipeline_v0.3"


def _resolve_book_meta(repo_root: str, book_dir_rel: str) -> Dict[str, str]:
    """Resolve book_id/title/author using books/books_registry.yaml.

    Heuristic: match any source_files.relpath that begins with the provided book_dir_rel.
    """
    reg_path = os.path.join(repo_root, "books", "books_registry.yaml")
    if not os.path.exists(reg_path):
        return {}
    if yaml is None:
        return {}
    data = yaml.safe_load(open(reg_path, encoding="utf-8"))
    books = (data or {}).get("books", [])
    for b in books:
        for sf in b.get("source_files", []) or []:
            relpath = sf.get("relpath")
            if isinstance(relpath, str) and relpath.startswith(book_dir_rel.rstrip("/") + "/"):
                return {
                    "book_id": b.get("book_id", ""),
                    "book_title": b.get("title", ""),
                    "author": b.get("author", ""),
                }
    return {}


def _copy_python_with_banner(src: str, dst: str, banner: str):
    """Copy a python file and add a non-canonical snapshot banner at the top."""
    if not os.path.exists(src):
        return
    txt = open(src, encoding="utf-8").read()
    lines = txt.splitlines(True)
    out_lines = []
    if lines and lines[0].startswith("#!"):
        out_lines.append(lines[0])
        lines = lines[1:]
    out_lines.append("# " + banner.replace("\n", "\n# ") + "\n\n")
    out_lines.extend(lines)
    with open(dst, "w", encoding="utf-8") as f:
        f.writelines(out_lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book-dir", required=True)
    ap.add_argument("--new-passage", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--from-passage", default=None, help="Existing passage folder to copy formats/counters from")
    args = ap.parse_args()

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    book_dir = os.path.abspath(os.path.join(repo_root, args.book_dir))

    out_dir = os.path.join(book_dir, f"{args.new_passage}_{args.version}")
    if os.path.exists(out_dir):
        raise SystemExit(f"Target already exists: {out_dir}")

    os.makedirs(out_dir, exist_ok=False)
    os.makedirs(os.path.join(out_dir, "tools"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "schemas"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "excerpts_rendered"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "checkpoint_outputs"), exist_ok=True)

    # Resolve canonical governance snapshots (latest in repo)
    atoms_root = os.path.join(repo_root, "2_atoms_and_excerpts")
    latest_binding = _find_latest_versioned_file(atoms_root, "00_BINDING_DECISIONS", ".md")
    latest_protocol = _find_latest_versioned_file(atoms_root, "extraction_protocol", ".md")
    if latest_binding:
        copy_if_exists(latest_binding, os.path.join(out_dir, os.path.basename(latest_binding)))
    if latest_protocol:
        copy_if_exists(latest_protocol, os.path.join(out_dir, os.path.basename(latest_protocol)))

    # Glossary snapshot
    copy_if_exists(os.path.join(repo_root, "project_glossary.md"), os.path.join(out_dir, "project_glossary.md"))

    # Copy stable formats from existing passage (if provided)
    if args.from_passage:
        src_pass = os.path.join(book_dir, args.from_passage)
        for fn in ["decision_log_format_v0.1.md", "checkpoint1_fixed_report.md", "checkpoint3_boundary_plan.md"]:
            copy_if_exists(os.path.join(src_pass, fn), os.path.join(out_dir, fn))

        # Also copy taxonomy snapshot if present
        for fn in os.listdir(src_pass):
            if fn.endswith(".yaml") and ("balagha_" in fn or "taxonomy" in fn):
                copy_if_exists(os.path.join(src_pass, fn), os.path.join(out_dir, fn))

    # Support schemas (baseline-local)
    for fn in [
        "passage_metadata_schema_v0.1.json",
        "baseline_manifest_schema_v0.1.json",
        "decision_log_schema_v0.1.json",
        "source_locator_schema_v0.1.json",
        "checkpoint_state_schema_v0.1.json",
    ]:
        copy_if_exists(os.path.join(repo_root, "schemas", fn), os.path.join(out_dir, "schemas", fn))

    # Tool snapshots
    canonical_validate = os.path.join(repo_root, "tools", "validate_gold.py")
    canonical_render = os.path.join(repo_root, "tools", "render_excerpts_md.py")
    banner = (
        "SNAPSHOT (NON-CANONICAL): this file is copied at scaffold time for convenience. "
        "Canonical tools live under ABD/tools/. Always run validations from ABD/: "
        "python tools/run_all_validations.py"
    )
    _copy_python_with_banner(canonical_validate, os.path.join(out_dir, "validate_gold.py"), banner)
    _copy_python_with_banner(canonical_render, os.path.join(out_dir, "tools", "render_excerpts_md.py"), banner)

    # Placeholders
    with open(os.path.join(out_dir, "AUDIT_LOG.md"), "w", encoding="utf-8") as f:
        f.write(f"# AUDIT — {args.new_passage} ({args.version})\n\n- Scaffolded baseline folder.\n")

    # Minimal metadata stub (modern canon)
    canon_schema = _find_latest_versioned_file(os.path.join(repo_root, "schemas"), "gold_standard_schema", ".json")
    schema_version = "gold_standard_v0.3.3"
    if canon_schema:
        m = re.search(r"gold_standard_schema_(v[^.]+(?:\.[^.]+)*)\.json$", os.path.basename(canon_schema))
        if m:
            schema_version = "gold_standard_" + m.group(1)

    book_meta = _resolve_book_meta(repo_root, args.book_dir)

    validator_version = _extract_validator_version(os.path.join(repo_root, "tools", "validate_gold.py"))
    meta = {
        "passage_id": args.new_passage,
        "book_id": book_meta.get("book_id", ""),
        "book_title": book_meta.get("book_title", ""),
        "author": book_meta.get("author", ""),
        "page_range": "",
        "topic": "",
        "taxonomy_version": "",
        "schema_version": schema_version,
        "offset_unit": "unicode_codepoint",
        "validation": {
            "validator": "validate_gold.py",
            "validator_version": validator_version,
            "validated_utc": "",
            "command": "",
            "warnings": 0,
            "errors": 0,
            "result": "FAIL",
        },
        "baseline_version": args.version if args.version.startswith("v") else f"v{args.version}",
    }
    with open(os.path.join(out_dir, f"{args.new_passage}_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # Checkpoint state (CP0)
    pipeline_version = _extract_pipeline_version(os.path.join(repo_root, "tools", "pipeline_gold.py"))
    state = {
        "record_type": "checkpoint_state",
        "checkpoint_state_version": "0.1",
        "book_id": meta.get("book_id") or "",
        "passage_id": args.new_passage,
        "baseline_version": args.version.lstrip("v"),
        "pipeline_version": pipeline_version,
        "checkpoint_last_completed": 0,
        "checkpoints": {
            "1": {"name": "CP1_clean_input", "status": "pending", "artifacts": []},
            "2": {"name": "CP2_atoms_and_canonicals", "status": "pending", "artifacts": []},
            "3": {"name": "CP3_decisions", "status": "pending", "artifacts": []},
            "4": {"name": "CP4_excerpts", "status": "pending", "artifacts": []},
            "5": {"name": "CP5_taxonomy_changes", "status": "pending", "artifacts": []},
            "6": {"name": "CP6_validate_and_package", "status": "pending", "artifacts": []},
        },
        "integrity": {"baseline_manifest_sha256": "0" * 64, "validator_version": validator_version},
    }
    with open(os.path.join(out_dir, "checkpoint_state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(f"Created: {out_dir}")


if __name__ == "__main__":
    main()
