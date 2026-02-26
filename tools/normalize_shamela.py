#!/usr/bin/env python3
"""Normalize a Shamela HTML export into structured JSONL.

This tool is the first step of the ABD extraction pipeline.
It takes a raw Shamela desktop HTML export and produces:
  - A JSONL file with one record per printed page (matn + footnotes separated)
  - A normalization report (statistics and warnings)

The output is the input to atomization — it does NOT atomize.

Design principles:
  - NEVER alter the author's text (no spelling correction, no diacritic changes)
  - ONLY remove Shamela presentation artifacts (HTML tags, running headers, page markers)
  - Separate structural layers (matn vs footnotes) using reliable HTML markers
  - Preserve footnote cross-references as metadata, strip inline markers from text
  - Preserve all whitespace-significant boundaries (paragraphs, verse breaks)

Usage:
  python tools/normalize_shamela.py \\
    --html 2_atoms_and_excerpts/1_jawahir_al_balagha/shamela_export.htm \\
    --out-jsonl normalized_pages.jsonl \\
    --out-report normalization_report.json \\
    [--book-id jawahir]
"""

from __future__ import annotations

import argparse
import hashlib
import html as htmlmod
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional


# ─── Shamela HTML structural patterns ───────────────────────────────────────

# We split page blocks by finding all <div class='PageText'> start positions
# and taking the content between consecutive starts. This avoids the nested-div
# problem with regex-based matching.
PAGE_TEXT_START = "<div class='PageText'>"

# Running header: book title + page number + separator
PAGE_HEAD_RE = re.compile(
    r"<div class='PageHead'>.*?</div>",
    re.DOTALL
)

# Page number marker
PAGE_NUM_RE = re.compile(r"\(ص:\s*([٠-٩]+)\s*\)")

# Footnote separator (horizontal rule before footnotes)
FN_SEPARATOR_RE = re.compile(r"<hr\s+width='95'[^>]*>")

# Footnote content div
FN_DIV_RE = re.compile(r"<div class='footnote'>(.*?)</div>", re.DOTALL)

# Font color tags (Shamela uses red for numbering)
FONT_COLOR_RE = re.compile(r"<font\s+color=[^>]+>(.*?)</font>", re.DOTALL)

# Footnote reference marker in matn text: (N) where N is one or more digits
# Must handle: (1), (2), (12) — but NOT Quran references like (وأخي هارون...)
# Strategy: match (digits) followed by optional whitespace + period/dash/end
FN_REF_IN_MATN_RE = re.compile(r"\s*\((\d+)\)\s*(?=[.،؛\s]|$)")

# Footnote number prefix in footnote text: (N) ـ at start of footnote
FN_NUM_PREFIX_RE = re.compile(r"^\((\d+)\)\s*[ـ\-–]\s*")

# Verse star markers: * text * (rare in Shamela)
VERSE_STAR_RE = re.compile(r"\*\s*([^*]+?)\s*\*")

# Verse hemistich separator (ellipsis)
HEMISTICH_SEP = "…"


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class FootnoteRecord:
    """One footnote on a page."""
    number: int                   # The (N) number
    text: str                     # Cleaned footnote text (number prefix stripped)
    raw_text: str                 # Text before stripping number prefix

@dataclass
class PageRecord:
    """One printed page after normalization."""
    volume: int                   # Volume number (1 for single-volume books)
    page_number_arabic: str       # e.g. "٢٠"
    page_number_int: int          # e.g. 20
    matn_text: str                # Cleaned matn layer text
    footnotes: list[FootnoteRecord]  # Separated footnote entries
    footnote_ref_numbers: list[int]  # Footnote numbers referenced in matn
    has_verse: bool               # Whether the page contains verse/poetry
    is_image_only: bool           # True if page is an embedded scan with no text
    has_tables: bool              # True if page contains HTML tables
    warnings: list[str]           # Any normalization warnings
    raw_matn_html: str            # Original HTML of matn portion (for debugging)
    raw_fn_html: str              # Original HTML of footnote portion

