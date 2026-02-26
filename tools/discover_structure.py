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

Version: v0.1
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

TOOL_VERSION = "v0.1"
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


@dataclass
class TOCEntry:
    """A parsed entry from the book's table of contents."""
    title: str
    page_number: Optional[int]
    indent_level: int = 0
    line_index: int = 0


@dataclass
class Division:
    """A node in the book's structural division tree."""
    div_id: str
    div_type: str                      # باب, فصل, مبحث, تنبيه, root, volume, etc.
    title: str
    level: int                         # 0=root, 1=volume, 2=top, 3=mid, 4=low, 5=supp
    parent_id: Optional[str]
    detection_method: str              # html_tagged, keyword_heuristic, llm_discovered, inferred
    confidence: str                    # confirmed, high, medium, low
    start_seq_index: int
    end_seq_index: int                 # inclusive
    start_page_hint: str
    end_page_hint: str
    digestible: bool = True
    page_count: int = 1
    children: list[str] = field(default_factory=list)
    keyword_type: Optional[str] = None
    ordinal: Optional[int] = None
    content_type: str = "teaching"     # teaching, exercise, non_digestible, uncertain
    review_flags: list[str] = field(default_factory=list)


@dataclass
class Passage:
    """A work-unit for Stage 3+ processing."""
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
    digestible: bool = True
    content_type: str = "teaching"
    sizing_action: str = "none"
    sizing_notes: Optional[str] = None
    split_info: Optional[dict] = None
    merge_info: Optional[dict] = None
    review_flags: list[str] = field(default_factory=list)
    science_id: Optional[str] = None
    predecessor_passage_id: Optional[str] = None
    successor_passage_id: Optional[str] = None


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
) -> tuple[list[HeadingCandidate], list[int]]:
    """Extract content headings from <span class="title"> in frozen HTML.

    Args:
        html_path: path to the frozen source HTML file
        page_index: mapping (volume, page_number_int) -> PageRecord
        volume_number: volume number for this HTML file
        multi_volume: whether the book has multiple volumes

    Returns:
        (list of HeadingCandidate, list of TOC page seq_indices)
    """
    with open(html_path, encoding="utf-8") as f:
        html = f.read()

    headings: list[HeadingCandidate] = []
    toc_pages: list[int] = []

    # Split into PageText divs
    page_divs = re.split(r"<div class='PageText'>", html)

    # Skip index 0 (before first PageText) and index 1 (metadata page)
    if len(page_divs) < 3:
        return headings, toc_pages

    current_page_number = 0
    current_seq_index = 0

    for div_text in page_divs[2:]:  # Skip pre-HTML and metadata page
        # Update current page number from PageNumber span
        pn_match = re.search(r"<span class='PageNumber'>\(ص:\s*([٠-٩]+)\s*\)</span>", div_text)
        if pn_match:
            current_page_number = indic_to_int(pn_match.group(1))
            # Look up seq_index
            key = (volume_number, current_page_number)
            if key in page_index:
                current_seq_index = page_index[key].seq_index
            else:
                # Try to find by page_number_int alone (single-volume fallback)
                for (v, p), rec in page_index.items():
                    if p == current_page_number and v == volume_number:
                        current_seq_index = rec.seq_index
                        break

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

            # R1.5: Detect TOC headings
            toc_keywords = ["فهرس", "المحتويات", "فهرس الموضوعات"]
            is_toc = any(kw in clean for kw in toc_keywords)
            if is_toc:
                toc_pages.append(current_seq_index)

            headings.append(HeadingCandidate(
                title=clean,
                seq_index=current_seq_index,
                page_number_int=current_page_number,
                volume=volume_number,
                page_hint=page_hint,
                detection_method="html_tagged",
                confidence="confirmed",
                notes="TOC heading" if is_toc else None,
            ))

    return headings, toc_pages


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

    # Collect all pages from the first TOC page to the end of the book
    # (TOC is typically at the end, may span multiple pages)
    min_toc_idx = min(toc_set)

    for page in pages:
        if page.seq_index < min_toc_idx:
            continue

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

    return entries


# ---------------------------------------------------------------------------
# Pass 2: Keyword Heuristic Detection
# ---------------------------------------------------------------------------

