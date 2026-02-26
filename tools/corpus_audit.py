#!/usr/bin/env python3
"""Corpus-wide audit for Stage 1 normalization fixes.

Validates all 5 fixes from STAGE1_AUDIT_REPORT.md against the full corpus:
  1. seq_index uniqueness (no duplicate keys)
  2. has_verse false positive rate (balanced hemistich heuristic)
  3. Table cell separator (code uses ' | ', not '\t')
  4. footnote_ref_numbers deduplication
  5. ZWNJ heading marker detection

Usage:
    python tools/corpus_audit.py [--books-dir books/Other\ Books]
"""

import os
import re
import sys
import time
import json
import argparse
from pathlib import Path
from collections import defaultdict

# Add repo root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.normalize_shamela import (
    normalize_book, normalize_multivolume, discover_volume_files,
    PageRecord, HEMISTICH_SEP, VERSE_STAR_RE
)


def discover_books(corpus_dir: str) -> list[tuple[str, str, bool]]:
    """Discover all books in the corpus. Returns (name, path, is_multivolume)."""
    books = []
    for cat_dir in sorted(Path(corpus_dir).iterdir()):
        if not cat_dir.is_dir():
            continue
        for entry in sorted(cat_dir.iterdir()):
            if entry.is_file() and entry.suffix.lower() in ('.htm', '.html'):
                books.append((entry.stem, str(entry), False))
            elif entry.is_dir():
                # Check if it contains numbered .htm files
                htm_files = [f for f in entry.iterdir() if f.suffix.lower() == '.htm']
                if htm_files:
                    books.append((entry.name, str(entry), True))
    return books


def audit_book(name: str, path: str, is_multi: bool) -> dict:
    """Normalize one book and collect audit metrics."""
    book_id = f"audit_{hash(name) % 100000}"

    try:
        if is_multi:
            vol_files = discover_volume_files(path)
            if not vol_files:
                return {"name": name, "error": "no volume files found"}
            pages = []
            seq_offset = 0
            for vol_num, vol_path in vol_files:
                with open(vol_path, encoding="utf-8", errors="ignore") as f:
                    html = f.read()
                vol_pages, _ = normalize_book(html, book_id, vol_path,
                                              volume=vol_num, seq_offset=seq_offset)
                pages.extend(vol_pages)
                seq_offset += len(vol_pages)
        else:
            with open(path, encoding="utf-8", errors="ignore") as f:
                html = f.read()
            pages, _ = normalize_book(html, book_id, path)
    except Exception as e:
        return {"name": name, "error": str(e)}

    # --- Fix 1: seq_index uniqueness ---
    seq_indices = [p.seq_index for p in pages]
    seq_unique = len(seq_indices) == len(set(seq_indices))
    seq_monotonic = all(seq_indices[i] < seq_indices[i+1] for i in range(len(seq_indices)-1))

    # Old-style key duplicates: (volume, page_number_int)
    old_keys = [(p.volume, p.page_number_int) for p in pages]
    old_key_dupes = len(old_keys) - len(set(old_keys))

    # --- Fix 2: has_verse analysis ---
    verse_pages = [p for p in pages if p.has_verse]
    # Count pages that WOULD have been flagged under old heuristic (any … on page)
    old_heuristic_verse = sum(1 for p in pages if HEMISTICH_SEP in p.matn_text or VERSE_STAR_RE.search(p.matn_text))

    # --- Fix 3: table separator check (spot check) ---
    table_pages = [p for p in pages if p.has_tables]
    tables_use_pipe = all(' | ' in p.matn_text for p in table_pages) if table_pages else True
    tables_use_tab = any('\t' in p.matn_text for p in table_pages) if table_pages else False

    # --- Fix 4: footnote_ref_numbers dedup ---
    fn_ref_has_dupes = False
    for p in pages:
        if len(p.footnote_ref_numbers) != len(set(p.footnote_ref_numbers)):
            fn_ref_has_dupes = True
            break
        if p.footnote_ref_numbers != sorted(p.footnote_ref_numbers):
            fn_ref_has_dupes = True
            break

    # --- Fix 5: ZWNJ heading detection ---
    zwnj_pages = sum(1 for p in pages if p.starts_with_zwnj_heading)

    return {
        "name": name,
        "total_pages": len(pages),
        "seq_unique": seq_unique,
        "seq_monotonic": seq_monotonic,
        "old_key_dupes": old_key_dupes,
        "verse_pages_new": len(verse_pages),
        "verse_pages_old_heuristic": old_heuristic_verse,
        "table_pages": len(table_pages),
        "tables_use_pipe": tables_use_pipe,
        "tables_use_tab": tables_use_tab,
        "fn_ref_has_dupes": fn_ref_has_dupes,
        "zwnj_pages": zwnj_pages,
        "total_footnotes": sum(len(p.footnotes) for p in pages),
    }


