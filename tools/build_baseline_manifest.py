#!/usr/bin/env python3
"""Build or refresh baseline_manifest.json for a baseline package.

This tool exists to remove guesswork for AI builders and to keep manifests truthful
when new required artifacts (e.g. checkpoint_outputs logs) are introduced.

Design:
- Uses stdlib only.
- Computes sha256 + size for all files under baseline_dir recursively.
- Excludes: baseline_manifest.json and checkpoint_state.json from the `files` inventory and fingerprint.
- Updates/creates baseline_sha256 fingerprint.
- Preserves created_utc if manifest already exists; always updates updated_utc.

Usage:
  python tools/build_baseline_manifest.py --baseline-dir <baseline_dir>

"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone


EXCLUDE_FILES = {"baseline_manifest.json", "checkpoint_state.json"}
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache"}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def detect_metadata(baseline_dir: str) -> dict | None:
    for fn in os.listdir(baseline_dir):
        if fn.startswith("passage") and fn.endswith("_metadata.json"):
            with open(os.path.join(baseline_dir, fn), encoding="utf-8") as f:
                return json.load(f)
    return None


def role_for(relpath: str) -> str:
    rp = relpath.replace("\\", "/")
    if rp.startswith("schemas/"):
        return "schema"
    if rp.startswith("tools/") or rp in {"validate_gold.py", "generate_report.py"}:
        return "tool"
    if rp.startswith("excerpts_rendered/"):
        return "derived"
    if rp.endswith(".yaml"):
        return "taxonomy_tree"
    if rp.endswith("_atoms_v02.jsonl"):
        return "atom_data"
    if rp.endswith("_excerpts_v02.jsonl") or rp.endswith("_exclusions_v01.jsonl"):
        return "excerpt_data"
    if rp == "taxonomy_changes.jsonl":
        return "taxonomy_change_data"
    if rp.endswith("_decisions.jsonl"):
        return "decision_log"
    if rp.endswith("_canonical.txt"):
        return "canonical_text"
    if rp.endswith("_clean_matn_input.txt") or rp.endswith("_clean_fn_input.txt"):
        return "checkpoint1_clean_input"
    if rp.endswith("_source_slice.json"):
        return "source_locator"
    if rp.startswith("checkpoint_outputs/"):
        return "checkpoint_output"
    if rp.endswith(".md"):
        return "documentation"
    if rp.endswith(".txt"):
        return "report"
    return "other"


def compute_counts(baseline_dir: str, meta: dict | None) -> dict:
    counts = {}
    if not meta:
        return counts
    pid = meta.get("passage_id")
    if pid:
        for key, fn in [("matn_atoms", f"{pid}_matn_atoms_v02.jsonl"), ("fn_atoms", f"{pid}_fn_atoms_v02.jsonl")]:
            fp = os.path.join(baseline_dir, fn)
            if os.path.exists(fp):
                with open(fp, encoding="utf-8") as f:
                    counts[key] = sum(1 for _ in f if _.strip())
        counts["total_atoms"] = (counts.get("matn_atoms", 0) + counts.get("fn_atoms", 0))
        exc_fp = os.path.join(baseline_dir, f"{pid}_excerpts_v02.jsonl")
        if os.path.exists(exc_fp):
            excerpts = 0
            exclusions = 0
            rels = 0
            with open(exc_fp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if obj.get("record_type") == "excerpt":
                        excerpts += 1
                        rels += len(obj.get("relations") or [])
                    elif obj.get("record_type") == "exclusion":
                        exclusions += 1
            counts["excerpts"] = excerpts
            counts["exclusions"] = exclusions
            counts["relations"] = rels
        tc_fp = os.path.join(baseline_dir, "taxonomy_changes.jsonl")
        if os.path.exists(tc_fp):
            with open(tc_fp, encoding="utf-8") as f:
                counts["taxonomy_changes"] = sum(1 for _ in f if _.strip())
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-dir", required=True)
    ap.add_argument("--output", default="baseline_manifest.json")
    args = ap.parse_args()

    base = os.path.abspath(args.baseline_dir)
    out_path = os.path.join(base, args.output)

    meta = detect_metadata(base)
    baseline_id = os.path.basename(base)

    created = None
    if os.path.exists(out_path):
        try:
            old = json.load(open(out_path, encoding="utf-8"))
            created = old.get("created_utc")
        except Exception:
            created = None

    files = {}
    for root, dirs, fns in os.walk(base):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fn in fns:
            if fn in EXCLUDE_FILES:
                continue
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, base).replace("\\", "/")
            # skip the output file itself if custom name
            if rel == args.output:
                continue
            files[rel] = {
                "sha256": sha256_file(fp),
                "size_bytes": os.path.getsize(fp),
                "role": role_for(rel),
            }

    # Fingerprint (reproducible)
    concat = "".join(f"{k}:{files[k]['sha256']}" for k in sorted(files.keys()))
    baseline_sha256 = hashlib.sha256(concat.encode("utf-8")).hexdigest()

    man = {
        "manifest_version": "1.2",
        "baseline_id": baseline_id,
        "created_utc": created or utc_now(),
        "updated_utc": utc_now(),
        "schema_version": (meta or {}).get("schema_version", ""),
        "taxonomy_version": (meta or {}).get("taxonomy_version", ""),
        "files": files,
        "baseline_sha256": baseline_sha256,
        "baseline_sha256_algorithm": "sha256(concat(path:sha256)) over all files EXCEPT baseline_manifest.json and checkpoint_state.json",
        "inventory_policy": "A valid baseline package contains exactly the files listed in 'files' plus baseline_manifest.json and checkpoint_state.json.",
        "fingerprint_algorithm": {
            "description": "baseline_sha256 is computed by: (1) sorting all file entries in 'files' by filename ascending, (2) concatenating 'filename:sha256' for each, (3) computing SHA-256 of the resulting UTF-8 string.",
            "formula": "sha256( ''.join( f'{k}:{v.sha256}' for k,v in sorted(files.items()) ) )",
            "self_exclusion": "baseline_manifest.json and checkpoint_state.json are excluded to avoid self-referential hashing cycles.",
        },
    }

    # Attach optional passage scope + counts if metadata has it
    if meta:
        if "description" not in man:
            pages = meta.get("page_range", "")
            title = meta.get("book_title", "")
            pid = meta.get("passage_id", "")
            man["description"] = f"Gold standard baseline for {pid} ({title}, {pages})."

        man["passage_scope"] = {
            "book_id": meta.get("book_id", ""),
            "book_title": meta.get("book_title", ""),
            "author": meta.get("author", ""),
            "pages": meta.get("page_range", ""),
            "section": meta.get("section", ""),
        }
        counts = compute_counts(base, meta)
        if counts:
            man["counts"] = counts
        desc = meta.get("baseline_description")
        if desc:
            man["description"] = desc

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)

    print(f"Wrote manifest: {out_path}")


if __name__ == "__main__":
    main()