# Pre-compiled ordinal pattern (filled at runtime after loading YAML)
_ORDINAL_RE: Optional[re.Pattern] = None


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
) -> list[HeadingCandidate]:
    """Scan normalized text for keyword-based heading candidates.

    Implements the conservative rules from STRUCTURE_SPEC v1.0 §6.

    Args:
        pages: all page records from Stage 1 JSONL
        keywords: keyword dict from structural_patterns.yaml
        ordinals: ordinal dict
        pass1_headings: headings already found by Pass 1 (for dedup)
        multi_volume: whether book is multi-volume

    Returns:
        New heading candidates not already found by Pass 1.
    """
    global _ORDINAL_RE
    if _ORDINAL_RE is None and ordinals:
        _ORDINAL_RE = _build_ordinal_regex(ordinals)

    # Build Pass 1 dedup index: (seq_index, normalized_title_prefix) -> True
    pass1_index: set[tuple[int, str]] = set()
    for h in pass1_headings:
        norm = normalize_arabic_for_match(h.title)[:30]
        pass1_index.add((h.seq_index, norm))

    candidates: list[HeadingCandidate] = []

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
                if _ORDINAL_RE:
                    rest_stripped_check = rest_after_keyword.strip()
                    if rest_stripped_check and _ORDINAL_RE.match(rest_stripped_check):
                        has_ordinal = True
                if not has_ordinal and len(line) > 20:
                    continue  # Skip: indefinite كتاب without ordinal in a non-trivial line

            # C2: Not a TOC entry (dot-leader pattern)
            # Catches: multiple dots/middots, single or multiple ellipsis chars,
            # or any dot-like sequence followed by a page number at end of line
            if re.search(r"[\.·]{3,}", line):
                continue
            if re.search(r"…", line):  # Single ellipsis character (U+2026)
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
            if _ORDINAL_RE and len(line) <= 120:
                ord_match = _ORDINAL_RE.match(rest_stripped) if rest_stripped else None
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
            ))

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
# Division Tree Builder
# ---------------------------------------------------------------------------

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
    """
    kw = heading.keyword_type or ""
    title_clean = heading.title.strip()

    # Non-digestible types
    if kw in NON_DIGESTIBLE_TYPES or title_clean in NON_DIGESTIBLE_TYPES:
        return "false", "non_content"

    # Non-digestible title patterns
    for pat in NON_DIGESTIBLE_TITLE_PATTERNS:
        if pat in title_clean:
            return "false", "non_content"

    # Exercise types
    if kw in EXERCISE_TYPES:
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

    For --skip-llm mode, this produces a usable (if flat) tree.
    """
    if not headings:
        return []

    # Sort headings by seq_index, then by position within page
    sorted_headings = sorted(headings, key=lambda h: (h.seq_index, h.title))

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

    divisions: list[DivisionNode] = []

    for i, h in enumerate(deduped):
        div_id = f"div_{i:04d}"

        # Page range: from this heading's page to just before the next heading's page
        start_seq = h.seq_index
        if i + 1 < len(deduped):
            end_seq = deduped[i + 1].seq_index - 1
            if end_seq < start_seq:
                end_seq = start_seq  # Same-page consecutive headings
        else:
            end_seq = max_seq

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
) -> list[PassageRecord]:
    """Construct passages from leaf-level digestible divisions.

    In the flat tree (pre-LLM), every division is a leaf. In the hierarchical tree
    (post-LLM), only divisions with no children are leaves.
    """
    # Identify leaf divisions (no children)
    all_ids = {d.id for d in divisions}
    parent_ids = {d.parent_id for d in divisions if d.parent_id}
    leaf_divisions = [d for d in divisions if d.id not in parent_ids]

    # Filter to digestible leaves
    digestible_leaves = [d for d in leaf_divisions if d.digestible != "false"]

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

        page_count = div.page_count

        # Sizing: merge short divisions
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
            volume=None,  # TODO: derive from pages
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

    return {
        "schema_version": "structure_report_v0.1",
        "book_id": book_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "pass_stats": {
            "pass1_html_tagged": pass1_count,
            "pass1_5_toc_entries": toc_count,
            "pass2_keyword_candidates": pass2_count,
            "pass2_after_dedup": pass2_count,
            "pass3_llm_discovered": 0,
            "pass3_confirmed": 0,
            "pass3_rejected": 0,
            "pass3_llm_calls": 0,
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
            "toc_mismatches": 0,
            "flagged_items": flagged_items,
        },
    }