@dataclass
class NormalizationReport:
    """Statistics from normalizing an entire book."""
    book_id: str
    source_file: str
    source_sha256: str
    volume: int                   # Volume number (1 for single-volume)
    total_pages: int
    pages_with_footnotes: int
    total_footnotes: int
    pages_with_verse: int
    pages_with_tables: int        # Pages containing HTML tables
    pages_image_only: int         # Pages that are embedded scans (no text)
    orphan_footnote_refs: int     # Refs in matn with no matching footnote
    orphan_footnotes: int         # Footnotes with no matching ref in matn
    warnings: list[str]
    pages_skipped: list[str]      # Pages that couldn't be parsed


# ─── Normalization functions ─────────────────────────────────────────────────

def arabic_to_int(arabic_num: str) -> int:
    """Convert Arabic-Indic numeral string to int."""
    mapping = {c: str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
    western = "".join(mapping.get(c, c) for c in arabic_num)
    return int(western)


def strip_tags(s: str) -> str:
    """Remove all HTML tags, converting block-level tags to line breaks."""
    # Remove scripts and styles
    s = re.sub(r"<script[\s\S]*?</script>", "", s, flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", "", s, flags=re.I)

    # Block-level breaks
    s = re.sub(r"<\s*br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</\s*p\s*>", "\n", s, flags=re.I)

    # Unwrap font color tags (keep content, lose the tag)
    s = FONT_COLOR_RE.sub(r"\1", s)

    # Drop all remaining tags
    s = re.sub(r"<[^>]+>", "", s)

    # Decode HTML entities
    s = htmlmod.unescape(s)

    return s


def normalize_whitespace(s: str) -> str:
    """Normalize whitespace while preserving paragraph structure."""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\u00a0", " ")  # non-breaking space → regular space

    # Collapse multiple spaces within lines
    lines = []
    for line in s.split("\n"):
        line = re.sub(r"[ \t]{2,}", " ", line).strip()
        lines.append(line)
    s = "\n".join(lines)

    # Collapse 3+ consecutive blank lines to 1
    s = re.sub(r"\n{3,}", "\n\n", s)

    return s.strip()


def strip_fn_refs_from_matn(text: str, known_fn_numbers: set[int] | None = None) -> tuple[str, list[int]]:
    """Remove footnote reference markers (N) from matn text.
    
    If known_fn_numbers is provided, only strip (N) where N is in that set.
    This prevents stripping exercise numbers like (1), (2) that look like
    footnote refs but aren't.
    
    Returns cleaned text and list of footnote numbers found.
    """
    refs_found = []

    def replace_ref(m):
        num = int(m.group(1))
        if known_fn_numbers is not None and num not in known_fn_numbers:
            return m.group(0)  # Keep it — not a real footnote ref
        refs_found.append(num)
        # The regex captures optional surrounding whitespace.
        # Replace with empty string to avoid leaving gaps.
        return ""

    # Strip (N) markers — digits only
    cleaned = FN_REF_IN_MATN_RE.sub(replace_ref, text)

    # Clean up double spaces created by removal (but don't touch original spacing)
    cleaned = re.sub(r"  +", " ", cleaned)

    return cleaned, refs_found


def clean_verse_markers(text: str) -> str:
    """Remove asterisk verse markers: * text * → text"""
    return VERSE_STAR_RE.sub(r"\1", text)


def detect_verse(text: str) -> bool:
    """Detect if page contains verse/poetry."""
    # Verse hemistich separator
    if HEMISTICH_SEP in text:
        return True
    # Star-marked verses
    if VERSE_STAR_RE.search(text):
        return True
    return False


def parse_footnotes(fn_html: str) -> list[FootnoteRecord]:
    """Parse footnote HTML into individual footnote records.
    
    Footnotes in Shamela are inside <div class='footnote'> and separated by
    (N) markers. The markers may or may not have a ـ dash after them.
    Within the HTML, subsequent footnote numbers are often wrapped in
    <font color=#be0000>(N)</font>.
    
    Strategy: 
    1. First, normalize the HTML by unwrapping font tags
    2. Convert to text
    3. Split at (N) boundaries that start a new footnote
    """
    if not fn_html or not fn_html.strip():
        return []

    # Strip tags
    fn_text = strip_tags(fn_html)
    fn_text = normalize_whitespace(fn_text)

    if not fn_text.strip():
        return []

    # Split at footnote number boundaries.
    # A footnote boundary is: (N) at the start of text, or (N) after a newline,
    # optionally followed by ـ or - or –
    # Pattern: start-or-newline, then (digits), then optional separator
    FN_BOUNDARY = re.compile(r"(?:^|\n)\((\d+)\)\s*(?:[ـ\-–]\s*)?", re.MULTILINE)
    
    records = []
    matches = list(FN_BOUNDARY.finditer(fn_text))
    
    if not matches:
        # No structured footnotes found — treat whole block as one note
        return []
    
    for i, m in enumerate(matches):
        num = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(fn_text)
        text = fn_text[start:end].strip()
        raw = fn_text[m.start():end].strip()
        records.append(FootnoteRecord(number=num, text=text, raw_text=raw))

    return records


# Embedded images (base64 page scans)
IMG_TAG_RE = re.compile(r"<img\s[^>]+>", re.I)

# HTML tables (content tables in matn)
TABLE_RE = re.compile(r"<table[^>]*>(.*?)</table>", re.I | re.DOTALL)
TABLE_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.DOTALL)
TABLE_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.DOTALL)


