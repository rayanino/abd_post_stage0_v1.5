#!/usr/bin/env python3
"""Tests for Stage 2: Structure Discovery (tools/discover_structure.py).

Test strategy:
- Unit tests for individual functions (normalization, ordinal parsing, etc.)
- Integration tests against synthetic HTML and JSONL
- No book-specific tests — tests must work on any Shamela-formatted input
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

import pytest

# Add tools/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from discover_structure import (
    DivisionNode,
    HeadingCandidate,
    PageRecord,
    PassageRecord,
    TOCEntry,
    build_division_tree,
    build_page_index,
    build_passages,
    classify_digestibility,
    detect_keyword_type_from_title,
    indic_to_int,
    int_to_indic,
    load_keywords,
    load_ordinals,
    make_page_hint,
    normalize_arabic_for_match,
    pass1_5_parse_toc,
    pass1_extract_html_headings,
    pass2_keyword_scan,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_patterns():
    """Minimal structural_patterns.yaml content for testing."""
    return {
        "ordinal_patterns": {
            "arabic_ordinals": [
                "الأوَّل|الأول",
                "الثاني|الثانى",
                "الثالث",
                "الرابع",
                "الخامس",
                "السادس",
            ]
        },
        "keyword_patterns": {
            "top_level": [
                {"keyword": "باب", "definite_form": "الباب"},
                {"keyword": "كتاب", "definite_form": "الكتاب"},
            ],
            "mid_level": [
                {"keyword": "فصل", "definite_form": "الفصل"},
                {"keyword": "مبحث", "definite_form": "المبحث"},
                {"keyword": "تقسيم", "definite_form": "التقسيم"},
            ],
            "low_level": [
                {"keyword": "تنبيه", "plural": "تنبيهات", "dual": "تنبيهان"},
                {"keyword": "خاتمة"},
                {"keyword": "فائدة"},
            ],
            "supplementary": [
                {"keyword": "مقدمة"},
                {"keyword": "تطبيق", "variants": ["تمارين", "مسائل التمرين"]},
                {"keyword": "فهرس", "variants": ["فهرس الموضوعات", "المحتويات"]},
            ],
        },
    }


@pytest.fixture
def ordinals(sample_patterns):
    return load_ordinals(sample_patterns)


@pytest.fixture
def keywords(sample_patterns):
    return load_keywords(sample_patterns)


def make_shamela_html(pages: list[dict], metadata_title: str = "كتاب تجريبي") -> str:
    """Generate synthetic Shamela HTML for testing.

    Each page dict has: page_number (int), content (str), headings (list of str).
    """
    html_parts = ["<html lang='ar' dir='rtl'><body><div class='Main'>"]

    # Metadata page
    html_parts.append(
        f"<div class='PageText'><span class='title'>{metadata_title}</span>"
        "<span class='title'>القسم:</span> كتب البلاغة</div>"
    )

    for page in pages:
        pn = int_to_indic(page["page_number"])
        html_parts.append(
            f" <div class='PageText'><div class='PageHead'>"
            f"<span class='PartName'>{metadata_title}</span>"
            f"<span class='PageNumber'>(ص: {pn})</span><hr/></div>"
        )

        for heading in page.get("headings", []):
            html_parts.append(f'&#8204;<span class="title">&#8204;{heading}</span></p>')

        html_parts.append(f'{page.get("content", "محتوى الصفحة")}</p>')
        html_parts.append("</div>")

    html_parts.append("</div></body></html>")
    return "".join(html_parts)


def make_pages(entries: list[dict]) -> list[PageRecord]:
    """Create PageRecord list from simplified dicts.

    Each entry: {page: int, text: str, ...}
    """
    pages = []
    for i, e in enumerate(entries):
        pages.append(PageRecord(
            seq_index=i,
            page_number_int=e.get("page", i + 1),
            volume=e.get("volume", 1),
            matn_text=e.get("text", ""),
            page_hint=f"ص:{int_to_indic(e.get('page', i + 1))}",
            footnote_section_format=e.get("fn_format", "none"),
        ))
    return pages


# ---------------------------------------------------------------------------
# Unit tests: utility functions
# ---------------------------------------------------------------------------

class TestIndicConversion:
    def test_indic_to_int_basic(self):
        assert indic_to_int("١٩") == 19

    def test_indic_to_int_large(self):
        assert indic_to_int("٣٠٨") == 308

    def test_indic_to_int_zero(self):
        assert indic_to_int("٠") == 0

    def test_int_to_indic_basic(self):
        assert int_to_indic(19) == "١٩"

    def test_int_to_indic_large(self):
        assert int_to_indic(308) == "٣٠٨"


class TestNormalizeArabic:
    def test_strip_diacritics(self):
        assert normalize_arabic_for_match("فَصْلٌ") == normalize_arabic_for_match("فصل")

    def test_normalize_ya(self):
        assert normalize_arabic_for_match("الثانى") == normalize_arabic_for_match("الثاني")

    def test_normalize_alef(self):
        assert normalize_arabic_for_match("إبراهيم") == normalize_arabic_for_match("ابراهيم")

    def test_collapse_whitespace(self):
        assert normalize_arabic_for_match("الباب  الأول") == "الباب الاول"


class TestMakePageHint:
    def test_single_volume(self):
        assert make_page_hint(1, 19) == "ص:١٩"

    def test_multi_volume(self):
        assert make_page_hint(2, 5, multi_volume=True) == "ج٢ ص:٥"


class TestLoadOrdinals:
    def test_basic_ordinals(self, ordinals):
        assert ordinals["الأول"] == 1
        assert ordinals["الأوَّل"] == 1
        assert ordinals["الثاني"] == 2
        assert ordinals["الثانى"] == 2
        assert ordinals["الثالث"] == 3

    def test_ordinal_count(self, ordinals):
        # 6 ordinals, some with variants
        assert len(ordinals) >= 6


class TestLoadKeywords:
    def test_basic_keywords(self, keywords):
        assert "باب" in keywords
        assert "الباب" in keywords
        assert "فصل" in keywords
        assert "تنبيه" in keywords
        assert "تنبيهات" in keywords

    def test_variants_loaded(self, keywords):
        assert "تمارين" in keywords
        assert "فهرس الموضوعات" in keywords


# ---------------------------------------------------------------------------
# Pass 1 tests
# ---------------------------------------------------------------------------

class TestPass1:
    def test_extracts_tagged_headings(self):
        html = make_shamela_html([
            {"page_number": 10, "headings": ["الباب الأول"], "content": "محتوى"},
            {"page_number": 11, "headings": ["المبحث الأول"], "content": "محتوى"},
        ])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".htm", delete=False, encoding="utf-8") as f:
            f.write(html)
            path = f.name

        try:
            pages = make_pages([{"page": 10}, {"page": 11}])
            idx = build_page_index(pages)
            headings, toc_pages, _ = pass1_extract_html_headings(path, idx)
            assert len(headings) == 2
            assert headings[0].title == "الباب الأول"
            assert headings[0].detection_method == "html_tagged"
            assert headings[0].confidence == "confirmed"
            assert headings[1].title == "المبحث الأول"
        finally:
            os.unlink(path)

    def test_skips_metadata_page(self):
        """Headings in the metadata page (first PageText) must be ignored."""
        html = make_shamela_html([
            {"page_number": 1, "headings": ["علم المعاني"], "content": "content"},
        ], metadata_title="كتاب تجريبي")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".htm", delete=False, encoding="utf-8") as f:
            f.write(html)
            path = f.name

        try:
            pages = make_pages([{"page": 1}])
            idx = build_page_index(pages)
            headings, _, _ = pass1_extract_html_headings(path, idx)
            # Only the content heading, not the metadata title
            assert all(h.title != "كتاب تجريبي" for h in headings)
        finally:
            os.unlink(path)

    def test_strips_zwnj_and_nested_tags(self):
        html_content = (
            "<html lang='ar' dir='rtl'><body><div class='Main'>"
            "<div class='PageText'><span class='title'>META</span></div>"
            " <div class='PageText'><div class='PageHead'>"
            "<span class='PartName'>T</span>"
            "<span class='PageNumber'>(ص: ٥)</span><hr/></div>"
            '&#8204;<span class="title">&#8204;<font color=red>الباب</font> الأول</span></p>'
            "content</div></div></body></html>"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".htm", delete=False, encoding="utf-8") as f:
            f.write(html_content)
            path = f.name

        try:
            pages = make_pages([{"page": 5}])
            idx = build_page_index(pages)
            headings, _, _ = pass1_extract_html_headings(path, idx)
            assert len(headings) == 1
            assert headings[0].title == "الباب الأول"
            assert "font" not in headings[0].title
            assert "&#8204;" not in headings[0].title
        finally:
            os.unlink(path)

    def test_detects_toc_page(self):
        html = make_shamela_html([
            {"page_number": 100, "headings": ["فهرس الموضوعات"], "content": "باب الأول.......5"},
        ])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".htm", delete=False, encoding="utf-8") as f:
            f.write(html)
            path = f.name

        try:
            pages = make_pages([{"page": 100}])
            idx = build_page_index(pages)
            headings, toc_pages, _ = pass1_extract_html_headings(path, idx)
            assert len(toc_pages) == 1
            # The heading IS still recorded (it's a valid heading for the TOC section)
            assert any("فهرس" in h.title for h in headings)
        finally:
            os.unlink(path)

    def test_no_double_quote_headings_returns_empty(self):
        """A file with only single-quote metadata spans returns no content headings."""
        html = (
            "<html lang='ar' dir='rtl'><body><div class='Main'>"
            "<div class='PageText'><span class='title'>META</span></div>"
            " <div class='PageText'><div class='PageHead'>"
            "<span class='PartName'>T</span>"
            "<span class='PageNumber'>(ص: ١)</span><hr/></div>"
            "just plain text</div></div></body></html>"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".htm", delete=False, encoding="utf-8") as f:
            f.write(html)
            path = f.name

        try:
            pages = make_pages([{"page": 1}])
            idx = build_page_index(pages)
            headings, _, _ = pass1_extract_html_headings(path, idx)
            assert len(headings) == 0
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Pass 1.5 tests
# ---------------------------------------------------------------------------

class TestPass1_5TOC:
    def test_parses_dot_leader_lines(self):
        pages = make_pages([
            {"page": 100, "text": "فهرس الموضوعات\nالباب الأول.......٥\nالمبحث الثاني.........١٢"},
        ])
        entries = pass1_5_parse_toc(pages, [0])
        assert len(entries) == 2
        assert entries[0].title == "الباب الأول"
        assert entries[0].page_number == 5
        assert entries[1].title == "المبحث الثاني"
        assert entries[1].page_number == 12

    def test_handles_western_digits(self):
        pages = make_pages([
            {"page": 50, "text": "الفصل الأول.......12"},
        ])
        entries = pass1_5_parse_toc(pages, [0])
        assert len(entries) == 1
        assert entries[0].page_number == 12

    def test_no_toc_pages_returns_empty(self):
        pages = make_pages([{"page": 1, "text": "محتوى عادي"}])
        entries = pass1_5_parse_toc(pages, [])
        assert len(entries) == 0

    def test_handles_ellipsis_character(self):
        pages = make_pages([
            {"page": 50, "text": "الفصل الأول…………٢٥"},
        ])
        entries = pass1_5_parse_toc(pages, [0])
        assert len(entries) == 1
        assert entries[0].page_number == 25


# ---------------------------------------------------------------------------
# Pass 2 tests
# ---------------------------------------------------------------------------

class TestPass2:
    def test_detects_keyword_ordinal_title(self, keywords, ordinals):
        pages = make_pages([
            {"page": 10, "text": "الباب الأول: في الفعل"},
        ])
        candidates = pass2_keyword_scan(pages, keywords, ordinals, [])
        assert len(candidates) >= 1
        c = candidates[0]
        assert c.keyword_type == "الباب"
        assert c.ordinal == 1
        assert c.confidence == "high"

    def test_detects_standalone_keyword(self, keywords, ordinals):
        pages = make_pages([
            {"page": 10, "text": "تنبيهات"},
        ])
        candidates = pass2_keyword_scan(pages, keywords, ordinals, [])
        assert len(candidates) >= 1
        assert candidates[0].keyword_type == "تنبيهات"
        assert candidates[0].confidence == "medium"

    def test_rejects_long_line(self, keywords, ordinals):
        """A line starting with a keyword but >120 chars for ordinal patterns should not match 'high'."""
        long_text = "الباب الأول: " + "أ" * 200
        pages = make_pages([{"page": 10, "text": long_text}])
        candidates = pass2_keyword_scan(pages, keywords, ordinals, [])
        # Should either reject or match at lower confidence
        high_conf = [c for c in candidates if c.confidence == "high"]
        assert len(high_conf) == 0

    def test_rejects_toc_entry(self, keywords, ordinals):
        """TOC-style lines with dot-leaders must be rejected."""
        pages = make_pages([
            {"page": 10, "text": "الباب الأول.......١٧"},
        ])
        candidates = pass2_keyword_scan(pages, keywords, ordinals, [])
        assert len(candidates) == 0

    def test_rejects_ellipsis_toc(self, keywords, ordinals):
        """TOC lines with … (U+2026) must be rejected."""
        pages = make_pages([
            {"page": 10, "text": "التقسيم الرابع … ٧٧"},
        ])
        candidates = pass2_keyword_scan(pages, keywords, ordinals, [])
        assert len(candidates) == 0

    def test_dedup_with_pass1(self, keywords, ordinals):
        """Pass 2 should not return headings already found by Pass 1."""
        pages = make_pages([
            {"page": 10, "text": "الباب الأول: في الفعل"},
        ])
        pass1 = [HeadingCandidate(
            title="الباب الأول: في الفعل", seq_index=0,
            page_number_int=10, volume=1, page_hint="ص:١٠",
            detection_method="html_tagged", confidence="confirmed",
        )]
        candidates = pass2_keyword_scan(pages, keywords, ordinals, pass1)
        assert len(candidates) == 0

    def test_detects_inline_heading(self, keywords, ordinals):
        """Inline headings (keyword - content) should be detected."""
        pages = make_pages([
            {"page": 23, "text": "تنبيه - يتصرف الماضى باعتبار اتصال ضمير الرفع"},
        ])
        candidates = pass2_keyword_scan(pages, keywords, ordinals, [])
        assert len(candidates) >= 1
        c = candidates[0]
        assert c.inline_heading is True
        assert c.heading_text_boundary is not None
        # Title should be just the keyword part, not the full line
        assert "يتصرف" not in c.title

    def test_keyword_في_pattern(self, keywords, ordinals):
        """KEYWORD في TITLE pattern."""
        pages = make_pages([
            {"page": 10, "text": "فصل في معاني صيغ الزوائد"},
        ])
        candidates = pass2_keyword_scan(pages, keywords, ordinals, [])
        assert len(candidates) >= 1
        assert candidates[0].confidence == "medium"

    def test_multiple_headings_on_different_pages(self, keywords, ordinals):
        pages = make_pages([
            {"page": 10, "text": "الباب الأول: في الفعل\nمحتوى الباب"},
            {"page": 11, "text": "المبحث الأول في الاسم"},
            {"page": 12, "text": "تنبيه\nمحتوى التنبيه"},
        ])
        candidates = pass2_keyword_scan(pages, keywords, ordinals, [])
        assert len(candidates) == 3

    def test_no_keyword_no_match(self, keywords, ordinals):
        """Plain text without keywords should produce no candidates."""
        pages = make_pages([
            {"page": 10, "text": "هذا نص عادي لا يحتوي على عناوين هيكلية"},
        ])
        candidates = pass2_keyword_scan(pages, keywords, ordinals, [])
        assert len(candidates) == 0

    def test_citation_pattern_rejection(self, keywords, ordinals):
        """Keywords preceded by citation phrases on the previous line should be skipped."""
        pages = make_pages([
            {"page": 10, "text": "وقد ذكر في\nباب الفعل أن الأمر كذلك"},
        ])
        # The keyword "باب" starts a line but the previous line ends with "ذكر في"
        candidates = pass2_keyword_scan(pages, keywords, ordinals, [])
        # Should ideally reject this, but it depends on the previous line context check
        # The citation check looks at previous line's tail
        # "ذكر في" is in CITATION_PREFIXES
        assert len(candidates) == 0


# ---------------------------------------------------------------------------
# Integration test placeholder
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_pipeline_synthetic(self, keywords, ordinals):
        """Run Pass 1 + Pass 2 on synthetic data and verify consistency."""
        html = make_shamela_html([
            {"page_number": 1, "headings": ["الباب الأول"], "content": "محتوى"},
            {"page_number": 2, "headings": [], "content": "تنبيه\nمحتوى التنبيه"},
            {"page_number": 3, "headings": ["المبحث الثاني"], "content": "محتوى"},
        ])

        with tempfile.NamedTemporaryFile(mode="w", suffix=".htm", delete=False, encoding="utf-8") as f:
            f.write(html)
            html_path = f.name

        try:
            pages = make_pages([
                {"page": 1, "text": "الباب الأول\nمحتوى"},
                {"page": 2, "text": "تنبيه\nمحتوى التنبيه"},
                {"page": 3, "text": "المبحث الثاني\nمحتوى"},
            ])
            idx = build_page_index(pages)

            # Pass 1
            pass1_headings, toc_pages, _ = pass1_extract_html_headings(html_path, idx)
            assert len(pass1_headings) == 2  # الباب and المبحث

            # Pass 2
            pass2_headings = pass2_keyword_scan(pages, keywords, ordinals, pass1_headings)
            assert len(pass2_headings) >= 1  # تنبيه at least

            all_headings = pass1_headings + pass2_headings
            # Should have at least 3 total (الباب + المبحث + تنبيه)
            assert len(all_headings) >= 3

            # All have required fields
            for h in all_headings:
                assert h.title
                assert h.detection_method in ("html_tagged", "keyword_heuristic")
                assert h.confidence in ("confirmed", "high", "medium", "low")
        finally:
            os.unlink(html_path)


# ---------------------------------------------------------------------------
# Keyword type detection tests
# ---------------------------------------------------------------------------

class TestDetectKeywordType:
    def test_detects_bab(self, keywords):
        assert detect_keyword_type_from_title("الباب الأول: في الفعل", keywords) == "الباب"

    def test_detects_fasl(self, keywords):
        assert detect_keyword_type_from_title("فصل في همزة الوصل", keywords) == "فصل"

    def test_detects_mabhath(self, keywords):
        assert detect_keyword_type_from_title("المبحث الأول في حقيقة الخبر", keywords) == "المبحث"

    def test_returns_implicit_for_unknown(self, keywords):
        assert detect_keyword_type_from_title("أنواع الجناس اللفظي", keywords) == "implicit"

    def test_keyword_must_be_at_start(self, keywords):
        assert detect_keyword_type_from_title("في باب الفعل", keywords) == "implicit"


# ---------------------------------------------------------------------------
# Digestibility classification tests
# ---------------------------------------------------------------------------

class TestDigestibility:
    def test_toc_is_non_digestible(self):
        h = HeadingCandidate(
            title="فهرس الموضوعات", seq_index=0, page_number_int=1, volume=1,
            page_hint="ص:١", detection_method="html_tagged", confidence="confirmed",
            keyword_type="فهرس الموضوعات",
        )
        dig, ct = classify_digestibility(h)
        assert dig == "false"
        assert ct == "non_content"

    def test_editor_intro_is_non_digestible(self):
        h = HeadingCandidate(
            title="مقدمة المحقق", seq_index=0, page_number_int=1, volume=1,
            page_hint="ص:١", detection_method="html_tagged", confidence="confirmed",
        )
        dig, ct = classify_digestibility(h)
        assert dig == "false"

    def test_khutba_is_non_digestible(self):
        h = HeadingCandidate(
            title="خطبة الكتاب", seq_index=0, page_number_int=1, volume=1,
            page_hint="ص:١", detection_method="html_tagged", confidence="confirmed",
        )
        dig, ct = classify_digestibility(h)
        assert dig == "false"

    def test_exercise_is_digestible(self):
        h = HeadingCandidate(
            title="تطبيق", seq_index=0, page_number_int=1, volume=1,
            page_hint="ص:١", detection_method="keyword_heuristic", confidence="medium",
            keyword_type="تطبيق",
        )
        dig, ct = classify_digestibility(h)
        assert dig == "true"
        assert ct == "exercise"

    def test_muqaddima_is_uncertain(self):
        h = HeadingCandidate(
            title="مقدمة", seq_index=0, page_number_int=1, volume=1,
            page_hint="ص:١", detection_method="keyword_heuristic", confidence="medium",
        )
        dig, ct = classify_digestibility(h)
        assert dig == "uncertain"

    def test_regular_bab_is_digestible(self):
        h = HeadingCandidate(
            title="الباب الأول: في الفعل", seq_index=0, page_number_int=1, volume=1,
            page_hint="ص:١", detection_method="html_tagged", confidence="confirmed",
            keyword_type="الباب",
        )
        dig, ct = classify_digestibility(h)
        assert dig == "true"
        assert ct == "teaching"


# ---------------------------------------------------------------------------
# Division tree builder tests
# ---------------------------------------------------------------------------

class TestBuildDivisionTree:
    def test_builds_correct_count(self, keywords):
        headings = [
            HeadingCandidate(
                title="الباب الأول", seq_index=0, page_number_int=1, volume=1,
                page_hint="ص:١", detection_method="html_tagged", confidence="confirmed",
            ),
            HeadingCandidate(
                title="المبحث الأول", seq_index=2, page_number_int=3, volume=1,
                page_hint="ص:٣", detection_method="html_tagged", confidence="confirmed",
            ),
        ]
        pages = make_pages([{"page": 1}, {"page": 2}, {"page": 3}, {"page": 4}])
        divs = build_division_tree(headings, pages, "test_book", keywords=keywords)
        assert len(divs) == 2

    def test_page_ranges_are_contiguous(self, keywords):
        headings = [
            HeadingCandidate(
                title="باب أ", seq_index=0, page_number_int=1, volume=1,
                page_hint="ص:١", detection_method="html_tagged", confidence="confirmed",
            ),
            HeadingCandidate(
                title="باب ب", seq_index=3, page_number_int=4, volume=1,
                page_hint="ص:٤", detection_method="html_tagged", confidence="confirmed",
            ),
        ]
        pages = make_pages([{"page": i} for i in range(1, 8)])
        divs = build_division_tree(headings, pages, "test", keywords=keywords)
        # First division: 0 to 2 (just before second heading)
        assert divs[0].start_seq_index == 0
        assert divs[0].end_seq_index == 2
        # Second division: 3 to end (6)
        assert divs[1].start_seq_index == 3
        assert divs[1].end_seq_index == 6

    def test_deduplicates_same_title_same_page(self, keywords):
        headings = [
            HeadingCandidate(
                title="الباب الأول", seq_index=0, page_number_int=1, volume=1,
                page_hint="ص:١", detection_method="html_tagged", confidence="confirmed",
            ),
            HeadingCandidate(
                title="الباب الأول", seq_index=0, page_number_int=1, volume=1,
                page_hint="ص:١", detection_method="keyword_heuristic", confidence="high",
            ),
        ]
        pages = make_pages([{"page": 1}, {"page": 2}])
        divs = build_division_tree(headings, pages, "test", keywords=keywords)
        assert len(divs) == 1

    def test_detects_keyword_type_from_title(self, keywords):
        headings = [
            HeadingCandidate(
                title="الباب الأول: في الفعل", seq_index=0, page_number_int=1, volume=1,
                page_hint="ص:١", detection_method="html_tagged", confidence="confirmed",
                keyword_type=None,  # Pass 1 doesn't set this
            ),
        ]
        pages = make_pages([{"page": 1}, {"page": 2}])
        divs = build_division_tree(headings, pages, "test", keywords=keywords)
        assert divs[0].type == "الباب"


# ---------------------------------------------------------------------------
# Passage constructor tests
# ---------------------------------------------------------------------------

class TestBuildPassages:
    def _make_divisions(self, specs):
        """Helper: create DivisionNode list from simple specs.

        Each spec: (id, type, title, start, end, digestible, content_type)
        """
        divs = []
        for s in specs:
            divs.append(DivisionNode(
                id=s[0], type=s[1], title=s[2], level=1,
                detection_method="html_tagged", confidence="confirmed",
                digestible=s[5], content_type=s[6],
                start_seq_index=s[3], end_seq_index=s[4],
                page_hint_start=f"ص:{s[3]}", page_hint_end=f"ص:{s[4]}",
                parent_id=None, page_count=s[4] - s[3] + 1,
            ))
        return divs

    def test_creates_passages_for_digestible_leaves(self):
        divs = self._make_divisions([
            ("d1", "باب", "باب أ", 0, 5, "true", "teaching"),
            ("d2", "باب", "باب ب", 6, 10, "true", "teaching"),
        ])
        passages = build_passages(divs, "test")
        assert len(passages) == 2
        assert passages[0].passage_id == "P001"
        assert passages[1].passage_id == "P002"

    def test_skips_non_digestible(self):
        divs = self._make_divisions([
            ("d1", "فهرس", "فهرس", 0, 2, "false", "non_content"),
            ("d2", "باب", "باب أ", 3, 10, "true", "teaching"),
        ])
        passages = build_passages(divs, "test")
        assert len(passages) == 1
        assert passages[0].title == "باب أ"

    def test_includes_uncertain_with_flag(self):
        divs = self._make_divisions([
            ("d1", "مقدمة", "مقدمة", 0, 5, "uncertain", None),
        ])
        passages = build_passages(divs, "test")
        assert len(passages) == 1
        assert "uncertain_content_type" in passages[0].review_flags

    def test_flags_long_passages(self):
        divs = self._make_divisions([
            ("d1", "باب", "باب طويل", 0, 24, "true", "teaching"),
        ])
        passages = build_passages(divs, "test")
        assert len(passages) == 1
        assert "long_passage" in passages[0].review_flags
        assert passages[0].sizing_action == "flagged_long"

    def test_links_predecessor_successor(self):
        divs = self._make_divisions([
            ("d1", "باب", "باب أ", 0, 3, "true", "teaching"),
            ("d2", "باب", "باب ب", 4, 7, "true", "teaching"),
            ("d3", "باب", "باب ج", 8, 11, "true", "teaching"),
        ])
        passages = build_passages(divs, "test")
        assert passages[0].predecessor_passage_id is None
        assert passages[0].successor_passage_id == "P002"
        assert passages[1].predecessor_passage_id == "P001"
        assert passages[1].successor_passage_id == "P003"
        assert passages[2].predecessor_passage_id == "P002"
        assert passages[2].successor_passage_id is None

    def test_science_id_inherited(self):
        divs = self._make_divisions([
            ("d1", "باب", "باب أ", 0, 5, "true", "teaching"),
        ])
        passages = build_passages(divs, "test", science_id="balagha")
        assert passages[0].science_id == "balagha"

    def test_same_page_cluster_not_separate_passages(self):
        """Regression: same-page headings must not create overlapping passages."""
        divs = self._make_divisions([
            ("d1", "باب", "باب أ", 5, 9, "true", "teaching"),
            ("d2", "المبحث", "المبحث الأول", 5, 5, "true", "teaching"),
            ("d3", "المبحث", "المبحث الثاني", 5, 5, "true", "teaching"),
        ])
        # Simulate same_page_cluster flags (as build_division_tree would set them)
        divs[1].review_flags = ["same_page_cluster"]
        divs[2].review_flags = ["same_page_cluster"]

        passages = build_passages(divs, "test")
        # Only 1 passage (the page-owning division), not 3
        assert len(passages) == 1
        assert passages[0].title == "باب أ"
        # Cluster siblings absorbed into division_ids
        assert "d2" in passages[0].division_ids
        assert "d3" in passages[0].division_ids

    def test_no_passage_overlaps(self):
        """Regression: passages must never have overlapping page ranges."""
        divs = self._make_divisions([
            ("d1", "باب", "باب أ", 0, 4, "true", "teaching"),
            ("d2", "باب", "باب ب", 5, 9, "true", "teaching"),
            ("d3", "باب", "باب ج", 10, 14, "true", "teaching"),
        ])
        passages = build_passages(divs, "test")
        for i in range(len(passages) - 1):
            assert passages[i].end_seq_index < passages[i + 1].start_seq_index, \
                f"Overlap: P{i+1} end={passages[i].end_seq_index} >= P{i+2} start={passages[i+1].start_seq_index}"

    def test_volume_derived_from_pages(self):
        """Regression: volume field should be derived from pages, not None."""
        divs = self._make_divisions([
            ("d1", "باب", "باب أ", 0, 5, "true", "teaching"),
        ])
        pages = [PageRecord(seq_index=i, page_number_int=i+1, volume=2,
                            matn_text="", page_hint=f"p{i}") for i in range(10)]
        passages = build_passages(divs, "test", pages=pages)
        assert passages[0].volume == 2


# ---------------------------------------------------------------------------
# Regression Tests: Critical Bug Fixes
# ---------------------------------------------------------------------------

class TestRegressionDocumentOrder:
    """Regression tests for document-order preservation (was sort-by-title bug)."""

    def test_same_page_headings_preserve_html_order(self, keywords):
        """When multiple headings share a seq_index, document_position determines order."""
        pages = [PageRecord(seq_index=i, page_number_int=i+1, volume=1,
                            matn_text="", page_hint=f"p{i}") for i in range(10)]
        headings = [
            HeadingCandidate(title="المبحث الأول", seq_index=5, page_number_int=6, volume=1,
                             page_hint="p5", detection_method="html_tagged", confidence="confirmed",
                             document_position=0),
            HeadingCandidate(title="الباب الأول", seq_index=5, page_number_int=6, volume=1,
                             page_hint="p5", detection_method="html_tagged", confidence="confirmed",
                             document_position=1),
        ]
        divs = build_division_tree(headings, pages, "test", keywords=keywords)
        # المبحث should come first (doc_position=0), not الباب (which sorts earlier alphabetically)
        assert divs[0].title == "المبحث الأول"
        assert divs[1].title == "الباب الأول"


class TestRegressionUnmappedHeadings:
    """Regression tests for unmapped heading detection (was ghost-heading bug)."""

    def test_unmapped_headings_dropped(self, keywords):
        """Headings with page_mapped=False must be filtered out of the division tree."""
        pages = [PageRecord(seq_index=i, page_number_int=i+1, volume=1,
                            matn_text="", page_hint=f"p{i}") for i in range(5)]
        headings = [
            HeadingCandidate(title="باب أ", seq_index=0, page_number_int=1, volume=1,
                             page_hint="p0", detection_method="html_tagged", confidence="confirmed",
                             page_mapped=True, document_position=0),
            HeadingCandidate(title="باب ب", seq_index=-1, page_number_int=999, volume=1,
                             page_hint="p999", detection_method="html_tagged", confidence="confirmed",
                             page_mapped=False, document_position=1),
        ]
        divs = build_division_tree(headings, pages, "test", keywords=keywords)
        assert len(divs) == 1
        assert divs[0].title == "باب أ"


class TestRegressionSamePageCluster:
    """Regression tests for same-page clustering (was overlapping passages bug)."""

    def test_same_page_cluster_flagged(self, keywords):
        """Multiple headings on same page: first is primary, rest get same_page_cluster flag."""
        pages = [PageRecord(seq_index=i, page_number_int=i+1, volume=1,
                            matn_text="", page_hint=f"p{i}") for i in range(10)]
        headings = [
            HeadingCandidate(title="باب أ", seq_index=5, page_number_int=6, volume=1,
                             page_hint="p5", detection_method="html_tagged", confidence="confirmed",
                             document_position=0),
            HeadingCandidate(title="المبحث الأول", seq_index=5, page_number_int=6, volume=1,
                             page_hint="p5", detection_method="html_tagged", confidence="confirmed",
                             document_position=1),
            HeadingCandidate(title="المبحث الثاني", seq_index=5, page_number_int=6, volume=1,
                             page_hint="p5", detection_method="html_tagged", confidence="confirmed",
                             document_position=2),
        ]
        divs = build_division_tree(headings, pages, "test", keywords=keywords)
        assert len(divs) == 3
        assert "same_page_cluster" not in divs[0].review_flags  # First on page
        assert "same_page_cluster" in divs[1].review_flags
        assert "same_page_cluster" in divs[2].review_flags

    def test_passages_from_clustered_divisions_no_overlap(self, keywords):
        """Same-page clusters must NOT produce overlapping passages."""
        pages = [PageRecord(seq_index=i, page_number_int=i+1, volume=1,
                            matn_text="", page_hint=f"p{i}") for i in range(10)]
        headings = [
            HeadingCandidate(title="باب أ", seq_index=5, page_number_int=6, volume=1,
                             page_hint="p5", detection_method="html_tagged", confidence="confirmed",
                             document_position=0),
            HeadingCandidate(title="المبحث الأول", seq_index=5, page_number_int=6, volume=1,
                             page_hint="p5", detection_method="html_tagged", confidence="confirmed",
                             document_position=1),
            HeadingCandidate(title="باب ب", seq_index=8, page_number_int=9, volume=1,
                             page_hint="p8", detection_method="html_tagged", confidence="confirmed",
                             document_position=2),
        ]
        divs = build_division_tree(headings, pages, "test", keywords=keywords)
        passages = build_passages(divs, "test")
        # Should be 2 passages (باب أ absorbs المبحث, and باب ب)
        assert len(passages) == 2
        # No overlaps
        assert passages[0].end_seq_index < passages[1].start_seq_index


class TestRegressionEllipsisFilter:
    """Regression tests for C2 ellipsis filter (was false-positive rejection)."""

    def test_legitimate_ellipsis_not_rejected(self, keywords, ordinals):
        """Lines with ellipsis as text omission should NOT be rejected by C2."""
        pages = [PageRecord(seq_index=0, page_number_int=1, volume=1,
                            matn_text="تنبيه: قد علمت … أن الاسم", page_hint="p0")]
        candidates = pass2_keyword_scan(pages, keywords, ordinals, [])
        # Should match: "تنبيه" keyword with inline pattern
        assert len(candidates) > 0
        assert candidates[0].keyword_type == "تنبيه"

    def test_toc_ellipsis_still_rejected(self, keywords, ordinals):
        """Lines with ellipsis followed by page number (TOC pattern) should still be rejected."""
        pages = [PageRecord(seq_index=0, page_number_int=1, volume=1,
                            matn_text="باب الأول … ٧٧", page_hint="p0")]
        candidates = pass2_keyword_scan(pages, keywords, ordinals, [])
        assert len(candidates) == 0


class TestRegressionTOCDetection:
    """Regression tests for TOC detection (was substring false-positive)."""

    def test_toc_heading_exact_match(self):
        """TOC detection should use exact match, not substring."""
        # "فهرس المصطلحات" contains "فهرس" but is NOT a TOC heading
        html = """<html><body>
        <div class='PageText'><p>metadata page</p></div>
        <div class='PageText'>
            <span class='PageNumber'>(ص: ١)</span>
            <span class="title">فهرس المصطلحات اللغوية</span>
        </div>
        </body></html>"""
        idx = {(1, 1): PageRecord(seq_index=0, page_number_int=1, volume=1,
                                   matn_text="", page_hint="p0")}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".htm", delete=False, encoding="utf-8") as f:
            f.write(html)
            path = f.name
        try:
            headings, toc_pages, _ = pass1_extract_html_headings(path, idx)
            # Should NOT be detected as TOC (it's a glossary heading, not a table of contents)
            assert len(toc_pages) == 0
            assert headings[0].notes is None  # Not marked as TOC
        finally:
            os.unlink(path)

    def test_toc_heading_real_toc(self):
        """Real TOC headings should still be detected."""
        html = """<html><body>
        <div class='PageText'><p>metadata page</p></div>
        <div class='PageText'>
            <span class='PageNumber'>(ص: ١)</span>
            <span class="title">فهرس الموضوعات</span>
        </div>
        </body></html>"""
        idx = {(1, 1): PageRecord(seq_index=0, page_number_int=1, volume=1,
                                   matn_text="", page_hint="p0")}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".htm", delete=False, encoding="utf-8") as f:
            f.write(html)
            path = f.name
        try:
            headings, toc_pages, _ = pass1_extract_html_headings(path, idx)
            assert len(toc_pages) == 1
            assert headings[0].notes == "TOC heading"
        finally:
            os.unlink(path)


class TestRegressionPass1HtmlCount:
    """Regression tests for HTML page count return value."""

    def test_html_page_count_returned(self):
        """pass1 should return the total HTML content page count."""
        html = """<html><body>
        <div class='PageText'><p>metadata page</p></div>
        <div class='PageText'><span class='PageNumber'>(ص: ١)</span><p>page 1</p></div>
        <div class='PageText'><span class='PageNumber'>(ص: ٢)</span><p>page 2</p></div>
        <div class='PageText'><span class='PageNumber'>(ص: ٣)</span><p>page 3</p></div>
        </body></html>"""
        idx = {(1, 1): PageRecord(seq_index=0, page_number_int=1, volume=1,
                                   matn_text="", page_hint="p0"),
               (1, 2): PageRecord(seq_index=1, page_number_int=2, volume=1,
                                   matn_text="", page_hint="p1")}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".htm", delete=False, encoding="utf-8") as f:
            f.write(html)
            path = f.name
        try:
            headings, toc_pages, html_page_count = pass1_extract_html_headings(path, idx)
            assert html_page_count == 3  # 3 content pages in HTML

            # Page 3 is NOT in the idx, so headings on it would be unmapped
            # This is the pre-flight check signal
        finally:
            os.unlink(path)

    def test_unmapped_page_flagged(self):
        """Headings on pages not in JSONL should have page_mapped=False."""
        html = """<html><body>
        <div class='PageText'><p>metadata page</p></div>
        <div class='PageText'>
            <span class='PageNumber'>(ص: ١)</span>
            <span class="title">باب أ</span>
        </div>
        <div class='PageText'>
            <span class='PageNumber'>(ص: ٩٩)</span>
            <span class="title">باب ب</span>
        </div>
        </body></html>"""
        idx = {(1, 1): PageRecord(seq_index=0, page_number_int=1, volume=1,
                                   matn_text="", page_hint="p0")}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".htm", delete=False, encoding="utf-8") as f:
            f.write(html)
            path = f.name
        try:
            headings, _, _ = pass1_extract_html_headings(path, idx)
            assert len(headings) == 2
            assert headings[0].page_mapped is True
            assert headings[0].title == "باب أ"
            assert headings[1].page_mapped is False
            assert headings[1].title == "باب ب"
        finally:
            os.unlink(path)


class TestRegressionExerciseClassification:
    """Regression: exercises must be detected even when keyword_type is None (Pass 1 headings)."""

    def test_exercise_detected_by_title_when_keyword_type_none(self):
        """Pass 1 headings have keyword_type=None; exercise detection must use title."""
        h = HeadingCandidate(
            title="تطبيق على باب الفعل", seq_index=0, page_number_int=1, volume=1,
            page_hint="p0", detection_method="html_tagged", confidence="confirmed",
            keyword_type=None,  # Pass 1 doesn't set this
        )
        dig, ct = classify_digestibility(h)
        assert ct == "exercise", f"Expected exercise, got {ct}"
        assert dig == "true"

    def test_exercise_detected_by_keyword_type(self):
        """Pass 2 headings have keyword_type set; should also work."""
        h = HeadingCandidate(
            title="تطبيق على باب الفعل", seq_index=0, page_number_int=1, volume=1,
            page_hint="p0", detection_method="keyword_heuristic", confidence="medium",
            keyword_type="تطبيق",
        )
        dig, ct = classify_digestibility(h)
        assert ct == "exercise"

    def test_non_exercise_not_misclassified(self):
        """A title starting with a non-exercise word should not be classified as exercise."""
        h = HeadingCandidate(
            title="باب التطبيقات", seq_index=0, page_number_int=1, volume=1,
            page_hint="p0", detection_method="html_tagged", confidence="confirmed",
            keyword_type=None,
        )
        dig, ct = classify_digestibility(h)
        assert ct == "teaching", f"Expected teaching, got {ct}"


class TestRegressionMergeCondition:
    """Regression: merge condition is intentionally inactive in flat tree."""

    def test_single_page_divisions_not_merged_in_flat_tree(self):
        """In the flat tree (pre-LLM), 1-page divisions should NOT be merged."""
        divs = []
        for i in range(5):
            divs.append(DivisionNode(
                id=f"d{i}", type="مبحث", title=f"مبحث {i}", level=1,
                detection_method="html_tagged", confidence="confirmed",
                digestible="true", content_type="teaching",
                start_seq_index=i, end_seq_index=i,
                page_hint_start=f"p{i}", page_hint_end=f"p{i}",
                parent_id=None, page_count=1,
            ))
        passages = build_passages(divs, "test")
        # Each 1-page division should be its own passage — not merged
        assert len(passages) == 5, f"Expected 5 passages, got {len(passages)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
