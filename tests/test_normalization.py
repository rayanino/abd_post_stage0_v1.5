#!/usr/bin/env python3
"""
Tests for Stage 1: Normalization (tools/normalize_shamela.py)

Run: pytest tests/test_normalization.py -v

Categories:
  - Unit tests for each transformation rule (§4 of spec)
  - Gold sample validation (jawahir pages 19–40)
  - Multi-volume support
  - Output format compliance
  - Stage 0 integration
  - Corpus-wide smoke tests (Other Books)
"""

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure tools/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from normalize_shamela import (
    FootnoteRecord,
    NormalizationReport,
    PageRecord,
    arabic_to_int,
    clean_verse_markers,
    detect_image_only_page,
    detect_verse,
    discover_volume_files,
    extract_table_text,
    normalize_book,
    normalize_multivolume,
    normalize_page,
    normalize_whitespace,
    page_to_jsonl_record,
    parse_footnotes,
    replace_tables_with_text,
    strip_fn_refs_from_matn,
    strip_tags,
    aggregate_reports,
    load_intake_metadata,
    resolve_source_paths,
)

# ─── Repo paths ────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLD_SAMPLES_DIR = REPO_ROOT / "1_normalization" / "gold_samples"
GOLD_FULL_JSONL = GOLD_SAMPLES_DIR / "jawahir_normalized_full.jsonl"
GOLD_JSONL = GOLD_SAMPLES_DIR / "jawahir_normalized.jsonl"
GOLD_REPORT = GOLD_SAMPLES_DIR / "jawahir_normalization_report.json"
BOOKS_DIR = REPO_ROOT / "books"
OTHER_BOOKS = BOOKS_DIR / "Other Books"
HAS_OTHER_BOOKS = OTHER_BOOKS.exists()


# ─── HTML helpers ──────────────────────────────────────────────────────────

def make_page_html(matn: str, page_num_arabic: str = "١", footnotes: str = "",
                   title: str = "Test Book") -> str:
    """Build a minimal Shamela PageText block for testing."""
    fn_section = ""
    if footnotes:
        fn_section = f"<hr width='95' align='right'><div class='footnote'>{footnotes}</div>"
    return (
        f"<div class='PageText'>"
        f"<div class='PageHead'>"
        f"<span class='PartName'>{title}</span>"
        f"<span class='PageNumber'>(ص: {page_num_arabic})</span>"
        f"<hr/>"
        f"</div>"
        f"{matn}"
        f"{fn_section}"
        f"</div>"
    )