def extract_table_text(table_html: str) -> str:
    """Extract readable text from an HTML table.
    
    Converts table to plain text, reading left-to-right (RTL display order),
    row by row. Cells separated by ' | ', rows by newlines.
    """
    rows = TABLE_ROW_RE.findall(table_html)
    text_rows = []
    for row_html in rows:
        cells = TABLE_CELL_RE.findall(row_html)
        cell_texts = [normalize_whitespace(strip_tags(c)) for c in cells]
        cell_texts = [t for t in cell_texts if t]  # drop empty cells
        if cell_texts:
            text_rows.append(" | ".join(cell_texts))
    return "\n".join(text_rows)


def replace_tables_with_text(html: str) -> tuple[str, int]:
    """Replace <table> blocks with their extracted text content.
    
    Returns modified HTML and count of tables replaced.
    """
    count = 0
    def replacer(m):
        nonlocal count
        count += 1
        text = extract_table_text(m.group(0))
        return f"\n{text}\n"
    result = TABLE_RE.sub(replacer, html)
    return result, count


def detect_image_only_page(page_html: str) -> bool:
    """Detect if a page is just an embedded image scan with no text content."""
    if not IMG_TAG_RE.search(page_html):
        return False
    # Strip all tags and check if there's meaningful text left
    # (beyond the page number which is in the header)
    content = PAGE_HEAD_RE.sub("", page_html)
    content = IMG_TAG_RE.sub("", content)
    text = strip_tags(content)
    text = normalize_whitespace(text)
    # If the remaining text (after removing header + images) is trivially short,
    # it's an image-only page
    return len(text) < 10