def generate_full_review_md(
    book_id: str,
    divisions: list[DivisionNode],
    passages: list[PassageRecord],
    toc_entries: list[TOCEntry],
    pages: list[PageRecord],
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

    for d in sorted(divisions, key=lambda x: x.start_seq_index):
        indent = "  " * (d.level - 1)
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

    if toc_entries:
        lines.extend(["", "## TOC Cross-Reference", ""])
        for entry in toc_entries[:30]:  # Cap at 30 entries for readability
            indent = "  " * entry.indent_level
            lines.append(f"  {indent}- {entry.title} ... p.{entry.page_number}")
        if len(toc_entries) > 30:
            lines.append(f"  ... and {len(toc_entries) - 30} more entries")

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
        len(toc_entries), len(pages),
    )
    report_path = os.path.join(outdir, f"{book_id}_structure_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[Output] Report: {report_path}")

    # 4. structure_review.md
    review_md = generate_full_review_md(book_id, divisions, passages, toc_entries, pages)
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


# ---------------------------------------------------------------------------
# Structure Review Markdown generation (deterministic-only, pre-tree)
# ---------------------------------------------------------------------------

def generate_review_md(
    book_id: str,
    headings: list[HeadingCandidate],
    toc_entries: list[TOCEntry],
    pages: list[PageRecord],
) -> str:
    """Generate a human-readable structure review Markdown (pre-LLM, deterministic passes only)."""
    lines = [
        f"# Structure Review — {book_id}",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Total pages: {len(pages)}",
        f"Total headings found: {len(headings)}",
        "",
        "## Headings (document order)",
        "",
    ]

    # Sort by seq_index
    sorted_h = sorted(headings, key=lambda h: (h.seq_index, h.title))

    for h in sorted_h:
        tier = "T1" if h.detection_method == "html_tagged" else "T2"
        conf = h.confidence
        inline_mark = " [INLINE]" if h.inline_heading else ""
        kw_mark = f" ({h.keyword_type})" if h.keyword_type else ""
        ord_mark = f" #{h.ordinal}" if h.ordinal else ""
        lines.append(
            f"- [{tier}/{conf}] {h.page_hint} — **{h.title}**{kw_mark}{ord_mark}{inline_mark}"
        )

    if toc_entries:
        lines.extend([
            "",
            "## TOC Entries",
            "",
        ])
        for entry in toc_entries:
            indent = "  " * entry.indent_level
            lines.append(f"  {indent}- {entry.title} ... p.{entry.page_number}")

    lines.extend([
        "",
        "---",
        "",
        "*Pass 3 (LLM) and passage construction not yet applied. Run without --skip-llm for full output.*",
    ])

    return "\n".join(lines)

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

    for vol_i, html_path in enumerate(args.html, start=1):
        if args.verbose:
            print(f"[Pass 1] Processing {html_path} (volume {vol_i})")

        vol_num = vol_i if multi_volume else 1
        headings, toc_pages = pass1_extract_html_headings(
            html_path, page_index, volume_number=vol_num, multi_volume=multi_volume
        )
        all_pass1_headings.extend(headings)
        all_toc_pages.extend(toc_pages)

    print(f"[Pass 1] Found {len(all_pass1_headings)} HTML-tagged headings")

    # --- Pass 1.5: TOC parsing ---

    toc_entries = pass1_5_parse_toc(pages, all_toc_pages)
    if toc_entries:
        print(f"[Pass 1.5] Parsed {len(toc_entries)} TOC entries from {len(all_toc_pages)} TOC page(s)")
    else:
        print("[Pass 1.5] No TOC detected")

    # --- Pass 2: Keyword heuristic scan ---

    pass2_headings = pass2_keyword_scan(
        pages, keywords, ORDINALS, all_pass1_headings, multi_volume
    )
    print(f"[Pass 2] Found {len(pass2_headings)} new keyword-based candidates (after dedup with Pass 1)")

    # --- Combine results ---

    all_headings = all_pass1_headings + pass2_headings
    all_headings.sort(key=lambda h: (h.seq_index, h.title))

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

    if args.skip_llm:
        print("[Pass 3] Skipped (--skip-llm). Building tree from deterministic passes only.")
    else:
        # TODO: Implement Pass 3 (LLM-assisted discovery)
        print("[Pass 3] LLM pass not yet implemented. Building tree from deterministic passes only.")

    # --- Build division tree ---

    science_id = metadata.get("science_id") or metadata.get("primary_science")

    divisions = build_division_tree(all_headings, pages, book_id, multi_volume, keywords)
    print(f"[Tree] Built {len(divisions)} divisions")

    # --- Build passages ---

    passages = build_passages(divisions, book_id, science_id)
    print(f"[Passages] Built {len(passages)} passages")

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
    )

    print(f"[Stage 2] Complete. Review: {os.path.join(args.outdir, f'{book_id}_structure_review.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
