#!/usr/bin/env python3
"""Stage 2: Structure Discovery — discover book divisions and build passage boundaries.

Three-pass algorithm:
  Pass 1   (Tier 1): Extract HTML-tagged headings (<span class="title">)
  Pass 1.5        : Parse table of contents (TOC) if detected
  Pass 2   (Tier 2): Keyword heuristic detection from normalized text
  Pass 3   (Tier 3): LLM-assisted discovery (hierarchy, gaps, digestibility)

Then: build division tree, construct passages, generate output artifacts.

Usage:
  python tools/discover_structure.py \\
    --html books/jawahir/source/jawahir_al_balagha.htm \\
    --pages 1_normalization/jawahir_normalized_full.jsonl \\
    --metadata books/jawahir/intake_metadata.json \\
    --patterns 2_structure_discovery/structural_patterns.yaml \\
    --outdir output/jawahir_structure \\
    [--skip-llm]  # Run only deterministic passes
    [--apply-overrides overrides.json]

Version: v0.2 (critical bug fixes — see git log)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOOL_VERSION = "v0.3"
TOOL_NAME = "tools/discover_structure.py"

# Arabic-Indic digit map
_INDIC = "٠١٢٣٤٥٦٧٨٩"
_INDIC_TO_INT = {c: i for i, c in enumerate(_INDIC)}

# Ordinal lookup — maps Arabic ordinal text to integer
ORDINALS: dict[str, int] = {}

# Citation patterns that indicate a keyword is being referenced, not used as a heading
CITATION_PREFIXES = [
    "قال في", "ذكر في", "كما في", "انظر", "ارجع إلى",
    "راجع", "في كتاب", "في باب", "في فصل",
    "ورد في", "جاء في", "نقل في",
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HeadingCandidate:
    """A candidate structural heading found by Pass 1 or Pass 2."""
    title: str
    seq_index: int
    page_number_int: int
    volume: int
    page_hint: str
    detection_method: str  # html_tagged | keyword_heuristic
    confidence: str  # confirmed | high | medium | low
    keyword_type: Optional[str] = None
    ordinal: Optional[int] = None
    inline_heading: bool = False
    heading_text_boundary: Optional[int] = None
    notes: Optional[str] = None
    document_position: int = 0  # counter preserving order within same page (0, 1, 2, ...)
    page_mapped: bool = True     # False if heading's page was not found in the JSONL


@dataclass
class TOCEntry:
    """A parsed entry from the book's table of contents."""
    title: str
    page_number: Optional[int]
    indent_level: int = 0
    line_index: int = 0


@dataclass
class PageRecord:
    """Minimal page record from Stage 1 JSONL."""
    seq_index: int
    page_number_int: int
    volume: int
    matn_text: str
    page_hint: str
    footnote_section_format: str = "none"
    starts_with_zwnj_heading: bool = False


@dataclass
class DivisionNode:
    """A node in the division tree."""
    id: str
    type: str
    title: str
    level: int
    detection_method: str
    confidence: str
    digestible: str  # "true", "false", "uncertain"
    content_type: Optional[str]  # teaching, exercise, mixed, non_content
    start_seq_index: int
    end_seq_index: int
    page_hint_start: str
    page_hint_end: str
    parent_id: Optional[str]
    child_ids: list[str] = field(default_factory=list)
    page_count: int = 1
    ordinal: Optional[int] = None
    editor_inserted: bool = False
    heading_in_html: bool = False
    inline_heading: bool = False
    heading_text_boundary: Optional[int] = None
    review_flags: list[str] = field(default_factory=list)
    detection_notes: Optional[str] = None
    human_override: Optional[dict] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class PassageRecord:
    """A passage — the unit of work for Stage 3."""
    passage_id: str
    book_id: str
    division_ids: list[str]
    title: str
    heading_path: list[str]
    start_seq_index: int
    end_seq_index: int
    page_hint_start: str
    page_hint_end: str
    page_count: int
    volume: Optional[int]
    digestible: bool
    content_type: str
    sizing_action: str  # none, merged, split, flagged_long
    sizing_notes: Optional[str]
    split_info: Optional[dict]
    merge_info: Optional[dict]
    review_flags: list[str]
    science_id: Optional[str]
    predecessor_passage_id: Optional[str]
    successor_passage_id: Optional[str]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["record_type"] = "passage"
        return d


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def indic_to_int(s: str) -> int:
    """Convert Arabic-Indic digit string to integer."""
    return int("".join(str(_INDIC_TO_INT.get(c, c)) for c in s))


def int_to_indic(n: int) -> str:
    """Convert integer to Arabic-Indic digit string."""
    return "".join(_INDIC[int(d)] for d in str(n))


def make_page_hint(volume: int, page_number_int: int, multi_volume: bool = False) -> str:
    """Create a human-readable page hint string."""
    if multi_volume:
        return f"ج{int_to_indic(volume)} ص:{int_to_indic(page_number_int)}"
    return f"ص:{int_to_indic(page_number_int)}"