def normalize_page(page_html: str, volume: int = 1) -> Optional[PageRecord]:
    """Normalize a single PageText block into a PageRecord."""
    warnings = []

    # Extract page number
    pn_match = PAGE_NUM_RE.search(page_html)
    if not pn_match:
        return None  # Skip pages without page numbers (metadata pages)

    page_arabic = pn_match.group(1)
    try:
        page_int = arabic_to_int(page_arabic)
    except ValueError:
        return None

    # Detect image-only pages (embedded scans)
    is_image_only = detect_image_only_page(page_html)
    if is_image_only:
        warnings.append("IMAGE_ONLY_PAGE: page is an embedded scan with no extractable text")
        return PageRecord(
            volume=volume,
            page_number_arabic=page_arabic,
            page_number_int=page_int,
            matn_text="",
            footnotes=[],
            footnote_ref_numbers=[],
            has_verse=False,
            is_image_only=True,
            has_tables=False,
            warnings=warnings,
            raw_matn_html=page_html,
            raw_fn_html="",
        )

    # Remove running header
    content = PAGE_HEAD_RE.sub("", page_html)

    # Split matn and footnotes at the horizontal rule
    fn_sep = FN_SEPARATOR_RE.search(content)
    if fn_sep:
        matn_html = content[:fn_sep.start()]
        fn_html = content[fn_sep.end():]
    else:
        matn_html = content
        fn_html = ""

    # Store raw HTML for debugging
    raw_matn_html = matn_html
    raw_fn_html = fn_html

    # Replace tables with extracted text (before stripping tags)
    matn_html, table_count = replace_tables_with_text(matn_html)
    has_tables = table_count > 0
    if has_tables:
        warnings.append(f"TABLES_EXTRACTED: {table_count} table(s) converted to text")

    # Remove any <img> tags from matn (they're page scans, not content)
    matn_html = IMG_TAG_RE.sub("", matn_html)

    # Detect verse before stripping
    has_verse = detect_verse(strip_tags(matn_html))

    # Parse footnotes FIRST so we know which numbers are real footnote refs
    footnotes = parse_footnotes(fn_html)
    fn_numbers = {fn.number for fn in footnotes}

    # Clean matn
    matn_text = strip_tags(matn_html)
    matn_text = clean_verse_markers(matn_text)
    matn_text, fn_refs = strip_fn_refs_from_matn(matn_text, known_fn_numbers=fn_numbers)
    matn_text = normalize_whitespace(matn_text)

    # Validate cross-references
    fn_numbers = {fn.number for fn in footnotes}
    ref_numbers = set(fn_refs)

    orphan_refs = ref_numbers - fn_numbers
    orphan_fns = fn_numbers - ref_numbers

    if orphan_refs:
        warnings.append(f"Footnote refs in matn with no matching footnote: {sorted(orphan_refs)}")
    if orphan_fns:
        warnings.append(f"Footnotes with no matching ref in matn: {sorted(orphan_fns)}")

    return PageRecord(
        volume=volume,
        page_number_arabic=page_arabic,
        page_number_int=page_int,
        matn_text=matn_text,
        footnotes=footnotes,
        footnote_ref_numbers=sorted(fn_refs),
        has_verse=has_verse,
        is_image_only=False,
        has_tables=has_tables,
        warnings=warnings,
        raw_matn_html=raw_matn_html,
        raw_fn_html=raw_fn_html,
    )


def normalize_book(html_text: str, book_id: str, source_path: str, volume: int = 1) -> tuple[list[PageRecord], NormalizationReport]:
    """Normalize an entire Shamela HTML export (one volume file)."""
    pages = []
    all_warnings = []
    skipped = []

    # Find all PageText blocks by splitting at boundaries
    starts = [m.start() for m in re.finditer(re.escape(PAGE_TEXT_START), html_text)]
    blocks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(html_text)
        blocks.append(html_text[start:end])

    for block in blocks:
        page = normalize_page(block, volume=volume)
        if page is None:
            # Try to identify what we skipped
            pn = PAGE_NUM_RE.search(block)
            if pn:
                skipped.append(pn.group(1))
            else:
                skipped.append("(no page number)")
            continue
        pages.append(page)

    # Compute source hash
    source_hash = hashlib.sha256(html_text.encode("utf-8")).hexdigest()

    # Aggregate statistics
    total_fns = sum(len(p.footnotes) for p in pages)
    orphan_refs = sum(1 for p in pages for w in p.warnings if "no matching footnote" in w)
    orphan_fns = sum(1 for p in pages for w in p.warnings if "no matching ref" in w)

    for p in pages:
        for w in p.warnings:
            all_warnings.append(f"v{volume} p{p.page_number_arabic}: {w}")

    report = NormalizationReport(
        book_id=book_id,
        source_file=source_path,
        source_sha256=source_hash,
        volume=volume,
        total_pages=len(pages),
        pages_with_footnotes=sum(1 for p in pages if p.footnotes),
        total_footnotes=total_fns,
        pages_with_verse=sum(1 for p in pages if p.has_verse),
        pages_with_tables=sum(1 for p in pages if p.has_tables),
        pages_image_only=sum(1 for p in pages if p.is_image_only),
        orphan_footnote_refs=orphan_refs,
        orphan_footnotes=orphan_fns,
        warnings=all_warnings,
        pages_skipped=skipped,
    )

    return pages, report


# ─── JSONL serialization ────────────────────────────────────────────────────

