#!/usr/bin/env python3
"""Extract a printed-page slice from a Shamela HTML export and emit clean input text.

This tool is an architectural reference implementation for Checkpoint 1.
It is intentionally conservative and only performs permitted normalization operations.

Limitations (v0.2):
- Produces a single plain-text stream from the HTML slice.
- Does not reliably separate footnotes from matn for all books.
  (Layer separation is handled downstream in gold baselines; production app may implement better splitting.)

Usage:
  python tools/extract_clean_input.py \
    --html 2_atoms_and_excerpts/1_jawahir_al_balagha/shamela_export.htm \
    --page-start 19 --page-end 25 \
    --out-matn passage1_clean_matn_input.txt \
    --out-fn passage1_clean_fn_input.txt \
    --out-slice passage1_source_slice.json
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import hashlib


def to_arabic_indic(n: int) -> str:
    digits = "٠١٢٣٤٥٦٧٨٩"
    return "".join(digits[int(d)] for d in str(n))


def strip_tags(s: str) -> str:
    # Remove scripts/styles
    s = re.sub(r"<script[\s\S]*?</script>", "", s, flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", "", s, flags=re.I)

    # Replace <br> and <p> with newlines (conservative)
    s = re.sub(r"<\s*br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</\s*p\s*>", "\n", s, flags=re.I)

    # Drop remaining tags
    s = re.sub(r"<[^>]+>", "", s)
    return s


def normalize_whitespace(s: str) -> str:
    s = s.replace("\r\n", "\n")
    s = s.replace("\u00a0", " ")
    # collapse multiple spaces inside a line
    s = "\n".join(re.sub(r"[ \t]{2,}", " ", line).rstrip() for line in s.split("\n"))
    # collapse >2 blank lines
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip() + "\n"


def find_page_markers(html_text: str):
    # matches (ص: ١٩) etc
    pat = re.compile(r"\(\s*ص\s*:\s*([٠-٩]+)\s*\)")
    return [(m.start(), m.group(1)) for m in pat.finditer(html_text)]


def sha256_text(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_abd_root(start_dir: str) -> str | None:
    """Find ABD root directory containing `spec/` and `schemas/`."""
    cur = os.path.abspath(start_dir)
    for _ in range(12):
        if os.path.isdir(os.path.join(cur, "spec")) and os.path.isdir(os.path.join(cur, "schemas")):
            return cur
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur = nxt
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", required=True)
    ap.add_argument("--book-id", default="", help="Optional explicit book_id; otherwise inferred from paths.")
    ap.add_argument("--page-start", type=int, required=True)
    ap.add_argument("--page-end", type=int, required=True)
    ap.add_argument("--out-matn", required=True)
    ap.add_argument("--out-fn", required=True)
    ap.add_argument("--out-slice", required=True)
    args = ap.parse_args()

    raw = open(args.html, encoding="utf-8", errors="ignore").read()

    start_indic = to_arabic_indic(args.page_start)
    end_next_indic = to_arabic_indic(args.page_end + 1)

    # locate slice
    m1 = re.search(rf"\(\s*ص\s*:\s*{re.escape(start_indic)}\s*\)", raw)
    if not m1:
        raise SystemExit(f"Start page marker not found: {args.page_start} ({start_indic})")

    m2 = re.search(rf"\(\s*ص\s*:\s*{re.escape(end_next_indic)}\s*\)", raw)
    end_pos = m2.start() if m2 else len(raw)

    slice_html = raw[m1.start():end_pos]

    # text extraction
    txt = html.unescape(slice_html)
    txt = strip_tags(txt)
    txt = normalize_whitespace(txt)

    os.makedirs(os.path.dirname(os.path.abspath(args.out_matn)) or ".", exist_ok=True)
    open(args.out_matn, "w", encoding="utf-8").write(txt)
    open(args.out_fn, "w", encoding="utf-8").write("")

    # Source locator (Checkpoint 1 provenance)
    # Prefer stable ABD-root-relative relpaths when ABD root can be inferred.
    cwd = os.getcwd()
    abd_root = find_abd_root(cwd)

    baseline_rel_html = os.path.relpath(
        os.path.abspath(args.html),
        start=os.path.dirname(os.path.abspath(args.out_slice))
    ).replace("\\", "/")

    proj_rel_html = None
    if abd_root:
        try:
            proj_rel_html = os.path.relpath(os.path.abspath(args.html), start=abd_root).replace("\\", "/")
        except Exception:
            proj_rel_html = None

    # Normalization contract is defined at ABD root
    norm_proj = "spec/normalization_contract_v0.1.md"
    norm_base = None
    if abd_root:
        try:
            norm_base = os.path.relpath(
                os.path.join(abd_root, norm_proj),
                start=os.path.dirname(os.path.abspath(args.out_slice))
            ).replace("\\", "/")
        except Exception:
            norm_base = None

    out_slice_name = os.path.splitext(os.path.basename(args.out_slice))[0]
    passage_id = out_slice_name.replace("_source_slice", "")

    # Infer book_id if not provided.
    book_id = (args.book_id or "").strip()
    if not book_id:
        # Common repo convention: 2_atoms_and_excerpts/<n>_<bookid>_.../
        p = os.path.abspath(args.html).replace("\\", "/")
        m = re.search(r"/2_atoms_and_excerpts/\d+_([a-z0-9]+)_", p, flags=re.I)
        if m:
            book_id = m.group(1)
        else:
            # Fallback: take the last plausible match, ignoring known non-book segments.
            matches = re.findall(r"/\d+_([a-z0-9]+)_[^/]+/", p, flags=re.I)
            matches = [x for x in matches if x.lower() not in {"atoms"}]
            if matches:
                book_id = matches[-1]
    if not book_id:
        book_id = "UNKNOWN"

    slice_info = {
        "record_type": "source_locator",
        "locator_version": "0.1",
        "locator_id": f"{passage_id}:cp1_source_locator",
        "book_id": book_id,
        "passage_id": passage_id,
        "source_artifact": {
            "artifact_kind": "shamela_html_export",
            "baseline_relpath": baseline_rel_html,
            **({"project_relpath": proj_rel_html} if proj_rel_html else {}),
            "sha256": sha256_text(args.html),
            "notes": "Full-file sha256 for immutability; selectors identify the slice."
        },
        "selectors": [
            {
                "kind": "shamela_page_marker_range",
                "page_start": args.page_start,
                "page_end": args.page_end,
                "marker_pattern": "(ص: N) with Arabic-Indic digits"
            },
            {
                "kind": "html_char_range",
                "char_start": m1.start(),
                "char_end": end_pos
            }
        ],
        "normalization_contract": {
            "contract_relpath": norm_base or norm_proj,
            "contract_version": "0.1",
            "notes": "ABD-root-relative path preferred; baseline-relative fallback allowed."
        },
        "extraction_tool": {
            "tool_name": "extract_clean_input.py",
            "tool_version": "0.2",
            "tool_relpath": "tools/extract_clean_input.py",
            "command": " ".join(
                [
                    "python tools/extract_clean_input.py",
                    f"--html {baseline_rel_html}",
                    f"--page-start {args.page_start}",
                    f"--page-end {args.page_end}",
                    f"--out-matn {os.path.basename(args.out_matn)}",
                    f"--out-fn {os.path.basename(args.out_fn)}",
                    f"--out-slice {os.path.basename(args.out_slice)}"
                ]
            ),
            "notes": "CP1 reference extractor; footnote separation intentionally left downstream."
        },
        "outputs": {
            "clean_matn_input": os.path.basename(args.out_matn),
            "clean_fn_input": os.path.basename(args.out_fn)
        },
        "notes": "CP1 locator: v0.2 emits source_locator schema; older v0.1 format superseded."
    }

    open(args.out_slice, "w", encoding="utf-8").write(json.dumps(slice_info, ensure_ascii=False, indent=2))

    print(f"Wrote: {args.out_matn}")
    print(f"Wrote: {args.out_fn} (empty)")
    print(f"Wrote: {args.out_slice}")


if __name__ == "__main__":
    main()
