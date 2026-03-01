#!/usr/bin/env python3
"""Run validation across all active gold baselines.

This script is meant to become CI.
It discovers active baselines via `ACTIVE_GOLD.md` files and then runs each baseline's
recorded validation command (from passage*_metadata.json).

By default it refuses to validate `_ARCHIVE/` baselines.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys


def find_active_gold_files(root: str):
    out = []
    for dirpath, _, filenames in os.walk(root):
        if "ACTIVE_GOLD.md" in filenames:
            out.append(os.path.join(dirpath, "ACTIVE_GOLD.md"))
    return sorted(out)


def parse_baseline_dirs(active_gold_md: str):
    base = os.path.dirname(active_gold_md)
    dirs = []
    with open(active_gold_md, encoding="utf-8") as f:
        for line in f:
            # Paths in ACTIVE_GOLD.md may begin with `passage...` directly.
            # Accept suffixes such as passage4_v0.3.13_plus1/ (avoid silent CI skips).
            m = re.search(r"`([^`]*passage\d+_v[0-9][0-9A-Za-z._+\-]*/?)`", line)
            if m:
                rel = m.group(1).rstrip("/")
                dirs.append(os.path.abspath(os.path.join(base, rel)))
    return dirs


def find_metadata(baseline_dir: str):
    for fn in os.listdir(baseline_dir):
        if fn.startswith("passage") and fn.endswith("_metadata.json"):
            return os.path.join(baseline_dir, fn)
    return None


def is_archive_path(p: str) -> bool:
    return "/_ARCHIVE/" in p.replace("\\", "/")


def run_one(baseline_dir: str) -> bool:
    md = find_metadata(baseline_dir)
    if not md:
        print(f"ERROR: no metadata in {baseline_dir}")
        return False
    with open(md, encoding="utf-8") as f:
        meta = json.load(f)
    cmd = meta.get("validation", {}).get("command")
    if not cmd:
        print(f"ERROR: missing validation.command in {md}")
        return False
    print(f"\n=== VALIDATE: {baseline_dir} ===\n{cmd}\n")
    res = subprocess.run(cmd, cwd=baseline_dir, shell=True)
    return res.returncode == 0


def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ok = True

    gold_files = find_active_gold_files(root)
    if not gold_files:
        print("ERROR: No ACTIVE_GOLD.md files found")
        sys.exit(1)

    baseline_dirs = []
    for f in gold_files:
        baseline_dirs.extend(parse_baseline_dirs(f))

    # de-dup
    seen = set(); uniq = []
    for d in baseline_dirs:
        if d not in seen:
            seen.add(d); uniq.append(d)

    for d in uniq:
        if is_archive_path(d):
            print(f"SKIP (archive): {d}")
            continue
        if not run_one(d):
            ok = False

    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