def page_to_jsonl_record(page: PageRecord, book_id: str) -> dict:
    """Convert a PageRecord to a JSON-serializable dict for JSONL output.
    
    Omits raw HTML fields (they're for debugging, not for output).
    """
    rec = {
        "record_type": "normalized_page",
        "book_id": book_id,
        "volume": page.volume,
        "page_number_arabic": page.page_number_arabic,
        "page_number_int": page.page_number_int,
        "matn_text": page.matn_text,
        "footnotes": [
            {
                "number": fn.number,
                "text": fn.text,
            }
            for fn in page.footnotes
        ],
        "footnote_ref_numbers": page.footnote_ref_numbers,
        "has_verse": page.has_verse,
        "is_image_only": page.is_image_only,
        "has_tables": page.has_tables,
        "warnings": page.warnings,
    }
    return rec


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Normalize a Shamela HTML export into structured JSONL.")
    ap.add_argument("--html", required=True, help="Path to Shamela HTML export")
    ap.add_argument("--out-jsonl", required=True, help="Output JSONL file path")
    ap.add_argument("--out-report", required=True, help="Output normalization report JSON path")
    ap.add_argument("--book-id", default="", help="Book identifier (inferred from path if omitted)")
    ap.add_argument("--volume", type=int, default=None,
                     help="Volume number (inferred from filename if omitted, defaults to 1)")
    ap.add_argument("--include-raw-html", action="store_true",
                     help="Include raw HTML in JSONL output (for debugging)")
    ap.add_argument("--page-start", type=int, default=None,
                     help="Only process pages from this number onward")
    ap.add_argument("--page-end", type=int, default=None,
                     help="Only process pages up to this number")
    args = ap.parse_args()

    # Infer book_id
    book_id = args.book_id
    if not book_id:
        m = re.search(r"/\d+_([a-z0-9]+)_", args.html.replace("\\", "/"), re.I)
        book_id = m.group(1) if m else "unknown"

    # Infer volume from filename if not specified
    volume = args.volume
    if volume is None:
        stem = os.path.splitext(os.path.basename(args.html))[0]
        try:
            volume = int(stem)
        except ValueError:
            volume = 1  # Single-volume book

    # Read source
    with open(args.html, encoding="utf-8", errors="ignore") as f:
        html_text = f.read()

    print(f"Source: {args.html} ({len(html_text)} chars)")
    print(f"Book ID: {book_id}")
    print(f"Volume: {volume}")

    # Normalize
    pages, report = normalize_book(html_text, book_id, args.html, volume=volume)

    # Filter page range if specified
    if args.page_start is not None:
        pages = [p for p in pages if p.page_number_int >= args.page_start]
    if args.page_end is not None:
        pages = [p for p in pages if p.page_number_int <= args.page_end]

    # Write JSONL
    os.makedirs(os.path.dirname(os.path.abspath(args.out_jsonl)) or ".", exist_ok=True)
    with open(args.out_jsonl, "w", encoding="utf-8") as f:
        for page in pages:
            rec = page_to_jsonl_record(page, book_id)
            if args.include_raw_html:
                rec["raw_matn_html"] = page.raw_matn_html
                rec["raw_fn_html"] = page.raw_fn_html
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Write report
    os.makedirs(os.path.dirname(os.path.abspath(args.out_report)) or ".", exist_ok=True)
    with open(args.out_report, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, ensure_ascii=False, indent=2)

    # Print summary
    print(f"\nNormalized {report.total_pages} pages (volume {volume})")
    print(f"  Pages with footnotes: {report.pages_with_footnotes}")
    print(f"  Total footnotes: {report.total_footnotes}")
    print(f"  Pages with verse: {report.pages_with_verse}")
    if report.pages_with_tables:
        print(f"  Pages with tables: {report.pages_with_tables}")
    if report.pages_image_only:
        print(f"  ⚠ Image-only pages (no text): {report.pages_image_only}")
    if report.orphan_footnote_refs:
        print(f"  ⚠ Orphan footnote refs: {report.orphan_footnote_refs}")
    if report.orphan_footnotes:
        print(f"  ⚠ Orphan footnotes: {report.orphan_footnotes}")
    if report.pages_skipped:
        print(f"  Skipped pages: {report.pages_skipped}")
    if report.warnings:
        print(f"  Total warnings: {len(report.warnings)}")

    print(f"\nWrote: {args.out_jsonl}")
    print(f"Wrote: {args.out_report}")


if __name__ == "__main__":
    main()