def make_book_html(*page_blocks: str) -> str:
    """Wrap page blocks in a Shamela HTML document."""
    return (
        "<!DOCTYPE html><html lang='ar' dir='rtl'>"
        "<head><meta content='text/html; charset=UTF-8' http-equiv='Content-Type'></head>"
        "<body><div class='Main'>"
        + "".join(page_blocks) +
        "</div></body></html>"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Unit Tests: arabic_to_int
# ═══════════════════════════════════════════════════════════════════════════

class TestArabicToInt:
    def test_single_digit(self):
        assert arabic_to_int("٥") == 5

    def test_double_digit(self):
        assert arabic_to_int("٢٠") == 20

    def test_triple_digit(self):
        assert arabic_to_int("٣٠٨") == 308

    def test_zero(self):
        assert arabic_to_int("٠") == 0

    def test_all_digits(self):
        assert arabic_to_int("٠١٢٣٤٥٦٧٨٩") == 123456789

    def test_large_number(self):
        assert arabic_to_int("١٠٢٤") == 1024


# ═══════════════════════════════════════════════════════════════════════════
# Unit Tests: strip_tags (Rule T1–T4)
# ═══════════════════════════════════════════════════════════════════════════

class TestStripTags:
    """Test HTML tag stripping per spec rules T1–T4."""

    def test_br_to_newline(self):
        """T1: <br> → newline."""
        assert "\n" in strip_tags("hello<br>world")

    def test_br_self_closing(self):
        """T1: <br/> → newline."""
        assert "\n" in strip_tags("hello<br/>world")

    def test_closing_p_to_newline(self):
        """T1: </p> → newline."""
        assert "\n" in strip_tags("hello</p>world")

    def test_font_color_unwrapped(self):
        """T2: font tags unwrapped, content preserved."""
        assert strip_tags("<font color=#be0000>1.</font>") == "1."

    def test_font_color_nested(self):
        """T2: font unwrap with surrounding text."""
        result = strip_tags("text <font color=#be0000>(2)</font> more")
        assert "(2)" in result
        assert "<font" not in result

    def test_other_tags_removed(self):
        """T3: all other tags stripped."""
        assert strip_tags("<span class='title'>hello</span>") == "hello"
        assert strip_tags("<div class='test'>content</div>") == "content"

    def test_html_entities_decoded(self):
        """T4: HTML entities decoded."""
        assert strip_tags("&amp;") == "&"
        assert strip_tags("&lt;") == "<"
        assert strip_tags("&gt;") == ">"
        # &nbsp; decodes to \xa0 (non-breaking space); the NBSP→space
        # normalization happens in normalize_whitespace, not strip_tags
        assert strip_tags("&nbsp;") == "\u00a0"

    def test_nbsp_pipeline(self):
        """T4 + W2: &nbsp; → NBSP via strip_tags, then → space via normalize_whitespace."""
        result = normalize_whitespace(strip_tags("hello&nbsp;world"))
        assert result == "hello world"

    def test_script_removed(self):
        result = strip_tags("before<script>var x=1;</script>after")
        assert "var" not in result
        assert "beforeafter" in result.replace(" ", "").replace("\n", "")

    def test_preserves_arabic_text(self):
        result = strip_tags("<span>بسم الله الرحمن الرحيم</span>")
        assert "بسم الله الرحمن الرحيم" in result


# ═══════════════════════════════════════════════════════════════════════════
# Unit Tests: normalize_whitespace (Rules W1–W5)
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalizeWhitespace:
    def test_crlf_to_lf(self):
        """W1: \\r\\n → \\n."""
        assert "\r\n" not in normalize_whitespace("hello\r\nworld")
        assert "\n" in normalize_whitespace("hello\r\nworld")

    def test_cr_to_lf(self):
        """W1: \\r → \\n."""
        assert "\r" not in normalize_whitespace("hello\rworld")

    def test_nbsp_to_space(self):
        """W2: NBSP → regular space."""
        assert "\u00a0" not in normalize_whitespace("hello\u00a0world")
        assert " " in normalize_whitespace("hello\u00a0world")

    def test_collapse_multiple_spaces(self):
        """W3: Multiple spaces → single space."""
        assert "hello world" in normalize_whitespace("hello    world")

    def test_trim_lines(self):
        """W4: Leading/trailing whitespace per line removed."""
        result = normalize_whitespace("  hello  \n  world  ")
        lines = result.split("\n")
        for line in lines:
            assert line == line.strip()

    def test_collapse_blank_lines(self):
        """W5: 3+ blank lines → 1 blank line."""
        result = normalize_whitespace("hello\n\n\n\n\nworld")
        assert "\n\n\n" not in result
        assert "hello\n\nworld" == result


# ═══════════════════════════════════════════════════════════════════════════
# Unit Tests: footnote reference stripping (Rules F1–F3)
# ═══════════════════════════════════════════════════════════════════════════

class TestStripFnRefs:
    def test_strip_known_ref(self):
        """F1: Strip (N) when N is a known footnote number."""
        text, refs = strip_fn_refs_from_matn("text (1) more", known_fn_numbers={1})
        assert "(1)" not in text
        assert 1 in refs

    def test_preserve_unknown_ref(self):
        """F1: Preserve (N) when N is NOT a known footnote number."""
        text, refs = strip_fn_refs_from_matn("exercise (1) text", known_fn_numbers={2})
        assert "(1)" in text
        assert 1 not in refs

    def test_quran_parentheses_preserved(self):
        """F2: Arabic parenthetical text never stripped."""
        text, refs = strip_fn_refs_from_matn(
            "(وأخي هارون هو أفصح مِنِّي لساناً)",
            known_fn_numbers={1}
        )
        assert "وأخي هارون" in text

    def test_multiple_refs(self):
        """F1: Multiple refs stripped correctly."""
        text, refs = strip_fn_refs_from_matn(
            "first (1) second (2) third",
            known_fn_numbers={1, 2}
        )
        assert "(1)" not in text
        assert "(2)" not in text
        assert sorted(refs) == [1, 2]

    def test_no_double_spaces(self):
        """F3: Double spaces collapsed after stripping."""
        text, _ = strip_fn_refs_from_matn("hello (1)  world", known_fn_numbers={1})
        assert "  " not in text

    def test_none_fn_numbers_strips_all(self):
        """When known_fn_numbers is None, strip all digit-only parens."""
        text, refs = strip_fn_refs_from_matn("text (1) more (2) end", known_fn_numbers=None)
        assert "(1)" not in text
        assert "(2)" not in text

    def test_ref_before_colon(self):
        """Corpus pattern: (N): colon follows ref — must be stripped."""
        text, refs = strip_fn_refs_from_matn("قال ابن حجر (4): «وسمع", known_fn_numbers={4})
        assert "(4)" not in text
        assert 4 in refs
        assert ": «وسمع" in text

    def test_ref_before_guillemet(self):
        """Corpus pattern: (N)» guillemet follows ref — must be stripped."""
        text, refs = strip_fn_refs_from_matn("النص (2)» ثم", known_fn_numbers={2})
        assert "(2)" not in text
        assert 2 in refs

    def test_consecutive_refs(self):
        """Corpus pattern: (N)(M) consecutive refs — both stripped."""
        text, refs = strip_fn_refs_from_matn("text (4)(5). end", known_fn_numbers={4, 5})
        assert "(4)" not in text
        assert "(5)" not in text
        assert sorted(refs) == [4, 5]

    def test_consecutive_refs_cross_line(self):
        """Corpus pattern: (N)\\n(M) consecutive refs across lines — collapse to space."""
        text, refs = strip_fn_refs_from_matn("end. (10)\n(7) start", known_fn_numbers={7, 10})
        assert "(10)" not in text
        assert "(7)" not in text
        # Should collapse to space, not preserve newline
        assert "\n" not in text
        assert "end. start" in text or "end.  start" in text

    def test_ref_before_arabic_parens_preserves_newline(self):
        """(N)\\n(Arabic text) — ref stripped but newline preserved."""
        text, refs = strip_fn_refs_from_matn(
            "مقدمة (1)\n(في معرفة الفصاحة والبلاغة)",
            known_fn_numbers={1}
        )
        assert "(1)" not in text
        assert 1 in refs
        # Newline must be preserved because (في...) is not a footnote ref
        assert "\n" in text
        assert "(في معرفة" in text

    def test_ref_preserves_space_before_detached_punctuation(self):
        """(N) : → space preserved before colon."""
        text, refs = strip_fn_refs_from_matn(
            "التكرار» (2) : كون اللفظ", known_fn_numbers={2}
        )
        assert "(2)" not in text
        # Space before colon preserved
        assert " : كون" in text or ": كون" in text

    def test_ref_before_question_mark(self):
        """Corpus pattern: (N)؟ question mark follows."""
        text, refs = strip_fn_refs_from_matn("ما هو (3)؟ نعم", known_fn_numbers={3})
        assert "(3)" not in text
        assert 3 in refs


# ═══════════════════════════════════════════════════════════════════════════
# Unit Tests: verse handling (Rules V1–V3)
# ═══════════════════════════════════════════════════════════════════════════

class TestVerseHandling:
    def test_star_markers_stripped(self):
        """V1: Asterisk verse markers removed."""
        assert clean_verse_markers("* تركت ناقتي *") == "تركت ناقتي"

    def test_hemistich_detected(self):
        """V2: Hemistich separator triggers has_verse."""
        assert detect_verse("first hemistich … second hemistich") is True

    def test_star_marker_detected(self):
        """V2: Star markers trigger has_verse."""
        assert detect_verse("* verse text *") is True

    def test_no_verse(self):
        """V2: Plain text has no verse."""
        assert detect_verse("regular prose without poetry") is False

    def test_verse_text_preserved(self):
        """V3: Verse formatting preserved (no reformatting)."""
        text = "first hemistich … second hemistich"
        assert clean_verse_markers(text) == text  # No stars to strip


# ═══════════════════════════════════════════════════════════════════════════
# Unit Tests: footnote parsing (Rules L1–L4)
# ═══════════════════════════════════════════════════════════════════════════

class TestParseFootnotes:
    def test_single_footnote(self):
        """L3: Single footnote parsed correctly."""
        fns = parse_footnotes("(1) This is a footnote.")
        assert len(fns) == 1
        assert fns[0].number == 1
        assert "This is a footnote." in fns[0].text

    def test_multiple_footnotes(self):
        """L3: Multiple footnotes split at (N) boundaries."""
        fns = parse_footnotes("(1) First note.\n(2) Second note.")
        assert len(fns) == 2
        assert fns[0].number == 1
        assert fns[1].number == 2

    def test_dash_separator(self):
        """L4: Footnote with dash separator: (N) ـ text."""
        fns = parse_footnotes("(1) ـ This has a dash.")
        assert len(fns) == 1
        assert "This has a dash." in fns[0].text
        assert "ـ" not in fns[0].text

    def test_no_dash_separator(self):
        """L4: Footnote without dash: (N) text."""
        fns = parse_footnotes("(1) Direct text here.")
        assert len(fns) == 1
        assert "Direct text here." in fns[0].text

    def test_empty_footnote_html(self):
        fns = parse_footnotes("")
        assert fns == []

    def test_whitespace_only(self):
        fns = parse_footnotes("   \n\n  ")
        assert fns == []

    def test_font_color_in_footnotes(self):
        """Footnote numbers wrapped in font color tags."""
        html = "(1) First note.\n<font color=#be0000>(2)</font> Second note."
        fns = parse_footnotes(html)
        assert len(fns) == 2

    def test_subpoints_merged_into_parent(self):
        """Sub-points that restart numbering are merged into parent footnote.
        
        Common in شروح: a footnote contains numbered sub-points (1), (2)
        that look like footnote boundaries but should stay merged.
        Monotonic merge: any (N) where N ≤ last footnote number gets merged.
        """
        fn_text = (
            "(1) Main footnote one.\n"
            "تنبيهات:\n"
            "(1) Sub-point A within fn 1.\n"
            "(2) Sub-point B within fn 1.\n"
            "(2) Main footnote two.\n"
            "(1) Sub-point within fn 2.\n"
            "(2) Another sub-point.\n"
        )
        fns = parse_footnotes(fn_text)
        # Monotonic merge produces 2 footnotes:
        # FN(1): main + sub-point A (sub-point (1) ≤ 1, merged)
        # FN(2): sub-point B + main fn 2 + remaining (all ≤ 2, merged)
        assert len(fns) == 2
        assert fns[0].number == 1
        assert fns[1].number == 2
        # Sub-point A merged into fn 1
        assert "Sub-point A" in fns[0].text
        # Main footnote two content preserved in fn 2
        assert "Main footnote two" in fns[1].text
        # All content preserved (no text lost)
        full_text = fns[0].text + fns[1].text
        assert "Sub-point B" in full_text
        assert "Another sub-point" in full_text

    def test_strictly_increasing_footnotes_unchanged(self):
        """Normal sequential footnotes are not affected by merge logic."""
        fn_text = "(1) First.\n(2) Second.\n(3) Third."
        fns = parse_footnotes(fn_text)
        assert len(fns) == 3
        assert [fn.number for fn in fns] == [1, 2, 3]


# ═══════════════════════════════════════════════════════════════════════════
# Unit Tests: table extraction (Rules TAB1–TAB3)
# ═══════════════════════════════════════════════════════════════════════════

class TestTableExtraction:
    def test_simple_table(self):
        """TAB1–TAB2: Simple 2x2 table extracted correctly."""
        html = "<table dir=rtl><tr><th>Header1</th><th>Header2</th></tr><tr><td>A</td><td>B</td></tr></table>"
        text = extract_table_text(html)
        assert "Header1" in text
        assert "Header2" in text
        assert "A" in text
        assert "B" in text

    def test_table_replacement(self):
        """TAB3: Table replaced in matn HTML."""
        html = "before text<table dir=rtl><tr><td>Cell</td></tr></table>after text"
        result, count = replace_tables_with_text(html)
        assert count == 1
        assert "Cell" in result
        assert "<table" not in result

    def test_multiple_tables(self):
        html = "<table><tr><td>T1</td></tr></table>gap<table><tr><td>T2</td></tr></table>"
        result, count = replace_tables_with_text(html)
        assert count == 2


# ═══════════════════════════════════════════════════════════════════════════
# Unit Tests: image-only page detection (Rules IMG1–IMG2)
# ═══════════════════════════════════════════════════════════════════════════

class TestImageOnlyDetection:
    def test_image_only_page(self):
        """IMG1: Page with only an image → image_only."""
        html = (
            "<div class='PageHead'><span class='PartName'>Book</span>"
            "<span class='PageNumber'>(ص: ٥)</span><hr/></div>"
            "<img src='data:image/jpg;base64,abc123'>"
        )
        assert detect_image_only_page(html) is True

    def test_text_page_no_image(self):
        html = (
            "<div class='PageHead'><span class='PartName'>Book</span>"
            "<span class='PageNumber'>(ص: ٥)</span><hr/></div>"
            "This is normal text content."
        )
        assert detect_image_only_page(html) is False

    def test_mixed_text_and_image(self):
        """IMG2: Page with text + image → not image_only."""
        html = (
            "<div class='PageHead'><span class='PartName'>Book</span>"
            "<span class='PageNumber'>(ص: ٥)</span><hr/></div>"
            "Significant text content here that is more than ten chars."
            "<img src='data:image/jpg;base64,abc123'>"
        )
        assert detect_image_only_page(html) is False


# ═══════════════════════════════════════════════════════════════════════════
# Unit Tests: normalize_page (integrated page normalization)
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalizePage:
    def test_basic_page(self):
        """Minimal page normalization."""
        html = make_page_html("Hello world</p>Second line", page_num_arabic="١")
        page = normalize_page(html)
        assert page is not None
        assert page.page_number_int == 1
        assert page.page_number_arabic == "١"
        assert "Hello world" in page.matn_text
        assert "Second line" in page.matn_text
        assert page.volume == 1

    def test_header_removed(self):
        """H1: Running header stripped from output."""
        html = make_page_html("Content text", title="الكتاب")
        page = normalize_page(html)
        assert "الكتاب" not in page.matn_text

    def test_page_number_extracted(self):
        """P2: Page number correctly extracted from Arabic-Indic digits."""
        html = make_page_html("text", page_num_arabic="٢٥")
        page = normalize_page(html)
        assert page.page_number_int == 25
        assert page.page_number_arabic == "٢٥"

    def test_no_page_number_returns_none(self):
        """P2: Pages without page numbers are skipped."""
        html = "<div class='PageText'><div class='PageHead'><span class='PartName'>Book</span><hr/></div>content</div>"
        page = normalize_page(html)
        assert page is None

    def test_footnotes_separated(self):
        """L1: Footnotes separated from matn at hr separator."""
        html = make_page_html(
            "Matn text (1) here",
            footnotes="(1) A footnote."
        )
        page = normalize_page(html)
        assert "A footnote" not in page.matn_text
        assert len(page.footnotes) == 1
        assert page.footnotes[0].number == 1

    def test_no_footnotes(self):
        """L2: Page without footnotes has empty footnote list."""
        html = make_page_html("Just matn text")
        page = normalize_page(html)
        assert page.footnotes == []

    def test_fn_ref_stripped_from_matn(self):
        """F1: Footnote ref (N) stripped when matching footnote exists."""
        html = make_page_html(
            "Text with reference (1) here.",
            footnotes="(1) The footnote."
        )
        page = normalize_page(html)
        assert "(1)" not in page.matn_text
        assert 1 in page.footnote_ref_numbers

    def test_exercise_number_preserved(self):
        """F1: Exercise (N) preserved when no matching footnote exists."""
        html = make_page_html("Exercise (1) Answer (2) End")
        page = normalize_page(html)
        assert "(1)" in page.matn_text
        assert "(2)" in page.matn_text

    def test_verse_detected(self):
        """V2: Verse presence flagged."""
        html = make_page_html("first … second")
        page = normalize_page(html)
        assert page.has_verse is True

    def test_volume_tagging(self):
        html = make_page_html("text", page_num_arabic="٣")
        page = normalize_page(html, volume=5)
        assert page.volume == 5

    def test_image_only_page(self):
        """IMG1: Image-only page detected and flagged."""
        html = (
            "<div class='PageText'>"
            "<div class='PageHead'>"
            "<span class='PartName'>Book</span>"
            "<span class='PageNumber'>(ص: ٧)</span><hr/></div>"
            "<img src='data:image/jpg;base64,abc123'>"
            "</div>"
        )
        page = normalize_page(html)
        assert page is not None
        assert page.is_image_only is True
        assert page.matn_text == ""
        assert page.footnotes == []

    def test_table_detected(self):
        """TAB3: Table presence flagged."""
        html = make_page_html(
            "Before<table dir=rtl><tr><td>Cell</td></tr></table>After"
        )
        page = normalize_page(html)
        assert page.has_tables is True
        assert "Cell" in page.matn_text

    def test_cross_reference_warnings(self):
        """X1: Orphan footnotes generate warnings."""
        html = make_page_html(
            "Text without any ref markers.",
            footnotes="(1) Orphan footnote."
        )
        page = normalize_page(html)
        assert any("no matching ref" in w for w in page.warnings)


# ═══════════════════════════════════════════════════════════════════════════
# Unit Tests: JSONL output format (spec §3)
# ═══════════════════════════════════════════════════════════════════════════

class TestJSONLFormat:
    """Verify JSONL output matches spec §3 field names and types."""

    @pytest.fixture
    def sample_record(self):
        page = PageRecord(
            volume=1,
            page_number_arabic="٢٠",
            page_number_int=20,
            matn_text="sample text",
            footnotes=[FootnoteRecord(number=1, text="fn text", raw_text="(1) fn text")],
            footnote_ref_numbers=[1],
            has_verse=True,
            is_image_only=False,
            has_tables=False,
            warnings=[],
            raw_matn_html="<p>sample text</p>",
            raw_fn_html="",
        )
        return page_to_jsonl_record(page, "jawahir")

    def test_required_fields_present(self, sample_record):
        """All spec §3 fields must be present."""
        required = {
            "record_type", "book_id", "volume", "page_number_arabic",
            "page_number_int", "content_type", "matn_text", "footnotes",
            "footnote_ref_numbers", "has_verse", "has_table", "warnings",
        }
        assert required.issubset(set(sample_record.keys()))

    def test_record_type_value(self, sample_record):
        assert sample_record["record_type"] == "normalized_page"

    def test_content_type_text(self, sample_record):
        assert sample_record["content_type"] == "text"

    def test_content_type_image_only(self):
        page = PageRecord(
            volume=1, page_number_arabic="٥", page_number_int=5,
            matn_text="", footnotes=[], footnote_ref_numbers=[],
            has_verse=False, is_image_only=True, has_tables=False,
            warnings=[], raw_matn_html="", raw_fn_html="",
        )
        rec = page_to_jsonl_record(page, "test")
        assert rec["content_type"] == "image_only"

    def test_volume_is_int(self, sample_record):
        assert isinstance(sample_record["volume"], int)

    def test_page_number_int_is_int(self, sample_record):
        assert isinstance(sample_record["page_number_int"], int)

    def test_footnotes_structure(self, sample_record):
        fns = sample_record["footnotes"]
        assert isinstance(fns, list)
        assert len(fns) == 1
        assert set(fns[0].keys()) == {"number", "text"}

    def test_no_raw_html_in_default_output(self, sample_record):
        """Raw HTML fields should NOT be in default JSONL output."""
        assert "raw_matn_html" not in sample_record
        assert "raw_fn_html" not in sample_record

    def test_no_is_image_only_field(self, sample_record):
        """The old is_image_only field should NOT be in output (replaced by content_type)."""
        assert "is_image_only" not in sample_record

    def test_no_has_tables_field(self, sample_record):
        """Spec says has_table (singular), not has_tables."""
        assert "has_tables" not in sample_record
        assert "has_table" in sample_record

    def test_json_serializable(self, sample_record):
        """Record must be JSON-serializable."""
        s = json.dumps(sample_record, ensure_ascii=False)
        roundtrip = json.loads(s)
        assert roundtrip == sample_record


# ═══════════════════════════════════════════════════════════════════════════
# Integration Tests: full book normalization
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalizeBook:
    def test_multi_page_book(self):
        """Book with multiple pages normalizes correctly."""
        p1 = make_page_html("Page one text", page_num_arabic="١")
        p2 = make_page_html("Page two text", page_num_arabic="٢")
        html = make_book_html(p1, p2)
        pages, report = normalize_book(html, "test", "test.htm", volume=1)
        assert len(pages) == 2
        assert pages[0].page_number_int == 1
        assert pages[1].page_number_int == 2

    def test_skips_metadata_pages(self):
        """Pages without page numbers are skipped."""
        meta = "<div class='PageText'><div class='PageHead'><span class='title'>Title</span><hr/></div>intro</div>"
        p1 = make_page_html("Real content", page_num_arabic="١")
        html = make_book_html(meta, p1)
        pages, report = normalize_book(html, "test", "test.htm")
        assert len(pages) == 1
        assert len(report.pages_skipped) == 1

    def test_document_order_preserved(self):
        """P3: Pages emitted in document order."""
        p1 = make_page_html("First", page_num_arabic="٥")
        p2 = make_page_html("Second", page_num_arabic="٣")
        html = make_book_html(p1, p2)
        pages, _ = normalize_book(html, "test", "test.htm")
        assert pages[0].page_number_int == 5
        assert pages[1].page_number_int == 3

    def test_report_statistics(self):
        """Report aggregates stats correctly."""
        p1 = make_page_html("Text (1) ref", footnotes="(1) A note")
        p2 = make_page_html("Verse … here")
        html = make_book_html(p1, p2)
        _, report = normalize_book(html, "test", "test.htm")
        assert report.total_pages == 2
        assert report.pages_with_footnotes == 1
        assert report.total_footnotes == 1
        assert report.pages_with_verse == 1

    def test_source_sha256_computed(self):
        html = make_book_html(make_page_html("text", page_num_arabic="١"))
        _, report = normalize_book(html, "test", "test.htm")
        assert len(report.source_sha256) == 64

    def test_determinism(self):
        """Same input → identical output (normalizer is deterministic)."""
        p1 = make_page_html("Content (1) here", footnotes="(1) Note")
        p2 = make_page_html("More text … verse")
        html = make_book_html(p1, p2)

        pages_a, _ = normalize_book(html, "test", "test.htm")
        pages_b, _ = normalize_book(html, "test", "test.htm")

        for a, b in zip(pages_a, pages_b):
            assert a.matn_text == b.matn_text
            assert a.footnote_ref_numbers == b.footnote_ref_numbers
            assert len(a.footnotes) == len(b.footnotes)


# ═══════════════════════════════════════════════════════════════════════════
# Multi-Volume Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMultiVolume:
    def test_discover_volume_files(self, tmp_path):
        """VOL2: Numbered .htm files discovered and sorted."""
        (tmp_path / "001.htm").write_text("<html></html>")
        (tmp_path / "002.htm").write_text("<html></html>")
        (tmp_path / "003.htm").write_text("<html></html>")
        vols = discover_volume_files(str(tmp_path))
        assert len(vols) == 3
        assert [v[0] for v in vols] == [1, 2, 3]

    def test_skip_non_numeric_files(self, tmp_path):
        """VOL3: Non-numeric .htm files skipped."""
        (tmp_path / "001.htm").write_text("<html></html>")
        (tmp_path / "muqaddima.htm").write_text("<html></html>")
        (tmp_path / "notes.txt").write_text("not html")
        vols = discover_volume_files(str(tmp_path))
        assert len(vols) == 1
        assert vols[0][0] == 1

    def test_volume_order(self, tmp_path):
        """VOL4: Volume files processed in numeric order."""
        (tmp_path / "003.htm").write_text("<html></html>")
        (tmp_path / "001.htm").write_text("<html></html>")
        (tmp_path / "002.htm").write_text("<html></html>")
        vols = discover_volume_files(str(tmp_path))
        assert [v[0] for v in vols] == [1, 2, 3]

    def test_multivolume_normalization(self, tmp_path):
        """Multi-volume: pages tagged with correct volume numbers."""
        for i in [1, 2]:
            p = make_page_html(f"Vol {i} content", page_num_arabic="١")
            html = make_book_html(p)
            (tmp_path / f"00{i}.htm").write_text(html, encoding="utf-8")

        pages, reports = normalize_multivolume(str(tmp_path), "test_book")
        assert len(reports) == 2
        assert pages[0].volume == 1
        assert pages[1].volume == 2

    def test_aggregate_reports(self):
        """Report aggregation sums correctly across volumes."""
        r1 = NormalizationReport(
            book_id="test", source_file="001.htm", source_sha256="abc",
            volume=1, total_pages=100, pages_with_footnotes=50,
            total_footnotes=200, pages_with_verse=10, pages_with_tables=1,
            pages_image_only=0, orphan_footnote_refs=0, orphan_footnotes=2,
            warnings=["w1"], pages_skipped=["s1"],
        )
        r2 = NormalizationReport(
            book_id="test", source_file="002.htm", source_sha256="def",
            volume=2, total_pages=80, pages_with_footnotes=30,
            total_footnotes=100, pages_with_verse=5, pages_with_tables=0,
            pages_image_only=1, orphan_footnote_refs=1, orphan_footnotes=0,
            warnings=["w2"], pages_skipped=[],
        )
        agg = aggregate_reports([r1, r2], "test")
        assert agg["total_pages"] == 180
        assert agg["volume_count"] == 2
        assert agg["total_footnotes"] == 300
        assert agg["pages_with_verse"] == 15
        assert agg["pages_with_tables"] == 1
        assert agg["pages_image_only"] == 1
        assert agg["orphan_footnotes"] == 2
        assert agg["orphan_footnote_refs"] == 1
        assert len(agg["warnings"]) == 2
        assert len(agg["volumes"]) == 2

    def test_empty_directory_raises(self, tmp_path):
        """Empty directory raises ValueError."""
        with pytest.raises(ValueError, match="No numbered .htm"):
            normalize_multivolume(str(tmp_path), "test")

    def test_non_numeric_only_directory_raises(self, tmp_path):
        """Directory with only named .htm files raises ValueError."""
        (tmp_path / "الكتاب.htm").write_text("<html></html>")
        (tmp_path / "مقدمة.htm").write_text("<html></html>")
        with pytest.raises(ValueError, match="skipped non-numeric"):
            discover_volume_files(str(tmp_path))

    def test_mixed_numeric_non_numeric(self, tmp_path):
        """Mixed directory: numeric files discovered, named files skipped."""
        (tmp_path / "001.htm").write_text("<html></html>")
        (tmp_path / "002.htm").write_text("<html></html>")
        (tmp_path / "مقدمة.htm").write_text("<html></html>")
        vols = discover_volume_files(str(tmp_path))
        assert len(vols) == 2  # Only 001.htm and 002.htm
        assert [v[0] for v in vols] == [1, 2]

    @pytest.mark.skipif(not HAS_OTHER_BOOKS, reason="Other Books not available")
    def test_real_multivolume_book(self):
        """Smoke test: normalize a real multi-volume book from Other Books."""
        mv_dir = OTHER_BOOKS / "كتب البلاغة" / "الإيضاح في علوم البلاغة"
        if not mv_dir.exists():
            pytest.skip("Multi-volume test book not available")
        pages, reports = normalize_multivolume(str(mv_dir), "iidah")
        assert len(reports) == 3
        assert len(pages) > 0
        # Verify volumes are distinct
        vols = {p.volume for p in pages}
        assert len(vols) == 3


# ═══════════════════════════════════════════════════════════════════════════
# Source fidelity tests (§4.1 — Forbidden Transformations)
# ═══════════════════════════════════════════════════════════════════════════

class TestSourceFidelity:
    """Verify normalizer NEVER alters the author's text."""

    def test_no_spelling_correction(self):
        """Typos preserved verbatim."""
        html = make_page_html("كلمة خاطاة مكتوبة")
        page = normalize_page(html)
        assert "خاطاة" in page.matn_text

    def test_diacritics_preserved(self):
        """Tashkeel preserved exactly."""
        text_with_harakat = "بِسْمِ اللّهِ الرَّحْمَنِ الرَّحِيم"
        html = make_page_html(text_with_harakat)
        page = normalize_page(html)
        assert text_with_harakat in page.matn_text

    def test_tatweel_preserved(self):
        """Tatweel (kashida) preserved."""
        html = make_page_html("كتـــاب")
        page = normalize_page(html)
        assert "كتـــاب" in page.matn_text

    def test_punctuation_preserved(self):
        """Arabic punctuation preserved exactly."""
        text = "قال: «نعم»، وأضاف؛ ثمّ قال."
        html = make_page_html(text)
        page = normalize_page(html)
        assert text in page.matn_text

    def test_parenthetical_content_preserved(self):
        """Non-footnote parenthetical text preserved."""
        text = "(في معرفة الفصاحة والبلاغة)"
        html = make_page_html(text)
        page = normalize_page(html)
        assert text in page.matn_text


# ═══════════════════════════════════════════════════════════════════════════
# Stage 0 integration tests
# ═══════════════════════════════════════════════════════════════════════════

class TestStage0Integration:
    """Test integration with books/{book_id}/intake_metadata.json."""

    def test_load_intake_metadata(self):
        """Can load intake metadata for intaken books."""
        meta = load_intake_metadata("jawahir", str(BOOKS_DIR))
        assert meta["book_id"] == "jawahir"
        assert meta["primary_science"] == "balagha"
        assert len(meta["source_files"]) >= 1

    def test_load_missing_book_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No intake_metadata.json"):
            load_intake_metadata("nonexistent", str(tmp_path))

    def test_resolve_source_paths_single_volume(self):
        meta = load_intake_metadata("jawahir", str(BOOKS_DIR))
        sources = resolve_source_paths(meta, str(REPO_ROOT))
        assert len(sources) == 1
        vol, path = sources[0]
        assert vol == 1
        assert "jawahir" in path

    def test_resolve_source_paths_multi_volume(self):
        meta = load_intake_metadata("ibn_aqil", str(BOOKS_DIR))
        sources = resolve_source_paths(meta, str(REPO_ROOT))
        assert len(sources) == 4
        assert [v for v, _ in sources] == [1, 2, 3, 4]

    @pytest.mark.parametrize("book_id", ["jawahir", "shadha", "qatr", "imla", "dalail", "miftah"])
    def test_all_single_volume_books_have_metadata(self, book_id):
        """All intaken books have valid intake_metadata.json."""
        meta = load_intake_metadata(book_id, str(BOOKS_DIR))
        assert meta["book_id"] == book_id
        assert len(meta.get("source_files", [])) >= 1

    def test_default_output_paths(self):
        """Verify default output paths follow convention."""
        book_id = "jawahir"
        expected_jsonl = os.path.join("books", book_id, "pages.jsonl")
        expected_report = os.path.join("books", book_id, "normalization_report.json")
        assert "pages.jsonl" in expected_jsonl
        assert "normalization_report.json" in expected_report


# ═══════════════════════════════════════════════════════════════════════════
# Gold sample validation tests
# ═══════════════════════════════════════════════════════════════════════════

class TestGoldSamples:
    """Validate normalizer output against gold samples (jawahir)."""

    @pytest.fixture(scope="class")
    def gold_records(self) -> list[dict]:
        """Load all gold sample records."""
        records = []
        with open(GOLD_JSONL, encoding="utf-8") as f:
            for line in f:
                records.append(json.loads(line))
        return records

    @pytest.fixture(scope="class")
    def gold_full_records(self) -> list[dict]:
        """Load gold records with raw HTML (pages 19–40)."""
        records = []
        with open(GOLD_FULL_JSONL, encoding="utf-8") as f:
            for line in f:
                records.append(json.loads(line))
        return records

    def test_gold_samples_exist(self):
        assert GOLD_JSONL.exists()
        assert GOLD_FULL_JSONL.exists()
        assert GOLD_REPORT.exists()

    def test_gold_page_count(self, gold_records):
        """Gold has 308 pages (matches jawahir intake metadata)."""
        assert len(gold_records) == 308

    def test_gold_full_page_range(self, gold_full_records):
        """Full gold covers pages 19–40."""
        page_nums = [r["page_number_int"] for r in gold_full_records]
        assert min(page_nums) == 19
        assert max(page_nums) == 40

    def test_gold_record_types(self, gold_records):
        """All gold records have record_type=normalized_page."""
        for r in gold_records:
            assert r["record_type"] == "normalized_page"

    def test_gold_book_ids(self, gold_records):
        """All gold records have book_id=jawahir."""
        for r in gold_records:
            assert r["book_id"] == "jawahir"

    def test_renormalize_gold_html_matn_matches(self, gold_full_records):
        """Re-normalizing raw HTML from gold produces same matn text."""
        for rec in gold_full_records:
            if "raw_matn_html" not in rec:
                continue
            raw_matn = rec["raw_matn_html"]
            raw_fn = rec.get("raw_fn_html", "")

            # Parse footnotes to get known numbers
            fns = parse_footnotes(raw_fn)
            fn_numbers = {fn.number for fn in fns}

            # Reproduce normalization
            matn_html, _ = replace_tables_with_text(raw_matn)
            from normalize_shamela import IMG_TAG_RE
            matn_html = IMG_TAG_RE.sub("", matn_html)
            matn_text = strip_tags(matn_html)
            matn_text = clean_verse_markers(matn_text)
            matn_text, _ = strip_fn_refs_from_matn(matn_text, known_fn_numbers=fn_numbers)
            matn_text = normalize_whitespace(matn_text)

            assert matn_text == rec["matn_text"], (
                f"Matn mismatch on page {rec['page_number_int']}: "
                f"expected length {len(rec['matn_text'])}, got {len(matn_text)}"
            )

    def test_renormalize_gold_html_footnotes_match(self, gold_full_records):
        """Re-normalizing raw HTML footnotes produces same footnotes."""
        for rec in gold_full_records:
            if "raw_fn_html" not in rec:
                continue
            fns = parse_footnotes(rec.get("raw_fn_html", ""))
            gold_fns = rec.get("footnotes", [])
            assert len(fns) == len(gold_fns), (
                f"Footnote count mismatch on page {rec['page_number_int']}: "
                f"expected {len(gold_fns)}, got {len(fns)}"
            )
            for fn, gfn in zip(fns, gold_fns):
                assert fn.number == gfn["number"]
                assert fn.text == gfn["text"], (
                    f"Footnote {fn.number} text mismatch on page {rec['page_number_int']}"
                )

    def test_gold_report_statistics(self):
        """Gold report has expected statistics."""
        with open(GOLD_REPORT, encoding="utf-8") as f:
            report = json.load(f)
        assert report["book_id"] == "jawahir"
        assert report["total_pages"] == 308
        assert report["pages_with_footnotes"] > 0
        assert report["total_footnotes"] > 0

    def test_unique_page_keys(self, gold_records):
        """Spec: (book_id, volume, page_number_int) is unique."""
        # Gold records are from old format (no volume field), so use page_number_int
        page_nums = [r["page_number_int"] for r in gold_records]
        assert len(page_nums) == len(set(page_nums))


# ═══════════════════════════════════════════════════════════════════════════
# Corpus-wide smoke tests (Other Books)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not HAS_OTHER_BOOKS, reason="Other Books not available")
class TestCorpusSmoke:
    """Smoke tests against real Shamela exports from Other Books."""

    @pytest.fixture(scope="class")
    def sample_balagha_files(self):
        """Get a sample of بلاغة books for testing."""
        balagha_dir = OTHER_BOOKS / "كتب البلاغة"
        files = [f for f in balagha_dir.iterdir() if f.suffix == ".htm" and f.is_file()]
        return files[:5]  # Test first 5

    @pytest.fixture(scope="class")
    def sample_nahw_files(self):
        """Get a sample of نحو/صرف books."""
        nahw_dir = OTHER_BOOKS / "كتب النحو والصرف"
        files = [f for f in nahw_dir.iterdir() if f.suffix == ".htm" and f.is_file()]
        return files[:5]

    def test_balagha_books_normalize(self, sample_balagha_files):
        """بلاغة books normalize without errors."""
        for f in sample_balagha_files:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                html = fh.read()
            pages, report = normalize_book(html, "test", str(f))
            assert report.total_pages > 0, f"No pages extracted from {f.name}"
            for p in pages:
                assert p.page_number_int > 0
                assert p.matn_text or p.is_image_only

    def test_nahw_books_normalize(self, sample_nahw_files):
        """نحو/صرف books normalize without errors."""
        for f in sample_nahw_files:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                html = fh.read()
            pages, report = normalize_book(html, "test", str(f))
            assert report.total_pages > 0, f"No pages extracted from {f.name}"

    def test_all_output_records_valid_json(self, sample_balagha_files):
        """Every output record serializes to valid JSON."""
        for f in sample_balagha_files:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                html = fh.read()
            pages, _ = normalize_book(html, "test", str(f))
            for p in pages:
                rec = page_to_jsonl_record(p, "test")
                s = json.dumps(rec, ensure_ascii=False)
                roundtrip = json.loads(s)
                assert roundtrip["record_type"] == "normalized_page"

    def test_no_page_has_negative_number(self, sample_balagha_files):
        """Sanity: no page has a negative or zero page number."""
        for f in sample_balagha_files:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                html = fh.read()
            pages, _ = normalize_book(html, "test", str(f))
            for p in pages:
                assert p.page_number_int > 0

    def test_shamela_format_assumptions(self, sample_balagha_files):
        """A1–A6: Core Shamela format assumptions hold."""
        for f in sample_balagha_files:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                html = fh.read()
            # A1: PageText divs exist
            assert "<div class='PageText'>" in html, f"A1 failed: {f.name}"
            # A2: PageHead structure
            assert "PageHead" in html, f"A2 failed: {f.name}"
            # A3: Arabic-Indic page numbers
            assert re.search(r"\(ص:\s*[٠-٩]+\)", html), f"A3 failed: {f.name}"

    @pytest.mark.skipif(not HAS_OTHER_BOOKS, reason="Other Books not available")
    def test_corpus_wide_page_count_sanity(self):
        """Across multiple books, total pages > 1000."""
        total = 0
        balagha_dir = OTHER_BOOKS / "كتب البلاغة"
        files = [f for f in balagha_dir.iterdir() if f.suffix == ".htm" and f.is_file()]
        for f in files[:10]:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                html = fh.read()
            _, report = normalize_book(html, "test", str(f))
            total += report.total_pages
        assert total > 1000


# ═══════════════════════════════════════════════════════════════════════════
# Edge case tests
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_empty_page(self):
        """Page with header but no content generates EMPTY_PAGE warning."""
        html = make_page_html("", page_num_arabic="١")
        page = normalize_page(html)
        assert page is not None
        assert page.matn_text == ""
        assert any("EMPTY_PAGE" in w for w in page.warnings)

    def test_footnote_spanning_formats(self):
        """L4: Both footnote formats in same page."""
        fn_html = "(1) ـ First with dash.\n(2) Second without dash."
        fns = parse_footnotes(fn_html)
        assert len(fns) == 2
        assert "First with dash." in fns[0].text
        assert "Second without dash." in fns[1].text

    def test_deeply_nested_html(self):
        """Deeply nested HTML doesn't crash."""
        nested = "<div>" * 20 + "content" + "</div>" * 20
        html = make_page_html(nested)
        page = normalize_page(html)
        assert "content" in page.matn_text

    def test_large_footnote_number(self):
        """Footnote numbers > 9 handled."""
        html = make_page_html(
            "Text (12) here",
            footnotes="(12) A big footnote number."
        )
        page = normalize_page(html)
        assert len(page.footnotes) == 1
        assert page.footnotes[0].number == 12

    def test_multiple_hr_separators(self):
        """Only the first hr width=95 separates matn from footnotes."""
        html = (
            "<div class='PageText'>"
            "<div class='PageHead'><span class='PageNumber'>(ص: ١)</span><hr/></div>"
            "Matn text"
            "<hr width='95' align='right'>"
            "<div class='footnote'>(1) First footnote</div>"
            "</div>"
        )
        page = normalize_page(html)
        assert "Matn text" in page.matn_text
        assert len(page.footnotes) == 1

    def test_unicode_preservation(self):
        """No Unicode normalization applied."""
        # Different Unicode representations of shadda+kasra
        text1 = "بِسْمِ"  # Standard
        html = make_page_html(text1)
        page = normalize_page(html)
        # Byte-level identity
        assert page.matn_text.encode("utf-8") == text1.encode("utf-8")

    def test_very_long_page(self):
        """Page with very long content doesn't crash."""
        long_text = "كلمة " * 10000
        html = make_page_html(long_text)
        page = normalize_page(html)
        assert len(page.matn_text) > 0


# ═══════════════════════════════════════════════════════════════════════════
# CLI tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCLI:
    def test_single_file_mode(self, tmp_path):
        """CLI: --html mode produces output files."""
        html = make_book_html(
            make_page_html("Test content", page_num_arabic="١")
        )
        html_file = tmp_path / "test.htm"
        html_file.write_text(html, encoding="utf-8")
        out_jsonl = tmp_path / "output.jsonl"
        out_report = tmp_path / "report.json"

        import subprocess
        result = subprocess.run(
            [
                sys.executable, str(REPO_ROOT / "tools" / "normalize_shamela.py"),
                "--html", str(html_file),
                "--out-jsonl", str(out_jsonl),
                "--out-report", str(out_report),
                "--id", "test_book",
            ],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"STDERR: {result.stderr}"
        assert out_jsonl.exists()
        assert out_report.exists()

        # Verify JSONL content
        with open(out_jsonl, encoding="utf-8") as f:
            records = [json.loads(line) for line in f]
        assert len(records) == 1
        assert records[0]["book_id"] == "test_book"
        assert records[0]["content_type"] == "text"
        assert records[0]["volume"] == 1

    def test_html_dir_mode(self, tmp_path):
        """CLI: --html-dir mode produces multi-volume output."""
        book_dir = tmp_path / "multibook"
        book_dir.mkdir()
        for i in [1, 2]:
            p = make_page_html(f"Volume {i}", page_num_arabic="١")
            (book_dir / f"00{i}.htm").write_text(make_book_html(p), encoding="utf-8")

        out_jsonl = tmp_path / "output.jsonl"
        out_report = tmp_path / "report.json"

        import subprocess
        result = subprocess.run(
            [
                sys.executable, str(REPO_ROOT / "tools" / "normalize_shamela.py"),
                "--html-dir", str(book_dir),
                "--out-jsonl", str(out_jsonl),
                "--out-report", str(out_report),
                "--id", "test_mv",
            ],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"STDERR: {result.stderr}"

        with open(out_jsonl, encoding="utf-8") as f:
            records = [json.loads(line) for line in f]
        assert len(records) == 2
        assert records[0]["volume"] == 1
        assert records[1]["volume"] == 2

    def test_page_range_filter(self, tmp_path):
        """CLI: --page-start/--page-end filters pages."""
        pages = [
            make_page_html(f"Page {i}", page_num_arabic=f"{'٠١٢٣٤٥٦٧٨٩'[i]}")
            for i in range(1, 6)
        ]
        html_file = tmp_path / "test.htm"
        html_file.write_text(make_book_html(*pages), encoding="utf-8")
        out_jsonl = tmp_path / "output.jsonl"

        import subprocess
        result = subprocess.run(
            [
                sys.executable, str(REPO_ROOT / "tools" / "normalize_shamela.py"),
                "--html", str(html_file),
                "--out-jsonl", str(out_jsonl),
                "--out-report", str(tmp_path / "r.json"),
                "--id", "test",
                "--page-start", "2",
                "--page-end", "4",
            ],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        with open(out_jsonl, encoding="utf-8") as f:
            records = [json.loads(line) for line in f]
        page_nums = [r["page_number_int"] for r in records]
        assert all(2 <= n <= 4 for n in page_nums)

    def test_mutually_exclusive_input(self, tmp_path):
        """CLI: --html, --html-dir, --book-id are mutually exclusive."""
        import subprocess
        result = subprocess.run(
            [
                sys.executable, str(REPO_ROOT / "tools" / "normalize_shamela.py"),
                "--html", "a.htm",
                "--html-dir", "b/",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