def sha256_file(path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_arabic_for_match(text: str) -> str:
    """Normalize Arabic text for fuzzy matching: strip diacritics, normalize ى/ي, collapse whitespace."""
    # Strip common diacritics
    diacritics = "\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652\u0653\u0654\u0655\u0670"
    out = "".join(c for c in text if c not in diacritics)
    # Normalize alef-maqsura / ya
    out = out.replace("ى", "ي")
    # Normalize alef variants
    out = out.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا")
    # Collapse whitespace
    out = re.sub(r"\s+", " ", out).strip()
    return out


def load_ordinals(patterns: dict) -> dict[str, int]:
    """Build ordinal lookup from structural_patterns.yaml."""
    ordinals: dict[str, int] = {}
    raw_list = patterns.get("ordinal_patterns", {}).get("arabic_ordinals", [])
    for i, entry in enumerate(raw_list, start=1):
        for variant in entry.split("|"):
            variant = variant.strip()
            if variant:
                ordinals[variant] = i
    return ordinals


def load_keywords(patterns: dict) -> dict[str, dict]:
    """Build keyword set from structural_patterns.yaml.

    Returns dict mapping keyword -> {level, max_standalone_len, ...}
    """
    keywords: dict[str, dict] = {}
    kp = patterns.get("keyword_patterns", {})

    for level_name, level_data in [
        ("top_level", kp.get("top_level", [])),
        ("mid_level", kp.get("mid_level", [])),
        ("low_level", kp.get("low_level", [])),
        ("supplementary", kp.get("supplementary", [])),
    ]:
        if isinstance(level_data, list):
            for entry in level_data:
                kw = entry.get("keyword", "")
                if kw:
                    keywords[kw] = {"level": level_name, **entry}
                definite = entry.get("definite_form", "")
                if definite and definite != kw:
                    keywords[definite] = {"level": level_name, **entry}
                # Add plural/dual forms
                for form_key in ("plural", "dual", "variants"):
                    forms = entry.get(form_key)
                    if isinstance(forms, str):
                        forms = [forms]
                    if isinstance(forms, list):
                        for form in forms:
                            if form:
                                keywords[form] = {"level": level_name, **entry}

    return keywords


# ---------------------------------------------------------------------------
# Pass 1: HTML-Tagged Heading Extraction
# ---------------------------------------------------------------------------

def pass1_extract_html_headings(
    html_path: str,
    page_index: dict[tuple[int, int], PageRecord],
    volume_number: int = 1,
    multi_volume: bool = False,
    pages_list: Optional[list[PageRecord]] = None,
) -> tuple[list[HeadingCandidate], list[int], int]:
    """Extract content headings from <span class="title"> in frozen HTML.

    Args:
        html_path: path to the frozen source HTML file
        page_index: mapping (volume, page_number_int) -> PageRecord
        volume_number: volume number for this HTML file
        multi_volume: whether the book has multiple volumes
        pages_list: ordered list of PageRecord from JSONL (for positional mapping)

    Returns:
        (list of HeadingCandidate, list of TOC page seq_indices, HTML content page count)
    """
    with open(html_path, encoding="utf-8") as f:
        html = f.read()

    headings: list[HeadingCandidate] = []
    toc_pages: list[int] = []

    # Split into PageText divs
    page_divs = re.split(r"<div class='PageText'>", html)

    # Skip index 0 (before first PageText) and index 1 (metadata page)
    if len(page_divs) < 3:
        return headings, toc_pages, 0

    content_divs = page_divs[2:]  # Skip pre-HTML and metadata page
    html_page_count = len(content_divs)

    # Build positional mapping: HTML div position → seq_index
    # This handles duplicate page numbers correctly because it uses
    # the same ordering as the normalization tool.
    positional_map: dict[int, PageRecord] = {}  # div_position → PageRecord
    if pages_list:
        for pos, page in enumerate(pages_list):
            positional_map[pos] = page

    current_page_number = 0
    current_seq_index = -1  # -1 means "not yet mapped"
    current_page_mapped = False
    heading_counter = 0  # global document-order counter

    for div_pos, div_text in enumerate(content_divs):
        # Update current page number from PageNumber span
        pn_match = re.search(r"<span class='PageNumber'>\(ص:\s*([٠-٩]+)\s*\)</span>", div_text)
        if pn_match:
            current_page_number = indic_to_int(pn_match.group(1))

        # Strategy: prefer positional mapping (handles duplicate page numbers);
        # fall back to page_index lookup when positional map is unavailable.
        if div_pos in positional_map:
            pr = positional_map[div_pos]
            current_seq_index = pr.seq_index
            current_page_mapped = True
        else:
            # Fallback: lookup by (volume, page_number_int)
            key = (volume_number, current_page_number)
            if key in page_index:
                current_seq_index = page_index[key].seq_index
                current_page_mapped = True
            else:
                # Try to find by page_number_int alone (single-volume fallback)
                found = False
                for (v, p), rec in page_index.items():
                    if p == current_page_number and v == volume_number:
                        current_seq_index = rec.seq_index
                        current_page_mapped = True
                        found = True
                        break
                if not found:
                    current_page_mapped = False
                    # Don't update current_seq_index — keep stale value

        # Find all double-quote title spans in this page div
        title_spans = re.finditer(r'<span class="title">(.*?)</span>', div_text)

        for m in title_spans:
            raw_text = m.group(1)
            # R1.2: Clean heading text
            clean = re.sub(r"<[^>]+>", "", raw_text)  # Strip nested tags
            clean = clean.replace("&nbsp;", "").replace("&#8204;", "")  # Remove NBSP, ZWNJ
            clean = re.sub(r"\s+", " ", clean).strip()  # Collapse whitespace

            if not clean:
                continue

            page_hint = make_page_hint(volume_number, current_page_number, multi_volume)

            # R1.5: Detect TOC headings — EXACT match only (not substring, not prefix)
            # These are the specific heading texts that indicate a table of contents.
            # Other headings starting with فهرس (like فهرس المصطلحات) are glossaries, not TOCs.
            toc_exact_titles = {
                "فهرس", "المحتويات", "فهرس الموضوعات",
                "فهرس المحتويات", "الفهرس", "فهارس",
                "فهرس الكتاب", "محتويات الكتاب",
            }
            clean_stripped = clean.strip()
            is_toc = clean_stripped in toc_exact_titles
            if is_toc and current_page_mapped:
                toc_pages.append(current_seq_index)

            headings.append(HeadingCandidate(
                title=clean,
                seq_index=current_seq_index if current_page_mapped else -1,
                page_number_int=current_page_number,
                volume=volume_number,
                page_hint=page_hint,
                detection_method="html_tagged",
                confidence="confirmed",
                notes="TOC heading" if is_toc else None,
                document_position=heading_counter,
                page_mapped=current_page_mapped,
            ))
            heading_counter += 1

    return headings, toc_pages, html_page_count


# ---------------------------------------------------------------------------
# Pass 1.5: TOC Parsing
# ---------------------------------------------------------------------------

# Dot-leader pattern: title text, then dots/ellipses, then page number
_TOC_LINE_RE = re.compile(
    r"^(.+?)\s*[\.·…]{3,}\s*([٠-٩0-9]+)\s*$"
)

def pass1_5_parse_toc(
    pages: list[PageRecord],
    toc_page_indices: list[int],
) -> list[TOCEntry]:
    """Parse TOC pages for dot-leader entries.

    Args:
        pages: all page records
        toc_page_indices: seq_index values of pages identified as TOC pages

    Returns:
        list of TOCEntry records
    """
    if not toc_page_indices:
        return []

    entries: list[TOCEntry] = []
    toc_set = set(toc_page_indices)

    # Determine TOC page range: from first TOC heading to a bounded window after
    # the last TOC heading. TOCs typically span a few consecutive pages.
    # We scan the TOC heading pages plus up to 10 pages after the last TOC heading
    # (to catch continuation pages that don't have their own heading).
    min_toc_idx = min(toc_set)
    max_toc_idx = max(toc_set)
    toc_scan_end = max_toc_idx + 10  # bounded window

    # Track density: if we scan 3 consecutive pages with no TOC entries, stop
    pages_without_entries = 0
    MAX_EMPTY_PAGES = 3

    for page in pages:
        if page.seq_index < min_toc_idx:
            continue
        if page.seq_index > toc_scan_end:
            break

        page_had_entries = False
        for line_i, line in enumerate(page.matn_text.split("\n")):
            line = line.strip()
            if not line:
                continue

            m = _TOC_LINE_RE.match(line)
            if m:
                title = m.group(1).strip()
                page_str = m.group(2)
                try:
                    page_num = indic_to_int(page_str) if any(c in _INDIC for c in page_str) else int(page_str)
                except ValueError:
                    continue

                # Estimate indent level from leading whitespace in original line
                raw_line = page.matn_text.split("\n")[line_i] if line_i < len(page.matn_text.split("\n")) else line
                indent = len(raw_line) - len(raw_line.lstrip())
                indent_level = indent // 2  # Rough heuristic

                entries.append(TOCEntry(
                    title=title,
                    page_number=page_num,
                    indent_level=indent_level,
                    line_index=line_i,
                ))
                page_had_entries = True

        # Density check: stop scanning if no entries for several consecutive pages
        if page.seq_index > max_toc_idx:  # Only apply density check after last TOC heading
            if page_had_entries:
                pages_without_entries = 0
            else:
                pages_without_entries += 1
                if pages_without_entries >= MAX_EMPTY_PAGES:
                    break

    return entries


# ---------------------------------------------------------------------------
# Pass 2: Keyword Heuristic Detection
# ---------------------------------------------------------------------------

# Pre-compiled ordinal pattern — built locally per call to avoid global mutable state


def _build_ordinal_regex(ordinals: dict[str, int]) -> re.Pattern:
    """Build a regex that matches any Arabic ordinal."""
    # Sort by length descending so longer matches take priority
    sorted_ords = sorted(ordinals.keys(), key=len, reverse=True)
    escaped = [re.escape(o) for o in sorted_ords]
    return re.compile(r"(?:" + "|".join(escaped) + r")")


def pass2_keyword_scan(
    pages: list[PageRecord],
    keywords: dict[str, dict],
    ordinals: dict[str, int],
    pass1_headings: list[HeadingCandidate],
    multi_volume: bool = False,
    next_doc_position: int = 0,
) -> list[HeadingCandidate]:
    """Scan normalized text for keyword-based heading candidates.

    Implements the conservative rules from STRUCTURE_SPEC v1.0 §6.

    Args:
        pages: all page records from Stage 1 JSONL
        keywords: keyword dict from structural_patterns.yaml
        ordinals: ordinal dict
        pass1_headings: headings already found by Pass 1 (for dedup)
        multi_volume: whether book is multi-volume
        next_doc_position: starting document_position counter (continue from Pass 1)

    Returns:
        New heading candidates not already found by Pass 1.
    """
    ordinal_re = _build_ordinal_regex(ordinals) if ordinals else None

    # Build Pass 1 dedup index: (seq_index, normalized_title_prefix) -> True
    pass1_index: set[tuple[int, str]] = set()
    for h in pass1_headings:
        norm = normalize_arabic_for_match(h.title)[:30]
        pass1_index.add((h.seq_index, norm))

    candidates: list[HeadingCandidate] = []
    doc_pos = next_doc_position

    # Sort keywords by length descending for matching priority
    sorted_keywords = sorted(keywords.keys(), key=len, reverse=True)
    # Build regex: match keyword at start of line followed by word boundary
    kw_pattern = re.compile(
        r"^(" + "|".join(re.escape(kw) for kw in sorted_keywords) + r")(?=[\s:؛\-–—]|$)"
    )

    for page in pages:
        lines = page.matn_text.split("\n")
        for line_idx, line in enumerate(lines):
            raw_line = line
            line = line.strip()
            if not line:
                continue

            # C1: Keyword at line start with word boundary
            m = kw_pattern.match(line)
            if not m:
                continue

            matched_keyword = m.group(1)
            rest_after_keyword = line[m.end():]

            # C-STRICT: Some keywords in indefinite form require ordinal or very short line.
            # كتاب (without ال) is a common noun; only treat as heading if structural evidence is strong.
            STRICT_INDEFINITE = {"كتاب"}
            if matched_keyword in STRICT_INDEFINITE:
                has_ordinal = False
                if ordinal_re:
                    rest_stripped_check = rest_after_keyword.strip()
                    if rest_stripped_check and ordinal_re.match(rest_stripped_check):
                        has_ordinal = True
                if not has_ordinal and len(line) > 20:
                    continue  # Skip: indefinite كتاب without ordinal in a non-trivial line

            # C2: Not a TOC entry (dot-leader pattern)
            # Catches: multiple dots/middots followed by digits, ellipsis+digits at end of line.
            # Only reject patterns that look like TOC entries (dots/ellipsis followed by page number).
            # Do NOT reject lines that merely contain an ellipsis as text omission.
            if re.search(r"[\.·]{3,}\s*[٠-٩0-9]+\s*$", line):
                continue
            if re.search(r"…+\s*[٠-٩0-9]+\s*$", line):  # Ellipsis character(s) then page number
                continue
            if re.search(r"\.{2,}\s*[٠-٩0-9]+\s*$", line):  # dots then page number at end
                continue

            # C3: Not inside footnote text
            # Stage 1 separates matn from footnotes, so matn_text should not contain footnotes.
            # But check the format just in case.

            # C5 + C6: Structural pattern matching with length limits
            confidence = None
            ordinal_value = None
            inline = False
            heading_boundary = None

            rest_stripped = rest_after_keyword.strip()

            # Try pattern: KEYWORD ORDINAL: TITLE (max 120 chars)
            if ordinal_re and len(line) <= 120:
                ord_match = ordinal_re.match(rest_stripped) if rest_stripped else None
                if ord_match:
                    ordinal_text = ord_match.group(0)
                    ordinal_value = ordinals.get(ordinal_text)
                    after_ordinal = rest_stripped[ord_match.end():].strip()
                    if after_ordinal and after_ordinal[0] in ":؛":
                        # KEYWORD ORDINAL: TITLE
                        confidence = "high"
                    elif not after_ordinal or len(after_ordinal) < 3:
                        # KEYWORD ORDINAL (alone)
                        if len(line) <= 60:
                            confidence = "high"
                    elif len(line) <= 120:
                        # KEYWORD ORDINAL TITLE (no separator)
                        confidence = "high"

            # Try pattern: KEYWORD في TITLE or KEYWORD: TITLE (max 100 chars)
            if confidence is None and len(line) <= 100:
                if rest_stripped and rest_stripped[0] in ":؛":
                    confidence = "medium"
                elif rest_stripped.startswith("في ") or rest_stripped.startswith("فى "):
                    confidence = "medium"

            # Try pattern: KEYWORD alone (max 30 chars)
            if confidence is None and len(line) <= 30 and not rest_stripped:
                confidence = "medium"

            # Try pattern: KEYWORD - CONTENT or KEYWORD: CONTENT (inline, max 400 chars)
            if confidence is None and len(line) <= 400:
                sep_match = re.match(r"\s*[-–—:؛]\s*", rest_after_keyword)
                if sep_match:
                    confidence = "medium"
                    inline = True
                    heading_boundary = m.end() + sep_match.end()

            # If no pattern matched, skip
            if confidence is None:
                continue

            # C4: Not a citation (only relevant if keyword is NOT at position 0 in the original
            # matn_text, but here we're checking line-starts, so C4 doesn't apply to the keyword
            # itself. However, we check the preceding line for context.)
            # Actually: check the end of the preceding line for citation patterns
            if line_idx > 0:
                prev_line = lines[line_idx - 1].strip()
                if prev_line:
                    prev_tail = prev_line[-40:] if len(prev_line) > 40 else prev_line
                    if any(cp in prev_tail for cp in CITATION_PREFIXES):
                        continue

            # Dedup with Pass 1
            norm_title = normalize_arabic_for_match(line)[:30]
            if (page.seq_index, norm_title) in pass1_index:
                continue

            # Build heading title
            if inline and heading_boundary is not None:
                title = line[:heading_boundary].strip().rstrip("-–—:؛").strip()
            else:
                title = line

            candidates.append(HeadingCandidate(
                title=title,
                seq_index=page.seq_index,
                page_number_int=page.page_number_int,
                volume=page.volume,
                page_hint=make_page_hint(page.volume, page.page_number_int, multi_volume),
                detection_method="keyword_heuristic",
                confidence=confidence,
                keyword_type=matched_keyword,
                ordinal=ordinal_value,
                inline_heading=inline,
                heading_text_boundary=heading_boundary,
                document_position=doc_pos,
            ))
            doc_pos += 1

    return candidates


# ---------------------------------------------------------------------------
# Page loading
# ---------------------------------------------------------------------------

def load_pages(jsonl_path: str) -> list[PageRecord]:
    """Load Stage 1 JSONL into PageRecord list."""
    pages = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            pages.append(PageRecord(
                seq_index=rec.get("seq_index", len(pages)),
                page_number_int=rec.get("page_number_int", 0),
                volume=rec.get("volume", 1),
                matn_text=rec.get("matn_text", ""),
                page_hint=f"ص:{int_to_indic(rec.get('page_number_int', 0))}",
                footnote_section_format=rec.get("footnote_section_format", "none"),
                starts_with_zwnj_heading=rec.get("starts_with_zwnj_heading", False),
            ))
    return pages


def build_page_index(pages: list[PageRecord]) -> dict[tuple[int, int], PageRecord]:
    """Build (volume, page_number_int) -> PageRecord index.

    For duplicate page numbers within a volume, the first occurrence wins.
    Consumers should prefer seq_index for unambiguous lookup.
    """
    idx: dict[tuple[int, int], PageRecord] = {}
    for p in pages:
        key = (p.volume, p.page_number_int)
        if key not in idx:
            idx[key] = p
    return idx


# ---------------------------------------------------------------------------
# Pass 3: LLM-Assisted Discovery (Tier 3)
# ---------------------------------------------------------------------------

LLM_DEFAULT_MODEL = "claude-sonnet-4-20250514"
LLM_MAX_RETRIES = 3


def _init_llm_client():
    """Initialize Anthropic client. Returns (client, error_message)."""
    try:
        import anthropic
    except ImportError:
        return None, "anthropic package not installed. Install with: pip install anthropic --break-system-packages"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None, "ANTHROPIC_API_KEY environment variable not set."

    return anthropic.Anthropic(api_key=api_key), None


def call_llm(client, prompt: str, *, max_tokens: int = 4096, model: str = LLM_DEFAULT_MODEL) -> Optional[dict]:
    """Call LLM and parse JSON response. Returns parsed dict or None on failure.

    Handles markdown fence stripping, retry on JSON parse failure (up to LLM_MAX_RETRIES).
    """
    last_raw = ""
    for attempt in range(LLM_MAX_RETRIES):
        try:
            messages = [{"role": "user", "content": prompt}]
            if attempt > 0:
                # On retry, append error feedback
                messages.append({"role": "assistant", "content": last_raw})
                messages.append({
                    "role": "user",
                    "content": f"Your response was not valid JSON. Error: {last_error}. "
                               "Please respond with ONLY a valid JSON object, no markdown fences or preamble."
                })

            response = client.messages.create(
                model=model, max_tokens=max_tokens, messages=messages,
            )
            raw_text = response.content[0].text.strip()
            last_raw = raw_text

            # Strip markdown fences if present
            clean = re.sub(r"^```(?:json)?\s*", "", raw_text)
            clean = re.sub(r"\s*```\s*$", "", clean).strip()

            result = json.loads(clean)
            return result

        except json.JSONDecodeError as e:
            last_error = str(e)
            print(f"  [LLM] JSON parse error (attempt {attempt + 1}/{LLM_MAX_RETRIES}): {e}")
            if attempt < LLM_MAX_RETRIES - 1:
                print(f"  [LLM] Retrying...")
            continue
        except Exception as e:
            print(f"  [LLM] API error: {e}", file=sys.stderr)
            return None

    print(f"  [LLM] Failed after {LLM_MAX_RETRIES} retries. Raw response: {last_raw[:200]}", file=sys.stderr)
    return None


def _build_context_samples(
    headings: list[HeadingCandidate],
    pages: list[PageRecord],
) -> list[str]:
    """Build context samples: first ~200 chars of content after each heading."""
    page_by_seq = {p.seq_index: p for p in pages}
    samples = []
    for h in headings:
        page = page_by_seq.get(h.seq_index)
        if not page:
            samples.append("")
            continue

        text = page.matn_text
        # If inline heading, start after the heading boundary
        if h.heading_text_boundary and h.heading_text_boundary < len(text):
            text = text[h.heading_text_boundary:]
        else:
            # Skip lines that ARE the heading
            lines = text.split("\n")
            content_lines = []
            title_norm = normalize_arabic_for_match(h.title)[:30]
            past_heading = False
            for line in lines:
                if not past_heading and title_norm and title_norm in normalize_arabic_for_match(line):
                    past_heading = True
                    continue
                if past_heading or not title_norm:
                    content_lines.append(line)
            text = "\n".join(content_lines) if content_lines else text

        # Take first 200 chars
        sample = text.strip()[:200].replace("\n", " ")
        samples.append(sample)
    return samples


def _format_candidates_for_prompt(headings: list[HeadingCandidate]) -> str:
    """Format heading candidates as JSON for the LLM prompt."""
    items = []
    for i, h in enumerate(headings):
        items.append({
            "index": i,
            "title": h.title,
            "seq_index": h.seq_index,
            "page_hint": h.page_hint,
            "detection_method": h.detection_method,
            "confidence": h.confidence,
            "keyword_type": h.keyword_type,
        })
    return json.dumps(items, ensure_ascii=False, indent=2)


def _load_prompt_template(prompt_path: str) -> str:
    """Load a prompt template from disk."""
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()


def pass3a_macro_structure(
    client,
    headings: list[HeadingCandidate],
    pages: list[PageRecord],
    toc_entries: list[TOCEntry],
    metadata: dict,
    prompt_dir: str,
) -> Optional[dict]:
    """Pass 3a — Macro Structure Discovery.

    Sends all heading candidates + context to LLM for:
    - Confirm/reject/modify each candidate
    - Hierarchy assignment (levels + parent refs)
    - Digestibility classification
    - Gap detection (new divisions)

    Returns parsed LLM response dict or None on failure.
    """
    # Load prompt template
    template_path = os.path.join(prompt_dir, "pass3a_macro_v0.1.md")
    if not os.path.exists(template_path):
        print(f"  [Pass 3a] ERROR: prompt template not found: {template_path}", file=sys.stderr)
        return None

    template = _load_prompt_template(template_path)

    # Build context samples
    context_samples = _build_context_samples(headings, pages)
    context_text = ""
    for i, (h, sample) in enumerate(zip(headings, context_samples)):
        if sample:
            context_text += f"\n[{i}] {h.title}\n  → {sample}\n"
        else:
            context_text += f"\n[{i}] {h.title}\n  → (no content sample available)\n"

    # Format TOC entries
    toc_json = ""
    if toc_entries:
        toc_items = [{"title": t.title, "page_number": t.page_number, "indent_level": t.indent_level}
                     for t in toc_entries]
        toc_json = json.dumps(toc_items, ensure_ascii=False, indent=2)

    # Fill template
    prompt = template
    prompt = prompt.replace("{{book_title}}", metadata.get("title", "Unknown"))
    prompt = prompt.replace("{{book_author}}", metadata.get("author", "Unknown"))
    prompt = prompt.replace("{{book_science}}", metadata.get("primary_science", "Unknown"))
    prompt = prompt.replace("{{total_pages}}", str(len(pages)))
    prompt = prompt.replace("{{candidate_count}}", str(len(headings)))
    prompt = prompt.replace("{{candidates_json}}", _format_candidates_for_prompt(headings))
    prompt = prompt.replace("{{context_samples}}", context_text)

    # Handle TOC conditional block
    if toc_entries:
        prompt = prompt.replace("{{#if toc_entries}}", "")
        prompt = prompt.replace("{{/if}}", "")
        prompt = prompt.replace("{{toc_entries_json}}", toc_json)
    else:
        # Remove entire TOC block
        prompt = re.sub(r"\{\{#if toc_entries\}\}.*?\{\{/if\}\}", "", prompt, flags=re.DOTALL)

    # Estimate tokens: ~4 chars per token for Arabic
    est_input_tokens = len(prompt) // 4
    print(f"  [Pass 3a] Prompt size: ~{est_input_tokens} tokens ({len(headings)} candidates)")

    # Call LLM
    result = call_llm(client, prompt, max_tokens=8192)
    if not result:
        return None

    # Validate response structure
    if "decisions" not in result:
        print("  [Pass 3a] ERROR: response missing 'decisions' field", file=sys.stderr)
        return None

    decisions = result["decisions"]
    if len(decisions) != len(headings):
        print(f"  [Pass 3a] WARNING: got {len(decisions)} decisions for {len(headings)} candidates")

    # Validate each decision
    valid_actions = {"confirm", "reject", "modify"}
    max_seq = max(p.seq_index for p in pages)
    for d in decisions:
        if d.get("action") not in valid_actions:
            print(f"  [Pass 3a] WARNING: invalid action '{d.get('action')}' for candidate {d.get('candidate_index')}")

    # Validate new divisions
    for nd in result.get("new_divisions", []):
        seq = nd.get("approximate_seq_index", -1)
        if seq < 0 or seq > max_seq:
            print(f"  [Pass 3a] WARNING: new division seq_index {seq} out of range [0, {max_seq}]")

    return result


def pass3b_deep_scan(
    client,
    section_title: str,
    section_type: str,
    start_seq: int,
    end_seq: int,
    known_subheadings: list[HeadingCandidate],
    pages: list[PageRecord],
    metadata: dict,
    prompt_dir: str,
) -> Optional[dict]:
    """Pass 3b — Deep Division Scan for a single macro division.

    Sends the full text of one section to find missed sub-divisions.
    Only called for confirmed macro divisions > 5 pages.

    Returns parsed LLM response dict or None on failure.
    """
    template_path = os.path.join(prompt_dir, "pass3b_deep_v0.1.md")
    if not os.path.exists(template_path):
        print(f"  [Pass 3b] ERROR: prompt template not found: {template_path}", file=sys.stderr)
        return None

    template = _load_prompt_template(template_path)

    page_by_seq = {p.seq_index: p for p in pages}
    page_count = end_seq - start_seq + 1

    # Build full text of the section
    section_lines = []
    for seq in range(start_seq, end_seq + 1):
        page = page_by_seq.get(seq)
        if page:
            section_lines.append(f"[seq={seq}]")
            section_lines.append(page.matn_text)
            section_lines.append("")
    section_text = "\n".join(section_lines)

    # Truncate if too long (aim for ~100K chars ≈ 25K tokens)
    if len(section_text) > 100_000:
        section_text = section_text[:100_000] + "\n\n[... text truncated for length ...]"

    # Format known sub-headings
    sub_items = []
    for i, h in enumerate(known_subheadings):
        sub_items.append({
            "index": i,
            "title": h.title,
            "seq_index": h.seq_index,
            "detection_method": h.detection_method,
        })
    known_json = json.dumps(sub_items, ensure_ascii=False, indent=2)

    # Fill template
    page_range = f"seq [{start_seq}–{end_seq}]"
    prompt = template
    prompt = prompt.replace("{{book_title}}", metadata.get("title", "Unknown"))
    prompt = prompt.replace("{{book_science}}", metadata.get("primary_science", "Unknown"))
    prompt = prompt.replace("{{section_title}}", section_title)
    prompt = prompt.replace("{{section_type}}", section_type)
    prompt = prompt.replace("{{page_range}}", page_range)
    prompt = prompt.replace("{{page_count}}", str(page_count))
    prompt = prompt.replace("{{known_subheadings_count}}", str(len(known_subheadings)))
    prompt = prompt.replace("{{known_subheadings_json}}", known_json)
    prompt = prompt.replace("{{section_text}}", section_text)

    est_input_tokens = len(prompt) // 4
    print(f"    [Pass 3b] '{section_title[:40]}' ({page_count}p, ~{est_input_tokens} tokens)")

    result = call_llm(client, prompt, max_tokens=4096)
    return result


def integrate_pass3_results(
    headings: list[HeadingCandidate],
    pass3a_result: dict,
    pass3b_results: dict[int, dict],  # keyed by candidate_index of the macro division
    pages: list[PageRecord],
) -> list[HeadingCandidate]:
    """Integrate Pass 3 LLM results back into the heading list.

    - Applies confirm/reject/modify decisions from Pass 3a
    - Enriches headings with hierarchy (level, parent_ref)
    - Adds new divisions discovered by Pass 3a and Pass 3b
    - Returns the final enriched heading list (rejected headings removed)

    Each heading gets new attributes stored in _pass3_* fields:
    - _pass3_level: int
    - _pass3_parent_ref: Optional[int] (index into final list)
    - _pass3_digestible: str
    - _pass3_content_type: Optional[str]
    """
    decisions = pass3a_result.get("decisions", [])
    new_divs_3a = pass3a_result.get("new_divisions", [])

    # Build decision lookup
    decision_map: dict[int, dict] = {}
    for d in decisions:
        ci = d.get("candidate_index")
        if ci is not None:
            decision_map[ci] = d

    # Phase 1: Apply decisions to existing headings
    # Tag each heading with its ORIGINAL index so parent_ref can resolve after sorting
    confirmed: list[tuple[HeadingCandidate, dict]] = []
    rejected_count = 0

    for i, h in enumerate(headings):
        h._original_index = i  # stable reference for parent_ref resolution

        dec = decision_map.get(i)
        if not dec:
            # No decision from LLM — keep with defaults
            confirmed.append((h, {"level": 1, "parent_ref": None,
                                  "digestible": "true", "content_type": "teaching"}))
            continue

        action = dec.get("action", "confirm")
        if action == "reject":
            rejected_count += 1
            continue

        if action == "modify":
            # Update title if provided
            new_title = dec.get("new_title")
            if new_title:
                h.title = new_title

        confirmed.append((h, dec))

    print(f"  [Pass 3] {len(confirmed)} confirmed, {rejected_count} rejected")

    # Phase 2: Add new divisions from Pass 3a
    max_seq = max(p.seq_index for p in pages)
    page_by_seq = {p.seq_index: p for p in pages}
    # Track next document_position for new headings
    max_doc_pos = max((h.document_position for h in headings), default=0) + 1

    new_from_3a = []
    for nd in new_divs_3a:
        seq = nd.get("approximate_seq_index", 0)
        seq = max(0, min(seq, max_seq))
        page = page_by_seq.get(seq)
        pn = page.page_number_int if page else seq + 1
        vol = page.volume if page else 1

        new_h = HeadingCandidate(
            title=nd.get("title", ""),
            seq_index=seq,
            page_number_int=pn,
            volume=vol,
            page_hint=page.page_hint if page else f"seq:{seq}",
            detection_method="llm_discovered",
            confidence=nd.get("confidence", "medium"),
            keyword_type=nd.get("type"),
            document_position=max_doc_pos,
            page_mapped=True,
        )
        new_h._original_index = None  # New heading, no original index
        max_doc_pos += 1
        dec_for_new = {
            "level": nd.get("level", 1),
            "parent_ref": nd.get("parent_ref"),
            "digestible": nd.get("digestible", "true"),
            "content_type": nd.get("content_type"),
        }
        new_from_3a.append((new_h, dec_for_new))

    if new_from_3a:
        print(f"  [Pass 3a] Discovered {len(new_from_3a)} new divisions")

    # Phase 3: Add new sub-divisions from Pass 3b
    new_from_3b = []
    # Build lookup for existing heading pages+titles to dedup Pass 3b discoveries
    existing_keys = set()
    for h, _ in confirmed + new_from_3a:
        norm_title = normalize_arabic_for_match(h.title)[:40]
        existing_keys.add((h.seq_index, norm_title))

    for parent_idx, result_3b in pass3b_results.items():
        if not result_3b:
            continue

        # Find parent's level for sub-division level assignment
        parent_dec = decision_map.get(parent_idx, {})
        parent_level = parent_dec.get("level", 1) or 1

        for sd in result_3b.get("new_subdivisions", []):
            seq = sd.get("approximate_seq_index", 0)
            seq = max(0, min(seq, max_seq))

            # Dedup: skip if heading already exists at same page with similar title
            norm_title = normalize_arabic_for_match(sd.get("title", ""))[:40]
            if (seq, norm_title) in existing_keys:
                continue
            existing_keys.add((seq, norm_title))

            page = page_by_seq.get(seq)
            pn = page.page_number_int if page else seq + 1
            vol = page.volume if page else 1

            new_h = HeadingCandidate(
                title=sd.get("title", ""),
                seq_index=seq,
                page_number_int=pn,
                volume=vol,
                page_hint=page.page_hint if page else f"seq:{seq}",
                detection_method="llm_discovered",
                confidence=sd.get("confidence", "medium"),
                keyword_type=sd.get("type"),
                inline_heading=sd.get("inline_heading", False),
                document_position=max_doc_pos,
                page_mapped=True,
            )
            new_h._original_index = None  # No original index for new headings
            max_doc_pos += 1

            # Sub-division's parent is the macro division; level = parent + 1
            sub_level = sd.get("level", parent_level + 1)
            if sub_level <= parent_level:
                sub_level = parent_level + 1

            dec_for_sub = {
                "level": sub_level,
                "parent_ref": parent_idx,
                "digestible": sd.get("digestible", "true"),
                "content_type": sd.get("content_type"),
            }
            new_from_3b.append((new_h, dec_for_sub))

    if new_from_3b:
        print(f"  [Pass 3b] Discovered {len(new_from_3b)} new sub-divisions")

    # Phase 4: Merge all into a single list sorted by (seq_index, document_position)
    all_entries = confirmed + new_from_3a + new_from_3b
    all_entries.sort(key=lambda x: (x[0].seq_index, x[0].document_position))

    # Enrich headings with Pass 3 attributes
    for h, dec in all_entries:
        h._pass3_level = dec.get("level", 1)
        h._pass3_parent_ref = dec.get("parent_ref")
        h._pass3_digestible = dec.get("digestible", "true")
        h._pass3_content_type = dec.get("content_type")

    return [h for h, _ in all_entries]


def build_hierarchical_tree(
    headings: list[HeadingCandidate],
    pages: list[PageRecord],
    book_id: str,
    multi_volume: bool = False,
    keywords: Optional[dict[str, dict]] = None,
    verbose: bool = False,
) -> list[DivisionNode]:
    """Build a hierarchical division tree from Pass 3-enriched headings.

    Unlike build_division_tree (flat), this produces a proper parent-child tree
    using the LLM-assigned levels and parent references.

    Page ranges respect hierarchy: a parent's range contains all children.
    Leaf-level digestible divisions become passages in the next step.
    """
    if not headings:
        return []

    # Filter unmapped headings
    mapped = [h for h in headings if h.page_mapped]
    unmapped_count = len(headings) - len(mapped)
    if unmapped_count > 0:
        print(f"[Tree] WARNING: {unmapped_count} headings dropped (page not in JSONL)")

    if not mapped:
        return []

    # Sort by (seq_index, document_position)
    sorted_headings = sorted(mapped, key=lambda h: (h.seq_index, h.document_position))

    # Deduplicate exact same title on same page
    deduped: list[HeadingCandidate] = []
    seen: set[tuple[int, str]] = set()
    for h in sorted_headings:
        key = (h.seq_index, normalize_arabic_for_match(h.title)[:40])
        if key not in seen:
            seen.add(key)
            deduped.append(h)

    max_seq = max(p.seq_index for p in pages)
    page_by_seq = {p.seq_index: p for p in pages}

    # Phase 1: Create all DivisionNode objects
    divisions: list[DivisionNode] = []
    heading_to_div: dict[int, str] = {}  # heading list index → div_id
    original_idx_to_div: dict[int, str] = {}  # original heading index → div_id

    for i, h in enumerate(deduped):
        div_id = f"div_{i:04d}"
        heading_to_div[i] = div_id
        # Track by original index for parent_ref resolution
        orig_idx = getattr(h, '_original_index', None)
        if orig_idx is not None:
            original_idx_to_div[orig_idx] = div_id

        # Detect keyword type from title
        div_type = "implicit"
        if keywords:
            div_type = detect_keyword_type_from_title(h.title, keywords)
        if h.keyword_type:
            div_type = h.keyword_type

        # Use Pass 3 digestibility if available, else deterministic
        if hasattr(h, '_pass3_digestible') and h._pass3_digestible:
            digestible = h._pass3_digestible
            content_type = getattr(h, '_pass3_content_type', None) or "teaching"
        else:
            digestible, content_type = classify_digestibility(h)

        level = getattr(h, '_pass3_level', 1) or 1

        # Determine editor_inserted
        editor_inserted = False
        if h.title and (h.title.startswith("[") or h.title.startswith("[")):
            editor_inserted = True

        # Placeholder page range — will be refined
        start_seq = h.seq_index

        div = DivisionNode(
            id=div_id,
            type=div_type,
            title=h.title,
            level=level,
            detection_method=h.detection_method,
            confidence=h.confidence,
            digestible=digestible,
            content_type=content_type,
            start_seq_index=start_seq,
            end_seq_index=start_seq,  # placeholder
            page_hint_start=h.page_hint,
            page_hint_end=h.page_hint,  # placeholder
            parent_id=None,  # set in phase 2
            page_count=1,
            editor_inserted=editor_inserted,
            inline_heading=h.inline_heading,
            heading_text_boundary=h.heading_text_boundary,
            heading_in_html=(h.detection_method == "html_tagged"),
        )
        divisions.append(div)

    # Phase 2: Assign parent-child relationships from Pass 3 references
    if verbose:
        print(f"  [Tree] original_idx_to_div has {len(original_idx_to_div)} entries")
        for oidx in sorted(original_idx_to_div.keys())[:10]:
            div_id = original_idx_to_div[oidx]
            div_obj = next((d for d in divisions if d.id == div_id), None)
            title_preview = div_obj.title[:40] if div_obj else "?"
            print(f"    orig[{oidx}] → {div_id} '{title_preview}'")

    fallback_count = 0
    for i, h in enumerate(deduped):
        parent_ref = getattr(h, '_pass3_parent_ref', None)
        if parent_ref is None:
            continue

        # parent_ref is the original candidate index (pre-sort, pre-dedup).
        # Use original_idx_to_div to resolve to a div_id.
        if isinstance(parent_ref, int) and parent_ref in original_idx_to_div:
            divisions[i].parent_id = original_idx_to_div[parent_ref]
        elif isinstance(parent_ref, int) and parent_ref in heading_to_div:
            # Fallback: try deduped index (for headings without _original_index)
            fallback_count += 1
            if verbose:
                target_div = heading_to_div.get(parent_ref, "?")
                print(f"  [Tree] FALLBACK parent_ref={parent_ref} for {divisions[i].id} "
                      f"'{divisions[i].title[:30]}' → {target_div}")
            divisions[i].parent_id = heading_to_div[parent_ref]
        elif isinstance(parent_ref, str) and parent_ref.startswith("new_"):
            # Reference to a new_division by position — resolve by scan
            pass  # Complex cross-referencing; logged and handled below

    if fallback_count > 0 and verbose:
        print(f"  [Tree] WARNING: {fallback_count} parent refs resolved via fallback (heading_to_div)")

    # Build child_ids from parent_ids
    for div in divisions:
        div.child_ids = []
    for div in divisions:
        if div.parent_id:
            parent = next((d for d in divisions if d.id == div.parent_id), None)
            if parent:
                parent.child_ids.append(div.id)

    # Phase 3: Tree-aware range computation.
    # Uses iterative top-down approach: compute root ranges, then children
    # within parent bounds. Detach children that fall outside parent range,
    # then repeat until stable (no more detachments).

    div_by_id = {d.id: d for d in divisions}
    total_detached = 0

    def _compute_sibling_ranges(sibling_ids: list[str], group_end: int):
        """Assign sequential ranges to a group of siblings.

        Each sibling's range runs from its start to just before the next
        sibling's start, with the last sibling extending to group_end.
        """
        siblings = [div_by_id[sid] for sid in sibling_ids if sid in div_by_id]
        siblings.sort(key=lambda d: (d.start_seq_index, divisions.index(d)))

        for idx, sib in enumerate(siblings):
            if idx + 1 < len(siblings):
                next_start = siblings[idx + 1].start_seq_index
                sib.end_seq_index = max(sib.start_seq_index, next_start - 1)
            else:
                sib.end_seq_index = group_end
            # Clamp to group boundary
            sib.end_seq_index = min(sib.end_seq_index, group_end)
            # Hard invariant: end >= start
            sib.end_seq_index = max(sib.end_seq_index, sib.start_seq_index)

    def _full_range_pass() -> int:
        """One full top-down pass: roots → children by level. Returns detach count."""
        detached_this_pass = 0

        # Compute root ranges
        root_ids = [d.id for d in divisions if d.parent_id is None]
        _compute_sibling_ranges(root_ids, max_seq)

        # Process children level by level (top-down)
        max_depth = max((d.level for d in divisions), default=1)
        for level in range(1, max_depth + 1):
            parents_at_level = [d for d in divisions
                                if d.level == level and d.child_ids]
            for parent in parents_at_level:
                valid_children = []
                for cid in list(parent.child_ids):
                    child = div_by_id.get(cid)
                    if not child:
                        parent.child_ids.remove(cid)
                        continue
                    # Check containment: child must start within parent range
                    if child.start_seq_index < parent.start_seq_index or \
                       child.start_seq_index > parent.end_seq_index:
                        if verbose:
                            print(f"  [Tree] Detaching {child.id} from {parent.id}: "
                                  f"child starts at {child.start_seq_index}, "
                                  f"parent range [{parent.start_seq_index}-"
                                  f"{parent.end_seq_index}]")
                        parent.child_ids.remove(cid)
                        child.parent_id = None
                        # Also detach grandchildren (they become orphans)
                        # They'll be re-parented as roots in the next iteration
                        detached_this_pass += 1
                    else:
                        valid_children.append(cid)

                # Compute ranges for valid children within parent bounds
                if valid_children:
                    _compute_sibling_ranges(valid_children, parent.end_seq_index)

        return detached_this_pass

    # Iterate until stable (max 5 iterations to prevent infinite loops)
    for iteration in range(5):
        detached = _full_range_pass()
        total_detached += detached
        if detached == 0:
            break
        if verbose:
            print(f"  [Tree] Iteration {iteration + 1}: detached {detached} — "
                  f"recomputing ranges")

    if total_detached > 0 and verbose:
        print(f"  [Tree] Total detached: {total_detached} divisions")

    # Final safety: enforce end >= start for ALL divisions
    for div in divisions:
        if div.end_seq_index < div.start_seq_index:
            div.end_seq_index = div.start_seq_index

    # Phase 4: Set page counts and hints
    for div in divisions:
        div.page_count = div.end_seq_index - div.start_seq_index + 1
        end_page = page_by_seq.get(div.end_seq_index)
        if end_page:
            if multi_volume:
                div.page_hint_end = f"ج{end_page.volume}:ص:{int_to_indic(end_page.page_number_int)}"
            else:
                div.page_hint_end = f"ص:{int_to_indic(end_page.page_number_int)}"

    # Phase 5: Add review flags
    for div in divisions:
        flags = []
        if div.digestible == "uncertain":
            flags.append("needs_human_review")
        if div.confidence == "low":
            flags.append("low_confidence")
        if div.page_count > 30:
            flags.append("long_passage")
        div.review_flags = flags

    return divisions


# ---------------------------------------------------------------------------
# TOC Cross-Reference (Spec §7.5, §5.3)
# ---------------------------------------------------------------------------

def cross_reference_toc(
    divisions: list[DivisionNode],
    toc_entries: list[TOCEntry],
    pages: list[PageRecord],
) -> dict:
    """Cross-reference discovered divisions against TOC entries.

    Returns a dict with:
    - matched: list of (toc_index, div_id, score) for matched pairs
    - missed_headings: TOC entries with no matching division (potential gaps)
    - false_positives: divisions not in TOC (potential false detections)
    - toc_mismatch_count: number of mismatches for the report
    """
    if not toc_entries:
        return {"matched": [], "missed_headings": [], "false_positives": [], "toc_mismatch_count": 0}

    page_by_seq = {p.seq_index: p for p in pages}

    # Build division lookup by page_number_int
    div_by_page: dict[int, list[DivisionNode]] = {}
    for d in divisions:
        page = page_by_seq.get(d.start_seq_index)
        if page:
            div_by_page.setdefault(page.page_number_int, []).append(d)

    matched: list[tuple[int, str, float]] = []
    missed: list[dict] = []
    matched_div_ids: set[str] = set()

    for ti, toc in enumerate(toc_entries):
        best_score = 0.0
        best_div = None

        # Search on same page and adjacent pages (±1 for boundary issues)
        for offset in [0, -1, 1]:
            target_page = toc.page_number + offset
            for d in div_by_page.get(target_page, []):
                score = _toc_match_score(toc.title, d.title)
                if score > best_score:
                    best_score = score
                    best_div = d

        if best_score >= 0.4 and best_div:
            matched.append((ti, best_div.id, best_score))
            matched_div_ids.add(best_div.id)
        else:
            missed.append({
                "toc_index": ti,
                "title": toc.title,
                "page_number": toc.page_number,
                "indent_level": toc.indent_level,
                "nearest_div": best_div.id if best_div else None,
                "nearest_score": round(best_score, 2),
            })

    # Divisions not in TOC (excluding non-digestible and LLM-discovered)
    false_positives = []
    for d in divisions:
        if d.id not in matched_div_ids and d.digestible != "false" and d.detection_method != "llm_discovered":
            false_positives.append({
                "div_id": d.id,
                "title": d.title,
                "detection_method": d.detection_method,
            })

    return {
        "matched": matched,
        "missed_headings": missed,
        "false_positives": false_positives,
        "toc_mismatch_count": len(missed),
    }


def _toc_match_score(toc_title: str, div_title: str) -> float:
    """Compute fuzzy match score between a TOC entry title and a division title."""
    t = normalize_arabic_for_match(toc_title.strip())
    d = normalize_arabic_for_match(div_title.strip())

    if not t or not d:
        return 0.0

    # Exact match
    if t == d:
        return 1.0

    # Prefix match (TOC titles are often truncated)
    min_len = min(len(t), len(d))
    if min_len < 4:
        return 0.0

    prefix_len = 0
    for i in range(min_len):
        if t[i] == d[i]:
            prefix_len += 1
        else:
            break

    max_len = max(len(t), len(d))
    if prefix_len >= 12 or (prefix_len / max_len > 0.5 and prefix_len >= 5):
        return prefix_len / max_len

    # Containment
    if len(t) > 5 and t in d:
        return 0.8
    if len(d) > 5 and d in t:
        return 0.8

    return 0.0


# ---------------------------------------------------------------------------
# Ordinal Sequence Validation (Spec §7.5.3)
# ---------------------------------------------------------------------------

def validate_ordinal_sequences(
    divisions: list[DivisionNode],
) -> list[dict]:
    """Validate that sibling divisions with the same keyword have sequential ordinals.

    Returns list of warnings for ordinal gaps or misordering.
    """
    warnings = []

    # Group siblings by parent_id and type
    from collections import defaultdict
    sibling_groups: dict[tuple[Optional[str], str], list[DivisionNode]] = defaultdict(list)

    for d in divisions:
        if d.ordinal is not None:
            key = (d.parent_id, d.type)
            sibling_groups[key].append(d)

    for (parent_id, div_type), siblings in sibling_groups.items():
        if len(siblings) < 2:
            continue

        # Sort by document order (start_seq_index)
        sorted_sibs = sorted(siblings, key=lambda d: d.start_seq_index)
        ordinals = [d.ordinal for d in sorted_sibs]

        for i in range(len(ordinals) - 1):
            expected = ordinals[i] + 1
            actual = ordinals[i + 1]
            if actual != expected:
                warnings.append({
                    "type": "ordinal_gap" if actual > expected else "ordinal_misordering",
                    "parent_id": parent_id,
                    "keyword": div_type,
                    "expected_ordinal": expected,
                    "actual_ordinal": actual,
                    "div_id": sorted_sibs[i + 1].id,
                    "title": sorted_sibs[i + 1].title,
                    "previous_div_id": sorted_sibs[i].id,
                })

    return warnings


# ---------------------------------------------------------------------------
# Human Override System (Spec §10.5)
# ---------------------------------------------------------------------------

def apply_overrides(
    divisions: list[DivisionNode],
    passages: list[PassageRecord],
    overrides_path: str,
    pages: list[PageRecord],
) -> tuple[list[DivisionNode], bool]:
    """Apply human review overrides to divisions.

    Override actions:
    - reject: remove a division (and its descendants)
    - confirm: mark an uncertain division as confirmed
    - modify: change a division's properties
    - split: split a passage at a given seq_index (creates new division boundary)
    - merge: merge a passage with its successor

    Returns (modified_divisions, any_changes_applied).
    Passages must be rebuilt after overrides are applied.
    """
    with open(overrides_path, encoding="utf-8") as f:
        data = json.load(f)

    override_list = data.get("overrides", [])
    if not override_list:
        return divisions, False

    div_by_id = {d.id: d for d in divisions}
    changes = 0

    for ov in override_list:
        item_type = ov.get("item_type")
        item_id = ov.get("item_id")
        action = ov.get("action")

        if item_type == "division":
            div = div_by_id.get(item_id)
            if not div:
                print(f"  [Override] WARNING: division '{item_id}' not found, skipping")
                continue

            if action == "rejected":
                div.digestible = "false"
                div.content_type = "non_content"
                div.review_flags.append("human_rejected")
                div.human_override = ov.get("notes", "rejected by human")
                changes += 1

            elif action == "confirmed":
                if div.digestible == "uncertain":
                    div.digestible = "true"
                div.confidence = "confirmed"
                div.human_override = ov.get("notes", "confirmed by human")
                changes += 1

            elif action == "modify":
                if "new_title" in ov:
                    div.title = ov["new_title"]
                if "new_type" in ov:
                    div.type = ov["new_type"]
                if "digestible" in ov:
                    div.digestible = ov["digestible"]
                if "content_type" in ov:
                    div.content_type = ov["content_type"]
                div.human_override = ov.get("notes", "modified by human")
                changes += 1

        elif item_type == "passage":
            if action == "split":
                split_seq = ov.get("split_at_seq_index")
                if split_seq is not None:
                    # Find the passage and the division it belongs to
                    target_passage = next(
                        (p for p in passages if p.passage_id == item_id), None
                    )
                    if target_passage:
                        # Find the owning division
                        owner_div = div_by_id.get(target_passage.division_ids[0])
                        if owner_div and owner_div.start_seq_index < split_seq <= owner_div.end_seq_index:
                            # Create a new division at the split point
                            page_by_seq = {p.seq_index: p for p in pages}
                            split_page = page_by_seq.get(split_seq)
                            new_id = f"{owner_div.id}_split"
                            new_div = DivisionNode(
                                id=new_id,
                                type=owner_div.type,
                                title=ov.get("new_title", f"{owner_div.title} (cont.)"),
                                level=owner_div.level,
                                detection_method="human_override",
                                confidence="confirmed",
                                digestible=owner_div.digestible,
                                content_type=owner_div.content_type,
                                start_seq_index=split_seq,
                                end_seq_index=owner_div.end_seq_index,
                                page_hint_start=split_page.page_hint if split_page else f"seq:{split_seq}",
                                page_hint_end=owner_div.page_hint_end,
                                parent_id=owner_div.parent_id,
                                page_count=owner_div.end_seq_index - split_seq + 1,
                                human_override=ov.get("notes", "split by human"),
                            )
                            # Truncate the original division
                            owner_div.end_seq_index = split_seq - 1
                            owner_div.page_count = owner_div.end_seq_index - owner_div.start_seq_index + 1
                            if split_seq - 1 in page_by_seq:
                                p = page_by_seq[split_seq - 1]
                                owner_div.page_hint_end = p.page_hint

                            divisions.append(new_div)
                            div_by_id[new_id] = new_div
                            changes += 1

    if changes:
        print(f"  [Override] Applied {changes} override(s)")
        # Re-sort divisions by start_seq_index
        divisions.sort(key=lambda d: (d.start_seq_index, d.level))

    return divisions, changes > 0

# Deterministic digestibility rules (STRUCTURE_SPEC v1.0 §8)
NON_DIGESTIBLE_TYPES = {"فهرس", "المحتويات", "فهرس الموضوعات", "تقاريظ"}
NON_DIGESTIBLE_TITLE_PATTERNS = [
    "مقدمة المحقق", "مقدمة المعلق", "كلمة المحقق",
    "خطبة الكتاب", "فهرس",
]
EXERCISE_TYPES = {"تمارين", "تطبيق", "مسائل التمرين", "أسئلة"}
UNCERTAIN_TITLES = {"مقدمة", "مقدمة الكتاب", "المقدمة"}


def classify_digestibility(heading: HeadingCandidate) -> tuple[str, Optional[str]]:
    """Apply deterministic digestibility rules.

    Returns (digestible, content_type) where digestible is "true"/"false"/"uncertain".

    Note: For Pass 1 headings, keyword_type may be None (resolved later by
    detect_keyword_type_from_title). We check BOTH keyword_type and title text
    to ensure correct classification regardless of call order.
    """
    kw = heading.keyword_type or ""
    title_clean = heading.title.strip()

    # Extract the first word of the title for title-based exercise/type detection
    title_first_word = title_clean.split()[0] if title_clean else ""

    # Non-digestible types (check both keyword and title)
    if kw in NON_DIGESTIBLE_TYPES or title_clean in NON_DIGESTIBLE_TYPES:
        return "false", "non_content"

    # Non-digestible title patterns (substring match)
    for pat in NON_DIGESTIBLE_TITLE_PATTERNS:
        if pat in title_clean:
            return "false", "non_content"

    # Exercise types (check keyword AND title first word)
    if kw in EXERCISE_TYPES or title_first_word in EXERCISE_TYPES or title_clean in EXERCISE_TYPES:
        return "true", "exercise"

    # Uncertain (author's مقدمة)
    if title_clean in UNCERTAIN_TITLES:
        return "uncertain", None

    # Default: LLM should classify in Pass 3; for deterministic-only mode, default true
    return "true", "teaching"


def detect_keyword_type_from_title(title: str, keywords: dict[str, dict]) -> str:
    """Detect the structural keyword type from a heading's title text.

    Used for Pass 1 headings which don't have keyword_type set.
    Returns the matched keyword or 'implicit'.
    """
    title_stripped = title.strip()
    # Sort keywords by length descending for priority
    for kw in sorted(keywords.keys(), key=len, reverse=True):
        if title_stripped.startswith(kw):
            # Check word boundary
            after = title_stripped[len(kw):]
            if not after or after[0] in " :؛\t-–—":
                return kw
    return "implicit"


def build_division_tree(
    headings: list[HeadingCandidate],
    pages: list[PageRecord],
    book_id: str,
    multi_volume: bool = False,
    keywords: Optional[dict[str, dict]] = None,
) -> list[DivisionNode]:
    """Build a flat list of DivisionNode from heading candidates.

    This is the deterministic tree builder (no LLM). It assigns:
    - Page ranges (start/end seq_index) based on heading positions
    - Digestibility from deterministic rules
    - A FLAT hierarchy (level=1 for all) — Pass 3 refines hierarchy

    Same-page headings: when multiple headings share a seq_index, they are
    flagged as "same_page_cluster". Only the first heading in each page
    gets a full page range; subsequent same-page headings get end_seq = start_seq
    to prevent overlapping passages.

    For --skip-llm mode, this produces a usable (if flat) tree.
    """
    if not headings:
        return []

    # CRITICAL: Filter out unmapped headings (page_mapped=False)
    mapped = [h for h in headings if h.page_mapped]
    unmapped_count = len(headings) - len(mapped)
    if unmapped_count > 0:
        print(f"[Tree] WARNING: {unmapped_count} headings dropped (page not in JSONL)")

    if not mapped:
        return []

    # Sort by (seq_index, document_position) — preserves document order
    sorted_headings = sorted(mapped, key=lambda h: (h.seq_index, h.document_position))

    # Deduplicate exact same title on same page
    deduped: list[HeadingCandidate] = []
    seen: set[tuple[int, str]] = set()
    for h in sorted_headings:
        key = (h.seq_index, normalize_arabic_for_match(h.title)[:40])
        if key not in seen:
            seen.add(key)
            deduped.append(h)

    max_seq = max(p.seq_index for p in pages) if pages else 0

    # Build page lookup for hints
    page_by_seq: dict[int, PageRecord] = {p.seq_index: p for p in pages}

    # Identify same-page clusters: group consecutive headings by seq_index
    # Within each cluster, the first heading "owns" the page range up to
    # the next cluster; subsequent headings share start_seq == end_seq
    # (zero-width) until Pass 3 resolves hierarchy.
    divisions: list[DivisionNode] = []

    for i, h in enumerate(deduped):
        div_id = f"div_{i:04d}"

        # Determine start_seq
        start_seq = h.seq_index

        # Find the seq_index of the next heading that is on a DIFFERENT page
        # (or the next heading overall if it's on a different page)
        next_different_page_seq = None
        for j in range(i + 1, len(deduped)):
            if deduped[j].seq_index > h.seq_index:
                next_different_page_seq = deduped[j].seq_index
                break

        # Is this heading first on its page?
        is_first_on_page = (i == 0 or deduped[i - 1].seq_index < h.seq_index)
        # Is there a next heading on the same page?
        has_next_on_same_page = (i + 1 < len(deduped) and deduped[i + 1].seq_index == h.seq_index)

        if is_first_on_page:
            # First heading on this page: gets the full range up to next different page
            if next_different_page_seq is not None:
                end_seq = next_different_page_seq - 1
                if end_seq < start_seq:
                    end_seq = start_seq
            else:
                end_seq = max_seq
        else:
            # Not first on page — zero-width until LLM resolves
            end_seq = start_seq

        page_count = end_seq - start_seq + 1

        # Page hints
        start_page = page_by_seq.get(start_seq)
        end_page = page_by_seq.get(end_seq)
        hint_start = make_page_hint(
            h.volume, start_page.page_number_int if start_page else h.page_number_int, multi_volume
        )
        hint_end = make_page_hint(
            h.volume,
            end_page.page_number_int if end_page else h.page_number_int,
            multi_volume,
        )

        # Digestibility
        digestible, content_type = classify_digestibility(h)

        # Review flags
        flags: list[str] = []
        if h.confidence == "low":
            flags.append("low_confidence")
        if digestible == "uncertain":
            flags.append("uncertain_digestibility")
        if page_count > 20:
            flags.append("long_division")
        if not is_first_on_page:
            flags.append("same_page_cluster")

        # Detect editor-inserted headings (bracket patterns)
        editor = bool(re.match(r"^\[.*\]$", h.title.strip()))

        # Determine division type
        div_type = h.keyword_type or "implicit"
        if div_type == "implicit" and keywords:
            div_type = detect_keyword_type_from_title(h.title, keywords)

        divisions.append(DivisionNode(
            id=div_id,
            type=div_type,
            title=h.title,
            level=1,  # Flat until Pass 3 refines
            detection_method=h.detection_method,
            confidence=h.confidence,
            digestible=digestible,
            content_type=content_type,
            start_seq_index=start_seq,
            end_seq_index=end_seq,
            page_hint_start=hint_start,
            page_hint_end=hint_end,
            parent_id=None,  # Flat until Pass 3
            child_ids=[],
            page_count=page_count,
            ordinal=h.ordinal,
            editor_inserted=editor,
            heading_in_html=(h.detection_method == "html_tagged"),
            inline_heading=h.inline_heading,
            heading_text_boundary=h.heading_text_boundary,
            review_flags=flags,
            detection_notes=h.notes,
        ))

    return divisions


# ---------------------------------------------------------------------------
# Passage Constructor
# ---------------------------------------------------------------------------

def build_passages(
    divisions: list[DivisionNode],
    book_id: str,
    science_id: Optional[str] = None,
    pages: Optional[list[PageRecord]] = None,
) -> list[PassageRecord]:
    """Construct passages from leaf-level digestible divisions.

    In the flat tree (pre-LLM), every division is a leaf. In the hierarchical tree
    (post-LLM), only divisions with no children are leaves.

    Same-page cluster divisions (flagged "same_page_cluster") are absorbed into
    the first heading's passage on that page — they don't become separate passages.
    """
    # Build page lookup for volume derivation
    page_by_seq: dict[int, PageRecord] = {}
    if pages:
        page_by_seq = {p.seq_index: p for p in pages}

    # Identify leaf divisions (no children)
    all_ids = {d.id for d in divisions}
    parent_ids = {d.parent_id for d in divisions if d.parent_id}
    leaf_divisions = [d for d in divisions if d.id not in parent_ids]

    # Create preamble pseudo-divisions for parent content before first child.
    # When a parent division (e.g., باب الأول at pages 0-14) has children
    # (e.g., فصل الأول at pages 2-9), pages 0-1 are the parent's preamble.
    # Without a preamble division, these pages have no passage.
    preamble_divs: list[DivisionNode] = []
    parent_divs = [d for d in divisions if d.id in parent_ids]
    div_by_id = {d.id: d for d in divisions}

    for parent in parent_divs:
        if parent.digestible == "false":
            continue
        children = [div_by_id[cid] for cid in parent.child_ids if cid in div_by_id]
        if not children:
            continue
        first_child_start = min(c.start_seq_index for c in children)
        if parent.start_seq_index < first_child_start:
            # There's a preamble gap
            preamble = DivisionNode(
                id=f"{parent.id}_preamble",
                type="preamble",
                title=f"{parent.title} — مقدمة",
                level=parent.level + 1,
                detection_method=parent.detection_method,
                confidence=parent.confidence,
                digestible=parent.digestible,
                content_type=parent.content_type,
                start_seq_index=parent.start_seq_index,
                end_seq_index=first_child_start - 1,
                page_hint_start=parent.page_hint_start,
                page_hint_end=parent.page_hint_start,  # approximate
                parent_id=parent.id,
                page_count=first_child_start - parent.start_seq_index,
            )
            preamble_divs.append(preamble)

    # Add preambles to leaf set
    leaf_divisions = leaf_divisions + preamble_divs

    # Filter to digestible leaves, EXCLUDING same-page cluster followers
    # Same-page cluster divisions get absorbed into the first heading's passage
    digestible_leaves = [
        d for d in leaf_divisions
        if d.digestible != "false" and "same_page_cluster" not in d.review_flags
    ]

    # Build a map: for each page-owning division, collect its same-page cluster siblings
    cluster_siblings: dict[int, list[DivisionNode]] = {}  # start_seq -> list of cluster divs
    for d in leaf_divisions:
        if "same_page_cluster" in d.review_flags and d.digestible != "false":
            cluster_siblings.setdefault(d.start_seq_index, []).append(d)

    # Sort by document order
    digestible_leaves.sort(key=lambda d: d.start_seq_index)

    passages: list[PassageRecord] = []
    passage_num = 1

    # Build ancestor path lookup
    div_by_id = {d.id: d for d in divisions}

    def get_heading_path(div: DivisionNode) -> list[str]:
        path = []
        current = div
        while current:
            path.append(current.title)
            current = div_by_id.get(current.parent_id) if current.parent_id else None
        path.reverse()
        return path

    i = 0
    while i < len(digestible_leaves):
        div = digestible_leaves[i]
        flags: list[str] = []
        sizing_action = "none"
        sizing_notes = None
        merge_info = None
        split_info = None
        merged_ids = [div.id]

        # Absorb same-page cluster siblings into this passage's division_ids
        cluster = cluster_siblings.get(div.start_seq_index, [])
        if cluster:
            for cd in cluster:
                merged_ids.append(cd.id)
            flags.append("has_same_page_subheadings")

        page_count = div.page_count

        # Sizing: merge short divisions (sub-page size)
        # In the flat tree (pre-LLM), page_count is always >= 1 (end_seq >= start_seq),
        # so this condition never triggers. This is correct: the flat tree doesn't have
        # sub-page divisions. Post-LLM, when the hierarchy is resolved, sub-page
        # divisions become possible (e.g., a تنبيه that occupies 3 lines within a page),
        # and this merge logic will activate. If page_count == 1, the division covers
        # exactly one page — that's a legitimate standalone passage, not a merge candidate.
        if page_count < 1 and i + 1 < len(digestible_leaves):
            # Try merging with next sibling(s) under same parent
            combined = page_count
            merge_candidates = [div]
            j = i + 1
            while j < len(digestible_leaves):
                next_div = digestible_leaves[j]
                # Never merge across different top-level parents
                if div.parent_id != next_div.parent_id and div.parent_id is not None:
                    break
                # Never merge exercise with teaching
                if div.content_type == "exercise" and next_div.content_type == "teaching":
                    break
                if div.content_type == "teaching" and next_div.content_type == "exercise":
                    break
                combined += next_div.page_count
                if combined > 15:
                    break
                merge_candidates.append(next_div)
                merged_ids.append(next_div.id)
                j += 1

            if len(merge_candidates) > 1:
                sizing_action = "merged"
                sizing_notes = f"Merged {len(merge_candidates)} short divisions ({combined} pages combined)"
                merge_info = {
                    "merged_division_ids": [d.id for d in merge_candidates],
                    "merge_reason": f"adjacent siblings under 1 page each, combined {combined} pages",
                }
                # Adjust range to cover all merged divisions
                div = merge_candidates[0]  # Use first as primary
                page_count = merge_candidates[-1].end_seq_index - merge_candidates[0].start_seq_index + 1
                i = j  # Skip merged divisions
            else:
                flags.append("short_passage")
                i += 1
        elif page_count > 30:
            flags.append("long_passage")
            sizing_action = "flagged_long"
            sizing_notes = f"Division spans {page_count} pages — consider splitting"
            i += 1
        elif page_count > 20:
            flags.append("long_passage")
            sizing_action = "flagged_long"
            sizing_notes = f"Division spans {page_count} pages — review recommended"
            i += 1
        else:
            i += 1

        # Low confidence boundary flag
        if div.confidence == "low":
            flags.append("low_confidence_boundary")
        if div.digestible == "uncertain":
            flags.append("uncertain_content_type")

        # Determine content type
        if merge_info and len(merged_ids) > 1:
            types = {div_by_id[did].content_type for did in merged_ids if did in div_by_id}
            if "exercise" in types and "teaching" in types:
                content_type = "mixed"
            elif "exercise" in types:
                content_type = "exercise"
            else:
                content_type = "teaching"
        else:
            content_type = div.content_type or "teaching"

        passage_id = f"P{passage_num:03d}"

        # Get the actual end for merged passages
        if merge_info:
            end_seq = max(div_by_id[did].end_seq_index for did in merged_ids if did in div_by_id)
            end_div = max((div_by_id[did] for did in merged_ids if did in div_by_id),
                          key=lambda d: d.end_seq_index)
            hint_end = end_div.page_hint_end
        else:
            end_seq = div.end_seq_index
            hint_end = div.page_hint_end

        actual_page_count = end_seq - div.start_seq_index + 1

        # Derive volume from first page in range
        volume = None
        if page_by_seq:
            start_page = page_by_seq.get(div.start_seq_index)
            if start_page:
                volume = start_page.volume

        passages.append(PassageRecord(
            passage_id=passage_id,
            book_id=book_id,
            division_ids=merged_ids,
            title=div.title,
            heading_path=get_heading_path(div),
            start_seq_index=div.start_seq_index,
            end_seq_index=end_seq,
            page_hint_start=div.page_hint_start,
            page_hint_end=hint_end,
            page_count=actual_page_count,
            volume=volume,
            digestible=True,
            content_type=content_type,
            sizing_action=sizing_action,
            sizing_notes=sizing_notes,
            split_info=split_info,
            merge_info=merge_info,
            review_flags=flags,
            science_id=science_id,
            predecessor_passage_id=None,
            successor_passage_id=None,
        ))
        passage_num += 1

    # Link predecessor/successor
    for idx, p in enumerate(passages):
        if idx > 0:
            p.predecessor_passage_id = passages[idx - 1].passage_id
        if idx < len(passages) - 1:
            p.successor_passage_id = passages[idx + 1].passage_id

    return passages


# ---------------------------------------------------------------------------
# Full Output Generation
# ---------------------------------------------------------------------------

def compute_structure_confidence(divisions: list[DivisionNode]) -> str:
    """Compute overall structure confidence based on detection methods."""
    if not divisions:
        return "minimal"
    html_count = sum(1 for d in divisions if d.detection_method == "html_tagged")
    total = len(divisions)
    ratio = html_count / total
    if ratio > 0.7:
        return "high"
    elif ratio > 0.3:
        return "medium"
    elif total > 0:
        return "low"
    return "minimal"


def generate_structure_report(
    book_id: str,
    divisions: list[DivisionNode],
    passages: list[PassageRecord],
    pass1_count: int,
    pass2_count: int,
    toc_count: int,
    total_pages: int,
    pass3_stats: Optional[dict] = None,
    toc_xref: Optional[dict] = None,
    ordinal_warnings: Optional[list] = None,
) -> dict:
    """Generate the structure_report.json content."""
    from collections import Counter
    import statistics

    by_method = Counter(d.detection_method for d in divisions)
    by_confidence = Counter(d.confidence for d in divisions)
    by_type = Counter(d.type for d in divisions)
    dig_count = sum(1 for d in divisions if d.digestible == "true")
    nondig_count = sum(1 for d in divisions if d.digestible == "false")
    uncert_count = sum(1 for d in divisions if d.digestible == "uncertain")

    page_counts = [p.page_count for p in passages] if passages else [0]

    flagged_items = []
    for d in divisions:
        if d.review_flags:
            flagged_items.append({
                "item_type": "division",
                "item_id": d.id,
                "flags": d.review_flags,
                "description": f"{d.type}: {d.title[:60]}",
            })
    for p in passages:
        if p.review_flags:
            flagged_items.append({
                "item_type": "passage",
                "item_id": p.passage_id,
                "flags": p.review_flags,
                "description": f"{p.title[:60]} ({p.page_count} pages)",
            })

    p3 = pass3_stats or {}

    return {
        "schema_version": "structure_report_v0.1",
        "book_id": book_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "pass_stats": {
            "pass1_html_tagged": pass1_count,
            "pass1_5_toc_entries": toc_count,
            "pass2_keyword_candidates": pass2_count,
            "pass2_after_dedup": pass2_count,
            "pass3_llm_discovered": p3.get("new_discovered", 0),
            "pass3_confirmed": p3.get("confirmed", 0),
            "pass3_rejected": p3.get("rejected", 0),
            "pass3_llm_calls": p3.get("llm_calls", 0),
        },
        "division_stats": {
            "total_divisions": len(divisions),
            "max_depth": max((d.level for d in divisions), default=0),
            "by_detection_method": dict(by_method),
            "by_confidence": dict(by_confidence),
            "by_type": dict(by_type),
            "digestible_count": dig_count,
            "non_digestible_count": nondig_count,
            "uncertain_digestible_count": uncert_count,
            "heading_density": round(len(divisions) / total_pages, 3) if total_pages > 0 else 0,
        },
        "passage_stats": {
            "total_passages": len(passages),
            "total_pages_covered": sum(p.page_count for p in passages),
            "total_pages_skipped": total_pages - sum(p.page_count for p in passages),
            "by_content_type": dict(Counter(p.content_type for p in passages)),
            "by_sizing_action": dict(Counter(p.sizing_action for p in passages)),
            "page_count_min": min(page_counts),
            "page_count_max": max(page_counts),
            "page_count_median": round(statistics.median(page_counts), 1),
            "page_count_mean": round(statistics.mean(page_counts), 1),
        },
        "review_summary": {
            "total_flags": len(flagged_items),
            "low_confidence_divisions": sum(1 for d in divisions if "low_confidence" in d.review_flags),
            "uncertain_digestibility": uncert_count,
            "long_passages": sum(1 for p in passages if "long_passage" in p.review_flags),
            "toc_matched": len(toc_xref.get("matched", [])) if toc_xref else 0,
            "toc_missed_headings": len(toc_xref.get("missed_headings", [])) if toc_xref else 0,
            "toc_false_positives": len(toc_xref.get("false_positives", [])) if toc_xref else 0,
            "ordinal_warnings": len(ordinal_warnings or []),
            "flagged_items": flagged_items,
        },
    }


def generate_full_review_md(
    book_id: str,
    divisions: list[DivisionNode],
    passages: list[PassageRecord],
    toc_entries: list[TOCEntry],
    pages: list[PageRecord],
    toc_xref: Optional[dict] = None,
    ordinal_warnings: Optional[list] = None,
) -> str:
    """Generate a full human-readable structure review Markdown."""
    lines = [
        f"# Structure Review — {book_id}",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Total pages: {len(pages)}",
        f"Total divisions: {len(divisions)}",
        f"Total passages: {len(passages)}",
        "",
        "## Division Tree",
        "",
    ]

    # Build actual depth from parent-child relationships (not LLM-assigned level)
    div_by_id = {d.id: d for d in divisions}
    actual_depth: dict[str, int] = {}
    for d in divisions:
        depth = 0
        pid = d.parent_id
        while pid and pid in div_by_id and depth < 10:
            depth += 1
            pid = div_by_id[pid].parent_id
        actual_depth[d.id] = depth

    for d in sorted(divisions, key=lambda x: x.start_seq_index):
        indent = "  " * actual_depth.get(d.id, 0)
        tier = {"html_tagged": "T1", "keyword_heuristic": "T2", "llm_discovered": "T3",
                "toc_inferred": "TOC", "human_override": "HO"}.get(d.detection_method, "??")
        conf = d.confidence[:3]
        dig = {"true": "✓", "false": "✗", "uncertain": "?"}.get(d.digestible, "?")
        flags_str = f" ⚠ {', '.join(d.review_flags)}" if d.review_flags else ""
        lines.append(
            f"{indent}- [{tier}/{conf}] [{dig}] {d.page_hint_start}–{d.page_hint_end} "
            f"**{d.title}** ({d.page_count}p){flags_str}"
        )

    lines.extend(["", "## Passages", ""])

    for p in passages:
        flags_str = f" ⚠ {', '.join(p.review_flags)}" if p.review_flags else ""
        action_str = f" [{p.sizing_action}]" if p.sizing_action != "none" else ""
        lines.append(
            f"- **{p.passage_id}** {p.page_hint_start}–{p.page_hint_end} "
            f"({p.page_count}p, {p.content_type}){action_str}{flags_str}"
        )
        lines.append(f"  → {p.title}")

    # TOC Cross-Reference Analysis
    if toc_xref and toc_entries:
        matched_count = len(toc_xref.get("matched", []))
        missed = toc_xref.get("missed_headings", [])

        lines.extend(["", "## TOC Cross-Reference", ""])
        lines.append(f"Matched: {matched_count}/{len(toc_entries)} TOC entries → discovered divisions")
        lines.append("")

        if missed:
            lines.append(f"### Missed Headings ({len(missed)} TOC entries with no matching division)")
            lines.append("")
            lines.append("These TOC entries may represent structural divisions that Pass 1/2/3 missed:")
            lines.append("")
            for m in missed:
                lines.append(f"- p.{m['page_number']} **{m['title']}**")
                if m.get("nearest_div"):
                    lines.append(f"  nearest: {m['nearest_div']} (score={m['nearest_score']})")
            lines.append("")

    elif toc_entries:
        lines.extend(["", "## TOC Entries (raw)", ""])
        for entry in toc_entries[:30]:
            indent = "  " * entry.indent_level
            lines.append(f"  {indent}- {entry.title} ... p.{entry.page_number}")
        if len(toc_entries) > 30:
            lines.append(f"  ... and {len(toc_entries) - 30} more entries")

    # Ordinal Sequence Warnings
    if ordinal_warnings:
        lines.extend(["", "## Ordinal Sequence Warnings", ""])
        lines.append(f"{len(ordinal_warnings)} ordinal sequence issue(s) detected:")
        lines.append("")
        for w in ordinal_warnings:
            lines.append(
                f"- **{w['keyword']}**: expected ordinal {w['expected_ordinal']}, "
                f"got {w['actual_ordinal']} at {w['div_id']} ({w['title'][:40]})"
            )

    lines.extend(["", "---", ""])

    return "\n".join(lines)


def write_full_output(
    outdir: str,
    book_id: str,
    divisions: list[DivisionNode],
    passages: list[PassageRecord],
    toc_entries: list[TOCEntry],
    pages: list[PageRecord],
    html_sha: str,
    pages_sha: str,
    pass1_count: int,
    pass2_count: int,
    pass3_stats: Optional[dict] = None,
    toc_xref: Optional[dict] = None,
    ordinal_warnings: Optional[list] = None,
):
    """Write all Stage 2 output artifacts."""
    os.makedirs(outdir, exist_ok=True)

    # 1. divisions.json
    div_path = os.path.join(outdir, f"{book_id}_divisions.json")
    div_data = {
        "schema_version": "divisions_v0.1",
        "book_id": book_id,
        "source_html_sha256": html_sha,
        "pages_jsonl_sha256": pages_sha,
        "generator_tool": TOOL_NAME,
        "generator_version": TOOL_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "total_pages": len(pages),
        "total_divisions": len(divisions),
        "toc_detected": bool(toc_entries),
        "structure_confidence": compute_structure_confidence(divisions),
        "divisions": [d.to_dict() for d in divisions],
        "human_overrides_applied": False,
        "notes": None,
    }
    with open(div_path, "w", encoding="utf-8") as f:
        json.dump(div_data, f, ensure_ascii=False, indent=2)
    print(f"[Output] Divisions: {div_path}")

    # 2. passages.jsonl
    pass_path = os.path.join(outdir, f"{book_id}_passages.jsonl")
    with open(pass_path, "w", encoding="utf-8") as f:
        for p in passages:
            f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")
    print(f"[Output] Passages: {pass_path}")

    # 3. structure_report.json
    report = generate_structure_report(
        book_id, divisions, passages, pass1_count, pass2_count,
        len(toc_entries), len(pages), pass3_stats=pass3_stats,
        toc_xref=toc_xref, ordinal_warnings=ordinal_warnings,
    )
    report_path = os.path.join(outdir, f"{book_id}_structure_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[Output] Report: {report_path}")

    # 4. structure_review.md
    review_md = generate_full_review_md(
        book_id, divisions, passages, toc_entries, pages,
        toc_xref=toc_xref, ordinal_warnings=ordinal_warnings,
    )
    review_path = os.path.join(outdir, f"{book_id}_structure_review.md")
    with open(review_path, "w", encoding="utf-8") as f:
        f.write(review_md)
    print(f"[Output] Review: {review_path}")

    # 5. Empty overrides template
    overrides_path = os.path.join(outdir, f"{book_id}_structure_overrides.json")
    if not os.path.exists(overrides_path):
        with open(overrides_path, "w", encoding="utf-8") as f:
            json.dump({"overrides": []}, f, ensure_ascii=False, indent=2)
        print(f"[Output] Overrides template: {overrides_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Stage 2: Structure Discovery — discover book divisions and passage boundaries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--html", required=True, nargs="+",
                        help="Path(s) to frozen source HTML file(s). For multi-volume: list all volume files in order.")
    parser.add_argument("--pages", required=True,
                        help="Path to Stage 1 normalized JSONL (pages.jsonl).")
    parser.add_argument("--metadata", required=True,
                        help="Path to intake_metadata.json.")
    parser.add_argument("--patterns", required=True,
                        help="Path to structural_patterns.yaml.")
    parser.add_argument("--outdir", required=True,
                        help="Output directory for structure artifacts.")
    parser.add_argument("--skip-llm", action="store_true",
                        help="Run only deterministic passes (Pass 1, 1.5, 2). Skip LLM Pass 3.")
    parser.add_argument("--apply-overrides",
                        help="Path to structure_overrides.json to apply human review decisions.")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print detailed progress information.")

    args = parser.parse_args()

    # --- Load inputs ---

    if args.verbose:
        print(f"[Stage 2] Loading structural patterns from {args.patterns}")
    with open(args.patterns, encoding="utf-8") as f:
        patterns = yaml.safe_load(f)

    global ORDINALS
    ORDINALS = load_ordinals(patterns)
    keywords = load_keywords(patterns)

    if args.verbose:
        print(f"[Stage 2] Loaded {len(ORDINALS)} ordinals, {len(keywords)} keywords")

    if args.verbose:
        print(f"[Stage 2] Loading metadata from {args.metadata}")
    with open(args.metadata, encoding="utf-8") as f:
        metadata = json.load(f)

    book_id = metadata.get("book_id", "unknown")
    multi_volume = len(args.html) > 1

    if args.verbose:
        print(f"[Stage 2] Loading pages from {args.pages}")
    pages = load_pages(args.pages)
    page_index = build_page_index(pages)

    if args.verbose:
        print(f"[Stage 2] Loaded {len(pages)} pages for book '{book_id}' ({'multi-volume' if multi_volume else 'single-volume'})")

    # --- Pass 1: HTML-tagged headings ---

    all_pass1_headings: list[HeadingCandidate] = []
    all_toc_pages: list[int] = []
    total_html_pages = 0

    for vol_i, html_path in enumerate(args.html, start=1):
        if args.verbose:
            print(f"[Pass 1] Processing {html_path} (volume {vol_i})")

        vol_num = vol_i if multi_volume else 1
        headings, toc_pages, html_page_count = pass1_extract_html_headings(
            html_path, page_index, volume_number=vol_num, multi_volume=multi_volume,
            pages_list=pages,
        )
        all_pass1_headings.extend(headings)
        all_toc_pages.extend(toc_pages)
        total_html_pages += html_page_count

    # --- Pre-flight validation: HTML vs JSONL page count ---
    unmapped_headings = [h for h in all_pass1_headings if not h.page_mapped]
    mapped_headings = [h for h in all_pass1_headings if h.page_mapped]

    if total_html_pages > 0 and len(pages) > 0:
        ratio = len(pages) / total_html_pages
        if ratio < 0.9:
            print(f"[PREFLIGHT WARNING] JSONL has {len(pages)} pages but HTML has {total_html_pages} content pages (ratio={ratio:.2f})")
            print(f"  → {len(unmapped_headings)} of {len(all_pass1_headings)} headings could not be mapped to JSONL pages")
            if len(unmapped_headings) > 0:
                print(f"  → Unmapped headings will be DROPPED. Run Stage 1 normalization on the full book first.")
            if ratio < 0.5:
                print(f"  [PREFLIGHT ERROR] Less than 50% of HTML pages are in the JSONL. Results will be unreliable.")
                print(f"  → Normalize the full book before running Stage 2.")
                return 1

    print(f"[Pass 1] Found {len(all_pass1_headings)} HTML-tagged headings "
          f"({len(mapped_headings)} mapped, {len(unmapped_headings)} unmapped)")

    # Use only mapped headings for further processing
    all_pass1_headings = mapped_headings

    # --- Pass 1.5: TOC parsing ---

    toc_entries = pass1_5_parse_toc(pages, all_toc_pages)
    if toc_entries:
        print(f"[Pass 1.5] Parsed {len(toc_entries)} TOC entries from {len(all_toc_pages)} TOC page(s)")
    else:
        print("[Pass 1.5] No TOC detected")

    # --- Pass 2: Keyword heuristic scan ---

    # Continue document_position counter from where Pass 1 left off
    max_pass1_docpos = max((h.document_position for h in all_pass1_headings), default=-1) + 1

    pass2_headings = pass2_keyword_scan(
        pages, keywords, ORDINALS, all_pass1_headings, multi_volume,
        next_doc_position=max_pass1_docpos,
    )
    print(f"[Pass 2] Found {len(pass2_headings)} new keyword-based candidates (after dedup with Pass 1)")

    # --- Combine results ---

    all_headings = all_pass1_headings + pass2_headings
    # Sort by (seq_index, document_position) — preserves document order
    all_headings.sort(key=lambda h: (h.seq_index, h.document_position))

    print(f"[Combined] Total headings: {len(all_headings)} (Pass 1: {len(all_pass1_headings)}, Pass 2: {len(pass2_headings)})")

    # --- Generate output ---

    os.makedirs(args.outdir, exist_ok=True)

    # Compute SHA-256 of input files for provenance
    # Use first HTML file for SHA (multi-volume: would need combined hash)
    html_sha = sha256_file(args.html[0])
    pages_sha = sha256_file(args.pages)

    # Candidates JSON (intermediate, for inspection or Pass 3 input)
    candidates_path = os.path.join(args.outdir, f"{book_id}_candidates.json")
    with open(candidates_path, "w", encoding="utf-8") as f:
        json.dump({
            "book_id": book_id,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "pass1_count": len(all_pass1_headings),
            "pass2_count": len(pass2_headings),
            "toc_entry_count": len(toc_entries),
            "total_pages": len(pages),
            "total_html_pages": total_html_pages,
            "unmapped_heading_count": len(unmapped_headings),
            "headings": [
                {
                    "title": h.title,
                    "seq_index": h.seq_index,
                    "page_number_int": h.page_number_int,
                    "volume": h.volume,
                    "page_hint": h.page_hint,
                    "detection_method": h.detection_method,
                    "confidence": h.confidence,
                    "keyword_type": h.keyword_type,
                    "ordinal": h.ordinal,
                    "inline_heading": h.inline_heading,
                    "heading_text_boundary": h.heading_text_boundary,
                    "document_position": h.document_position,
                    "page_mapped": h.page_mapped,
                    "notes": h.notes,
                }
                for h in all_headings
            ],
            "toc_entries": [
                {
                    "title": e.title,
                    "page_number": e.page_number,
                    "indent_level": e.indent_level,
                }
                for e in toc_entries
            ],
        }, f, ensure_ascii=False, indent=2)

    if args.verbose:
        print(f"[Output] Candidates written to {candidates_path}")

    # --- Pass 3: LLM-Assisted Discovery ---

    pass3_stats = {"llm_calls": 0, "confirmed": 0, "rejected": 0, "new_discovered": 0}
    prompt_dir = os.path.join(os.path.dirname(__file__), "..", "2_structure_discovery", "prompts")
    prompt_dir = os.path.normpath(prompt_dir)

    if args.skip_llm:
        print("[Pass 3] Skipped (--skip-llm). Building tree from deterministic passes only.")
        # Use flat tree builder
        science_id = metadata.get("science_id") or metadata.get("primary_science")
        divisions = build_division_tree(all_headings, pages, book_id, multi_volume, keywords)
        print(f"[Tree] Built {len(divisions)} divisions (flat — no hierarchy)")
    else:
        # Initialize LLM client
        client, err = _init_llm_client()
        if not client:
            print(f"[Pass 3] ERROR: {err}", file=sys.stderr)
            print("[Pass 3] Falling back to deterministic passes only.")
            science_id = metadata.get("science_id") or metadata.get("primary_science")
            divisions = build_division_tree(all_headings, pages, book_id, multi_volume, keywords)
            print(f"[Tree] Built {len(divisions)} divisions (flat — no hierarchy)")
        else:
            # Step 3a: Macro structure
            print("[Pass 3a] Macro structure discovery...")
            pass3_stats["llm_calls"] += 1
            result_3a = pass3a_macro_structure(
                client, all_headings, pages, toc_entries, metadata, prompt_dir,
            )

            if not result_3a:
                print("[Pass 3a] FAILED — falling back to deterministic tree.")
                science_id = metadata.get("science_id") or metadata.get("primary_science")
                divisions = build_division_tree(all_headings, pages, book_id, multi_volume, keywords)
                print(f"[Tree] Built {len(divisions)} divisions (flat — fallback)")
            else:
                # Count stats
                for d in result_3a.get("decisions", []):
                    if d.get("action") == "confirm":
                        pass3_stats["confirmed"] += 1
                    elif d.get("action") == "reject":
                        pass3_stats["rejected"] += 1
                pass3_stats["new_discovered"] += len(result_3a.get("new_divisions", []))

                if result_3a.get("structure_notes"):
                    print(f"  [Pass 3a] LLM notes: {result_3a['structure_notes'][:120]}")

                # Step 3b: Deep scan for large divisions
                # Skip for small books (<50 pages) — 3a already sees full structure
                pass3b_results: dict[int, dict] = {}

                if len(pages) < 50:
                    print(f"[Pass 3b] Skipping — small book ({len(pages)} pages < 50)")
                else:
                    # Identify confirmed macro divisions > 5 pages for deep scan
                    decisions = result_3a.get("decisions", [])
                    decision_map = {d["candidate_index"]: d for d in decisions if "candidate_index" in d}

                    # Build preliminary page ranges to identify large divisions
                    confirmed_headings = []
                    for i, h in enumerate(all_headings):
                        dec = decision_map.get(i)
                        if dec and dec.get("action") == "reject":
                            continue
                        confirmed_headings.append((i, h))

                    # Compute approximate page ranges for deep scan eligibility
                    max_seq = max(p.seq_index for p in pages)
                    deep_scan_targets = []
                    for idx_in_list, (orig_idx, h) in enumerate(confirmed_headings):
                        dec = decision_map.get(orig_idx, {})
                        level = dec.get("level", 1)
                        # Only scan top-level or second-level divisions
                        if level > 2:
                            continue

                        # Estimate end page: next heading at same or higher level
                        end_est = max_seq
                        for j in range(idx_in_list + 1, len(confirmed_headings)):
                            other_orig_idx, other_h = confirmed_headings[j]
                            other_dec = decision_map.get(other_orig_idx, {})
                            other_level = other_dec.get("level", 1)
                            if other_level <= level:
                                end_est = other_h.seq_index - 1
                                break

                        page_count_est = end_est - h.seq_index + 1
                        if page_count_est > 5:
                            # Find known sub-headings within this range
                            sub_headings = []
                            for _, (sub_orig_idx, sub_h) in enumerate(confirmed_headings):
                                sub_dec = decision_map.get(sub_orig_idx, {})
                                sub_level = sub_dec.get("level", 1)
                                if (sub_h.seq_index >= h.seq_index and
                                    sub_h.seq_index <= end_est and
                                    sub_level > level and
                                    sub_orig_idx != orig_idx):
                                    sub_headings.append(sub_h)

                            deep_scan_targets.append((orig_idx, h, end_est, sub_headings))

                    if deep_scan_targets:
                        print(f"[Pass 3b] Deep scanning {len(deep_scan_targets)} macro divisions...")
                        for orig_idx, h, end_est, sub_headings in deep_scan_targets:
                            pass3_stats["llm_calls"] += 1
                            result_3b = pass3b_deep_scan(
                                client,
                                section_title=h.title,
                                section_type=h.keyword_type or "implicit",
                                start_seq=h.seq_index,
                                end_seq=end_est,
                                known_subheadings=sub_headings,
                                pages=pages,
                                metadata=metadata,
                                prompt_dir=prompt_dir,
                            )
                            if result_3b:
                                pass3b_results[orig_idx] = result_3b
                                new_subs = len(result_3b.get("new_subdivisions", []))
                                if new_subs > 0:
                                    pass3_stats["new_discovered"] += new_subs
                    else:
                        print("[Pass 3b] No divisions > 5 pages — skipping deep scan.")

                # Integrate all Pass 3 results
                enriched_headings = integrate_pass3_results(
                    all_headings, result_3a, pass3b_results, pages,
                )

                # Build hierarchical tree
                science_id = metadata.get("science_id") or metadata.get("primary_science")
                divisions = build_hierarchical_tree(
                    enriched_headings, pages, book_id, multi_volume, keywords,
                    verbose=args.verbose,
                )
                print(f"[Tree] Built {len(divisions)} divisions (hierarchical)")
                max_depth = max((d.level for d in divisions), default=0)
                print(f"  Max depth: {max_depth}, LLM calls: {pass3_stats['llm_calls']}")

    # --- Post-tree validation and cross-referencing ---

    # TOC cross-reference (Spec §7.5)
    toc_xref = cross_reference_toc(divisions, toc_entries, pages)
    if toc_entries:
        n_matched = len(toc_xref["matched"])
        n_missed = len(toc_xref["missed_headings"])
        print(f"[TOC] Cross-reference: {n_matched}/{len(toc_entries)} matched, "
              f"{n_missed} missed headings")
        if n_missed > 0 and args.verbose:
            for m in toc_xref["missed_headings"][:5]:
                print(f"  missed: page {m['page_number']} '{m['title'][:50]}'")

    # Ordinal sequence validation (Spec §7.5.3)
    ordinal_warnings = validate_ordinal_sequences(divisions)
    if ordinal_warnings:
        print(f"[Ordinal] {len(ordinal_warnings)} ordinal sequence warning(s)")
        for w in ordinal_warnings:
            div = next((d for d in divisions if d.id == w["div_id"]), None)
            if div and "ordinal_gap" not in div.review_flags:
                div.review_flags.append("ordinal_gap")

    # Apply human overrides if provided (Spec §10.5)
    if args.apply_overrides:
        if os.path.exists(args.apply_overrides):
            print(f"[Override] Applying overrides from {args.apply_overrides}")
            divisions, overrides_applied = apply_overrides(
                divisions, passages if 'passages' in dir() else [],
                args.apply_overrides, pages,
            )
            if overrides_applied:
                print("[Override] Re-building passages after overrides...")
        else:
            print(f"[Override] WARNING: file not found: {args.apply_overrides}")

    # --- Build passages ---

    science_id = metadata.get("science_id") or metadata.get("primary_science")
    passages = build_passages(divisions, book_id, science_id, pages=pages)
    print(f"[Passages] Built {len(passages)} passages")

    # Post-build sanity: check for passage overlaps
    # Same-page siblings (both start on same page, each covers ≤1 page) are tolerated
    # as they represent multiple headings sharing one page.
    true_overlap_count = 0
    same_page_count = 0
    for idx in range(len(passages) - 1):
        p1, p2 = passages[idx], passages[idx + 1]
        if p1.end_seq_index >= p2.start_seq_index:
            if p1.start_seq_index == p2.start_seq_index and \
               p1.start_seq_index == p1.end_seq_index and \
               p2.start_seq_index == p2.end_seq_index:
                same_page_count += 1
            else:
                true_overlap_count += 1
    if true_overlap_count > 0:
        print(f"[WARNING] {true_overlap_count} passage overlap(s) detected — review output carefully")
    if same_page_count > 0:
        print(f"[INFO] {same_page_count} same-page passage pair(s) (multiple headings on one page)")

    # --- Write all output artifacts ---

    write_full_output(
        outdir=args.outdir,
        book_id=book_id,
        divisions=divisions,
        passages=passages,
        toc_entries=toc_entries,
        pages=pages,
        html_sha=html_sha,
        pages_sha=pages_sha,
        pass1_count=len(all_pass1_headings),
        pass2_count=len(pass2_headings),
        pass3_stats=pass3_stats,
        toc_xref=toc_xref,
        ordinal_warnings=ordinal_warnings if ordinal_warnings else [],
    )

    print(f"[Stage 2] Complete. Review: {os.path.join(args.outdir, f'{book_id}_structure_review.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