def main():
    parser = argparse.ArgumentParser(description="Corpus-wide Stage 1 audit")
    parser.add_argument("--books-dir", default="books/Other Books",
                        help="Path to corpus directory")
    parser.add_argument("--json-out", default=None,
                        help="Optional: write raw results to JSON")
    args = parser.parse_args()

    print(f"Discovering books in {args.books_dir}...")
    books = discover_books(args.books_dir)
    print(f"Found {len(books)} books ({sum(1 for _,_,m in books if m)} multi-volume, "
          f"{sum(1 for _,_,m in books if not m)} single-volume)")

    results = []
    errors = []
    t0 = time.time()

    for i, (name, path, is_multi) in enumerate(books):
        if (i + 1) % 50 == 0 or i == 0:
            print(f"  Processing {i+1}/{len(books)}...", flush=True)
        r = audit_book(name, path, is_multi)
        if "error" in r:
            errors.append(r)
        else:
            results.append(r)

    elapsed = time.time() - t0
    total_pages = sum(r["total_pages"] for r in results)
    total_fns = sum(r["total_footnotes"] for r in results)

    print(f"\n{'='*72}")
    print(f"CORPUS AUDIT RESULTS  ({len(results)} books, {total_pages:,} pages, {total_fns:,} footnotes)")
    print(f"{'='*72}")
    print(f"Processed in {elapsed:.1f}s ({total_pages/elapsed:.0f} pages/sec)")
    if errors:
        print(f"\n⚠ {len(errors)} books failed to process:")
        for e in errors:
            print(f"  - {e['name']}: {e['error']}")

    # --- Fix 1: seq_index ---
    books_with_old_dupes = [r for r in results if r["old_key_dupes"] > 0]
    total_old_dupes = sum(r["old_key_dupes"] for r in results)
    seq_all_unique = all(r["seq_unique"] for r in results)
    seq_all_monotonic = all(r["seq_monotonic"] for r in results)
    print(f"\n--- Fix 1: DUPLICATE KEYS → seq_index ---")
    print(f"  OLD: {len(books_with_old_dupes)}/{len(results)} books ({len(books_with_old_dupes)/len(results)*100:.1f}%) "
          f"had duplicate (volume, page_number_int) keys ({total_old_dupes:,} total dupes)")
    print(f"  NEW: seq_index unique across all books: {'✅ YES' if seq_all_unique else '❌ NO'}")
    print(f"       seq_index monotonic across all books: {'✅ YES' if seq_all_monotonic else '❌ NO'}")

    # --- Fix 2: has_verse ---
    verse_new = sum(r["verse_pages_new"] for r in results)
    verse_old = sum(r["verse_pages_old_heuristic"] for r in results)
    false_positives_eliminated = verse_old - verse_new
    fp_rate_old = ((verse_old - verse_new) / verse_old * 100) if verse_old > 0 else 0
    print(f"\n--- Fix 2: has_verse FALSE POSITIVES ---")
    print(f"  OLD heuristic (any …): {verse_old:,} pages flagged as verse")
    print(f"  NEW heuristic (balanced hemistich ≥5 chars): {verse_new:,} pages flagged")
    print(f"  False positives eliminated: {false_positives_eliminated:,} ({fp_rate_old:.1f}%)")

    # --- Fix 3: table separator ---
    total_table_pages = sum(r["table_pages"] for r in results)
    all_pipe = all(r["tables_use_pipe"] for r in results)
    any_tab = any(r["tables_use_tab"] for r in results)
    print(f"\n--- Fix 3: TABLE CELL SEPARATOR ---")
    print(f"  Pages with tables: {total_table_pages}")
    print(f"  All use ' | ' separator: {'✅ YES' if all_pipe else '❌ NO'}")
    print(f"  Any use '\\t' separator: {'❌ YES' if any_tab else '✅ NO'}")

    # --- Fix 4: footnote_ref_numbers dedup ---
    books_with_fn_dupes = [r for r in results if r["fn_ref_has_dupes"]]
    print(f"\n--- Fix 4: footnote_ref_numbers DEDUPLICATION ---")
    print(f"  Books with duplicate/unsorted fn_ref_numbers: "
          f"{len(books_with_fn_dupes)}/{len(results)} {'✅ (none)' if not books_with_fn_dupes else '❌'}")

    # --- Fix 5: ZWNJ heading markers ---
    total_zwnj = sum(r["zwnj_pages"] for r in results)
    books_with_zwnj = sum(1 for r in results if r["zwnj_pages"] > 0)
    print(f"\n--- Fix 5: ZWNJ HEADING MARKERS ---")
    print(f"  Pages with ZWNJ heading marker: {total_zwnj:,} ({total_zwnj/total_pages*100:.1f}% of corpus)")
    print(f"  Books containing ZWNJ markers: {books_with_zwnj}/{len(results)}")

    # --- Overall verdict ---
    all_pass = (seq_all_unique and seq_all_monotonic and all_pipe and
                not any_tab and not books_with_fn_dupes)
    print(f"\n{'='*72}")
    print(f"OVERALL: {'✅ ALL FIXES VERIFIED' if all_pass else '❌ ISSUES REMAIN'}")
    print(f"{'='*72}")

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump({"results": results, "errors": errors}, f, ensure_ascii=False, indent=2)
        print(f"\nRaw results written to {args.json_out}")


if __name__ == "__main__":
    main()
