#!/usr/bin/env python3
"""
Tests for Stage 0: Book Intake (tools/intake.py)

Run: pytest tests/test_intake.py -v
"""

import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

# Ensure tools/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from intake import (
    BOOK_ID_PATTERN,
    EXACT_FIELDS,
    MUHAQIQ_EXCLUSIONS,
    MUHAQIQ_PATTERNS,
    QISM_HIGH_RELIABILITY,
    QISM_LOW_RELIABILITY,
    QISM_MEDIUM_RELIABILITY,
    SINGLE_SCIENCES,
    VALID_SCIENCES,
    build_registry_entry,
    check_duplicate_hashes,
    check_duplicate_id,
    classify_directory,
    count_pages,
    extract_scholarly_context,
    normalize_volume_filename,
    parse_metadata_card,
    strip_html,
    suggest_book_id,
    validate_science,
    validate_shamela_file,
)

# ─── Repo root helper ──────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
OTHER_BOOKS = REPO_ROOT / "books" / "Other Books"
HAS_OTHER_BOOKS = OTHER_BOOKS.exists()


# ─── Unit tests: strip_html ────────────────────────────────────────────────

class TestStripHtml:
    def test_basic_tags(self):
        assert strip_html("<b>bold</b>") == "bold"

    def test_nbsp(self):
        assert strip_html("hello&nbsp;&nbsp;world") == "hello world"

    def test_xa0(self):
        assert strip_html("hello\xa0world") == "hello world"

    def test_multiple_whitespace(self):
        assert strip_html("hello   \n\t  world") == "hello world"

    def test_font_tags(self):
        assert strip_html("<font color=#be0000>:</font>") == ":"

    def test_combined(self):
        result = strip_html("<span class='title'>القسم<font color=#be0000>:</font></span> البلاغة")
        assert result == "القسم: البلاغة"


# ─── Unit tests: book ID validation ────────────────────────────────────────

class TestBookIdPattern:
    @pytest.mark.parametrize("book_id", [
        "abc", "jawahir", "ibn_aqil", "shadha_al_arf", "aa",
    ])
    def test_valid_ids(self, book_id):
        # Note: "aa" matches regex but may fail length check (2 chars)
        if len(book_id) >= 3:
            assert BOOK_ID_PATTERN.match(book_id)

    @pytest.mark.parametrize("book_id,reason", [
        ("a_", "ends with underscore"),
        ("_a", "starts with underscore"),
        ("a1b", "contains digit"),
        ("ABC", "uppercase"),
        ("a-b", "contains hyphen"),
        ("a b", "contains space"),
        ("a", "single char"),
    ])
    def test_invalid_ids(self, book_id, reason):
        assert not BOOK_ID_PATTERN.match(book_id), f"Should reject: {reason}"

    def test_consecutive_underscores_allowed(self):
        # Documented: consecutive underscores pass the regex.
        # This is accepted behavior per spec.
        assert BOOK_ID_PATTERN.match("a__b")


# ─── Unit tests: parse_metadata_card ───────────────────────────────────────

class TestParseMetadataCard:
    MINIMAL_CARD = """
    <div class='PageText'>
    <span class='title'>كتاب اختبار&nbsp;&nbsp;&nbsp;</span>
    <span class='footnote'>(المؤلف القصير)</span>
    <p>
    <span class='title'>القسم:</span> البلاغة<hr>
    <p>
    <span class='title'>الكتاب<font color=#be0000>:</font></span> الكتاب الرسمي
    <p>
    <span class='title'>المؤلف<font color=#be0000>:</font></span> الاسم الكامل للمؤلف
    </div>
    """

    def test_minimal_card(self):
        result, err = parse_metadata_card(self.MINIMAL_CARD)
        assert err is None
        assert result["title"] == "كتاب اختبار"
        assert result["shamela_author_short"] == "المؤلف القصير"
        assert result["html_qism_field"] == "البلاغة"
        assert result["title_formal"] == "الكتاب الرسمي"
        assert result["author"] == "الاسم الكامل للمؤلف"

    def test_no_pagetext_div(self):
        result, err = parse_metadata_card("<html><body>nothing</body></html>")
        assert result is None
        assert "No PageText div" in err

    def test_no_title_spans(self):
        result, err = parse_metadata_card("<div class='PageText'>bare text</div>")
        assert result is None
        assert "No <span class='title'>" in err

    def test_muhaqiq_patterns(self):
        """Each muhaqiq label variant should match correctly."""
        for label in ["المحقق", "تحقيق", "دراسة وتحقيق", "ضبط وتعليق"]:
            html = f"""<div class='PageText'>
            <span class='title'>Test&nbsp;&nbsp;&nbsp;</span>
            <span class='footnote'>(A)</span>
            <p>
            <span class='title'>{label}<font color=#be0000>:</font></span> Editor Name
            </div>"""
            result, err = parse_metadata_card(html)
            assert err is None
            assert result["muhaqiq"] == "Editor Name", f"Failed for label: {label}"

    def test_muhaqiq_exclusion(self):
        """أصل التحقيق should NOT match as muhaqiq."""
        html = """<div class='PageText'>
        <span class='title'>Test&nbsp;&nbsp;&nbsp;</span>
        <span class='footnote'>(A)</span>
        <p>
        <span class='title'>المحقق<font color=#be0000>:</font></span> Real Editor
        <p>
        <span class='title'>أصل التحقيق<font color=#be0000>:</font></span> PhD thesis description
        </div>"""
        result, err = parse_metadata_card(html)
        assert err is None
        assert result["muhaqiq"] == "Real Editor"
        assert any("أصل التحقيق" in line for line in result["unrecognized_metadata_lines"])

    def test_muhaqiq_keep_first(self):
        """If two non-excluded muhaqiq labels exist, keep the first."""
        html = """<div class='PageText'>
        <span class='title'>Test&nbsp;&nbsp;&nbsp;</span>
        <span class='footnote'>(A)</span>
        <p>
        <span class='title'>المحقق<font color=#be0000>:</font></span> First Editor
        <p>
        <span class='title'>ضبط وتعليق<font color=#be0000>:</font></span> Second Editor
        </div>"""
        result, err = parse_metadata_card(html)
        assert err is None
        assert result["muhaqiq"] == "First Editor"
        assert any("Second Editor" in line for line in result["unrecognized_metadata_lines"])

    def test_leading_digit_extraction(self):
        """Page count should extract leading digits from annotated strings."""
        html = """<div class='PageText'>
        <span class='title'>Test&nbsp;&nbsp;&nbsp;</span>
        <span class='footnote'>(A)</span>
        <p>
        <span class='title'>عدد الصفحات<font color=#be0000>:</font></span> 344[ترقيم الكتاب موافق للمطبوع]
        </div>"""
        result, err = parse_metadata_card(html)
        assert err is None
        assert result["shamela_page_count"] == 344

    def test_floating_annotation_stripped(self):
        """Floating [ترقيم...] annotations should be stripped from field values."""
        html = """<div class='PageText'>
        <span class='title'>Test&nbsp;&nbsp;&nbsp;</span>
        <span class='footnote'>(A)</span>
        <p>
        <span class='title'>الناشر<font color=#be0000>:</font></span> دار النشر
        [ترقيم الكتاب موافق للمطبوع]
        </div>"""
        result, err = parse_metadata_card(html)
        assert err is None
        assert result["publisher"] == "دار النشر"

    def test_floating_annotation_standalone_preserved(self):
        """Standalone [ترقيم...] segment should go to unrecognized."""
        html = """<div class='PageText'>
        <span class='title'>Test&nbsp;&nbsp;&nbsp;</span>
        <span class='footnote'>(A)</span>
        <p>
        <span class='title'>[ترقيم الكتاب موافق للمطبوع]</span>
        </div>"""
        result, err = parse_metadata_card(html)
        assert err is None
        assert len(result["unrecognized_metadata_lines"]) >= 1

    def test_unrecognized_label(self):
        """Unknown labels should go to unrecognized_metadata_lines."""
        html = """<div class='PageText'>
        <span class='title'>Test&nbsp;&nbsp;&nbsp;</span>
        <span class='footnote'>(A)</span>
        <p>
        <span class='title'>كود المادة<font color=#be0000>:</font></span> 12345
        </div>"""
        result, err = parse_metadata_card(html)
        assert err is None
        assert any("كود المادة" in line for line in result["unrecognized_metadata_lines"])


# ─── Unit tests: count_pages ───────────────────────────────────────────────

class TestCountPages:
    def test_basic(self):
        html = "<span class='PageNumber'>1</span><span class='PageNumber'>2</span>"
        assert count_pages(html) == 2

    def test_no_pages(self):
        assert count_pages("<html><body>no pages</body></html>") == 0

    def test_does_not_count_pagetext(self):
        html = ("<div class='PageText'>content</div>"
                "<div class='PageText'>content</div>"
                "<span class='PageNumber'>1</span>")
        assert count_pages(html) == 1


# ─── Unit tests: validate_science ──────────────────────────────────────────

class TestValidateScience:
    def test_high_reliability_match(self):
        result = validate_science("balagha", "البلاغة", non_interactive=True)
        assert result == "balagha"

    def test_high_reliability_mismatch_aborts(self):
        """High-reliability mismatch in non-interactive mode should abort."""
        with pytest.raises(SystemExit):
            validate_science("sarf", "البلاغة", non_interactive=True)

    def test_medium_reliability_accepted(self):
        result = validate_science("nahw", "النحو والصرف", non_interactive=True)
        assert result == "nahw"

    def test_low_reliability_accepted(self):
        result = validate_science("balagha", "كتب اللغة", non_interactive=True)
        assert result == "balagha"

    def test_unrelated_accepted(self):
        result = validate_science("unrelated", "البلاغة", non_interactive=True)
        assert result == "unrelated"

    def test_multi_accepted(self):
        result = validate_science("multi", "النحو والصرف", non_interactive=True)
        assert result == "multi"

    def test_none_qism(self):
        result = validate_science("nahw", None, non_interactive=True)
        assert result == "nahw"


# ─── Unit tests: check_duplicate_id ────────────────────────────────────────

class TestCheckDuplicateId:
    def test_no_registry(self):
        assert check_duplicate_id(None, "test") is None

    def test_empty_books(self):
        assert check_duplicate_id({"books": []}, "test") is None

    def test_no_match(self):
        reg = {"books": [{"book_id": "other", "title": "Other Book"}]}
        assert check_duplicate_id(reg, "test") is None

    def test_match(self):
        reg = {"books": [{"book_id": "test", "title": "Test Book"}]}
        assert check_duplicate_id(reg, "test") == "Test Book"


# ─── Unit tests: check_duplicate_hashes ────────────────────────────────────

class TestCheckDuplicateHashes:
    def test_no_registry(self):
        assert check_duplicate_hashes(None, {"f.htm": "abc123"}, False) is False

    def test_clean(self):
        reg = {"books": [{"book_id": "other", "source_hashes": ["xyz789"]}]}
        assert check_duplicate_hashes(reg, {"f.htm": "abc123"}, False) is False

    def test_duplicate_no_force(self):
        reg = {"books": [{"book_id": "other", "source_hashes": ["abc123"]}]}
        with pytest.raises(SystemExit):
            check_duplicate_hashes(reg, {"f.htm": "abc123"}, False)

    def test_duplicate_with_force(self):
        reg = {"books": [{"book_id": "other", "source_hashes": ["abc123"]}]}
        result = check_duplicate_hashes(reg, {"f.htm": "abc123"}, True)
        assert result is True  # duplicates found but force-bypassed


# ─── Unit tests: build_registry_entry ──────────────────────────────────────

class TestBuildRegistryEntry:
    def test_null_fields_omitted(self):
        metadata = {
            "book_id": "test",
            "title": "Test",
            "title_formal": None,
            "author": None,
            "muhaqiq": None,
            "primary_science": "nahw",
            "book_category": "single_science",
            "volume_count": 1,
            "language": "ar",
            "edition_notes": None,
            "source_files": [
                {"relpath": "books/test/source/test.htm", "sha256": "abc", "role": "primary_export",
                 "volume_number": None}
            ],
            "science_parts": None,
        }
        entry = build_registry_entry(metadata)
        assert "title_formal" not in entry
        assert "author" not in entry
        assert "muhaqiq" not in entry
        assert "edition_notes" not in entry
        assert "science_parts" not in entry
        assert entry["status"] == "active"
        assert entry["source_format"] == "shamela_html"


# ─── Integration tests: existing metadata files ───────────────────────────

class TestExistingMetadata:
    """Validate the 7 existing intake_metadata.json files."""

    BOOKS = ["jawahir", "dalail", "ibn_aqil", "imla", "qatr", "shadha", "miftah"]

    @pytest.mark.parametrize("book_id", BOOKS)
    def test_metadata_is_valid_json(self, book_id):
        path = REPO_ROOT / "books" / book_id / "intake_metadata.json"
        if not path.exists():
            pytest.skip(f"Metadata not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    @pytest.mark.parametrize("book_id", BOOKS)
    def test_metadata_validates_against_schema(self, book_id):
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")

        meta_path = REPO_ROOT / "books" / book_id / "intake_metadata.json"
        schema_path = REPO_ROOT / "schemas" / "intake_metadata_schema.json"
        if not meta_path.exists():
            pytest.skip(f"Metadata not found: {meta_path}")

        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(metadata, schema)

    @pytest.mark.parametrize("book_id", BOOKS)
    def test_metadata_registry_consistency(self, book_id):
        meta_path = REPO_ROOT / "books" / book_id / "intake_metadata.json"
        reg_path = REPO_ROOT / "books" / "books_registry.yaml"
        if not meta_path.exists() or not reg_path.exists():
            pytest.skip("Files not found")

        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        registry = yaml.safe_load(reg_path.read_text(encoding="utf-8"))

        reg_entry = None
        for b in registry.get("books", []):
            if b.get("book_id") == book_id:
                reg_entry = b
                break
        assert reg_entry is not None, f"Book {book_id} not in registry"

        assert reg_entry["title"] == metadata["title"]
        assert reg_entry["volume_count"] == metadata["volume_count"]

        reg_hashes = reg_entry.get("source_hashes", [])
        meta_hashes = [sf["sha256"] for sf in metadata["source_files"]]
        assert reg_hashes == meta_hashes


# ─── Integration tests: parser on real corpus ─────────────────────────────

@pytest.mark.skipif(not HAS_OTHER_BOOKS, reason="Other Books not present")
class TestParserOnCorpus:
    """Run the metadata parser across the full Other Books corpus."""

    @staticmethod
    def _all_htm_files():
        """Collect all .htm paths in Other Books."""
        files = []
        for root, dirs, fnames in os.walk(str(OTHER_BOOKS)):
            for fn in fnames:
                if fn.endswith('.htm'):
                    files.append(os.path.join(root, fn))
        return files

    def test_all_files_parse_without_error(self):
        files = self._all_htm_files()
        assert len(files) > 0, "No .htm files found"
        failures = []
        for path in files:
            html = open(path, 'r', encoding='utf-8', errors='replace').read()
            result, err = parse_metadata_card(html)
            if err:
                failures.append(f"{os.path.basename(path)}: {err}")
            elif not result.get("title"):
                failures.append(f"{os.path.basename(path)}: no title")
        assert len(failures) == 0, f"{len(failures)} parse failures:\n" + "\n".join(failures[:10])

    def test_all_files_have_qism(self):
        files = self._all_htm_files()
        missing_qism = []
        for path in files:
            html = open(path, 'r', encoding='utf-8', errors='replace').read()
            result, _ = parse_metadata_card(html)
            if result and not result.get("html_qism_field"):
                missing_qism.append(os.path.basename(path))
        # We expect all Shamela exports to have a قسم field
        assert len(missing_qism) == 0, f"{len(missing_qism)} files missing قسم"

    def test_no_muhaqiq_data_loss(self):
        """Verify that muhaqiq exclusions and keep-first logic work across corpus."""
        files = self._all_htm_files()
        for path in files:
            html = open(path, 'r', encoding='utf-8', errors='replace').read()
            result, err = parse_metadata_card(html)
            if result and result.get("muhaqiq"):
                # muhaqiq should never contain thesis-description text
                assert "أطروحة" not in result["muhaqiq"], \
                    f"{os.path.basename(path)}: muhaqiq contains thesis text"
                assert "رسالة دكتوراة" not in result["muhaqiq"], \
                    f"{os.path.basename(path)}: muhaqiq contains thesis text"


# ─── Unit tests: scholarly context extraction ──────────────────────────────

class TestScholarlyContext:
    def test_death_date_western_numerals(self):
        meta = {"author": "عبد القاهر الجرجاني (ت 471 هـ)", "title": "Test", "title_formal": None}
        ctx = extract_scholarly_context(meta)
        assert ctx["author_death_hijri"] == 471

    def test_death_date_arabic_numerals(self):
        meta = {"author": "القزويني (ت ٧٣٩هـ)", "title": "Test", "title_formal": None}
        ctx = extract_scholarly_context(meta)
        assert ctx["author_death_hijri"] == 739

    def test_madhab_shafii(self):
        meta = {"author": "القزويني الشافعي", "title": "Test", "title_formal": None}
        ctx = extract_scholarly_context(meta)
        assert ctx["fiqh_madhab"] == "shafii"

    def test_madhab_hanafi(self):
        meta = {"author": "ابن الهمام الحنفي", "title": "Test", "title_formal": None}
        ctx = extract_scholarly_context(meta)
        assert ctx["fiqh_madhab"] == "hanafi"

    def test_geographic_origin(self):
        meta = {"author": "جلال الدين القزويني الشافعي", "title": "Test", "title_formal": None}
        ctx = extract_scholarly_context(meta)
        assert ctx["geographic_origin"] == "القزويني"

    def test_geographic_filters_madhab(self):
        """الشافعي should not be captured as geographic origin."""
        meta = {"author": "أحمد الشافعي", "title": "Test", "title_formal": None}
        ctx = extract_scholarly_context(meta)
        assert ctx["geographic_origin"] != "الشافعي" or ctx["geographic_origin"] is None

    def test_book_type_sharh(self):
        meta = {"author": "Author", "title": "شرح ابن عقيل", "title_formal": None}
        ctx = extract_scholarly_context(meta)
        assert ctx["book_type"] == "sharh"

    def test_book_type_hashiya(self):
        meta = {"author": "Author", "title": "حاشية الخضري", "title_formal": None}
        ctx = extract_scholarly_context(meta)
        assert ctx["book_type"] == "hashiya"

    def test_book_type_mukhtasar(self):
        meta = {"author": "Author", "title": "مختصر المعاني", "title_formal": None}
        ctx = extract_scholarly_context(meta)
        assert ctx["book_type"] == "mukhtasar"

    def test_no_author_graceful(self):
        meta = {"author": None, "title": "Test", "title_formal": None}
        ctx = extract_scholarly_context(meta)
        assert ctx["author_death_hijri"] is None
        assert ctx["fiqh_madhab"] is None

    def test_extraction_source_always_auto(self):
        meta = {"author": "Author (ت 500 هـ)", "title": "Test", "title_formal": None}
        ctx = extract_scholarly_context(meta)
        assert ctx["extraction_source"] == "auto"


# ─── Unit tests: volume filename normalization ─────────────────────────────

class TestNormalizeVolumeFilename:
    def test_already_padded(self):
        assert normalize_volume_filename("001.htm", 1) == "001.htm"

    def test_needs_padding(self):
        assert normalize_volume_filename("1.htm", 1) == "001.htm"

    def test_two_digits(self):
        assert normalize_volume_filename("12.htm", 12) == "012.htm"

    def test_preserves_extension(self):
        assert normalize_volume_filename("1.html", 1) == "001.html"


# ─── Unit tests: adjacent science ──────────────────────────────────────────

class TestAdjacentScience:
    def test_adjacent_in_valid_sciences(self):
        assert "adjacent" in VALID_SCIENCES

    def test_adjacent_not_in_single_sciences(self):
        assert "adjacent" not in SINGLE_SCIENCES

    def test_adjacent_validation(self):
        result = validate_science("adjacent", "الأدب", non_interactive=True)
        assert result == "adjacent"


# ─── Integration: scholarly context on real corpus ─────────────────────────

@pytest.mark.skipif(not HAS_OTHER_BOOKS, reason="Other Books not present")
class TestScholarlyContextCorpus:
    def test_death_dates_are_reasonable(self):
        """All auto-extracted death dates should be between 1-1500 AH."""
        files = []
        for root, dirs, fnames in os.walk(str(OTHER_BOOKS)):
            for fn in fnames:
                if fn.endswith('.htm'):
                    files.append(os.path.join(root, fn))

        unreasonable = []
        for path in files:
            html = open(path, 'r', encoding='utf-8', errors='replace').read()
            result, _ = parse_metadata_card(html)
            if result:
                ctx = extract_scholarly_context(result)
                d = ctx["author_death_hijri"]
                if d is not None and (d < 1 or d > 1500):
                    unreasonable.append((os.path.basename(path), d))

        assert len(unreasonable) == 0, \
            f"Unreasonable death dates: {unreasonable[:5]}"

    def test_madhabs_are_valid(self):
        """All auto-extracted madhabs should be from the known set."""
        valid_madhabs = {"shafii", "hanafi", "maliki", "hanbali", None}
        files = []
        for root, dirs, fnames in os.walk(str(OTHER_BOOKS)):
            for fn in fnames:
                if fn.endswith('.htm'):
                    files.append(os.path.join(root, fn))

        invalid = []
        for path in files:
            html = open(path, 'r', encoding='utf-8', errors='replace').read()
            result, _ = parse_metadata_card(html)
            if result:
                ctx = extract_scholarly_context(result)
                if ctx["fiqh_madhab"] not in valid_madhabs:
                    invalid.append((os.path.basename(path), ctx["fiqh_madhab"]))

        assert len(invalid) == 0, f"Invalid madhabs: {invalid[:5]}"


# ─── Interactive multi-science input tests ────────────────────────────────

class TestCollectSciencePartsInteractive:
    """Test the interactive multi-science section collection."""

    def test_two_sections_normal_flow(self):
        """User adds two sections then presses Enter to finish."""
        from intake import collect_science_parts_interactive

        # Simulate: section1 name, science, desc, section2 name, science, desc, empty to finish
        inputs = iter([
            "القسم الأول", "nahw", "علم النحو",
            "القسم الثاني", "balagha", "علم البلاغة",
            "",  # finish
        ])
        with patch("builtins.input", lambda prompt: next(inputs)):
            result = collect_science_parts_interactive()

        assert len(result) == 2
        assert result[0] == {"section": "القسم الأول", "science_id": "nahw", "description": "علم النحو"}
        assert result[1] == {"section": "القسم الثاني", "science_id": "balagha", "description": "علم البلاغة"}

    def test_three_sections(self):
        """User adds three sections (like مفتاح العلوم)."""
        from intake import collect_science_parts_interactive

        inputs = iter([
            "الصرف", "sarf", "علم الصرف",
            "النحو", "nahw", "علم النحو",
            "البلاغة", "balagha", "المعاني والبيان والبديع",
            "",
        ])
        with patch("builtins.input", lambda prompt: next(inputs)):
            result = collect_science_parts_interactive()

        assert len(result) == 3
        assert [p["science_id"] for p in result] == ["sarf", "nahw", "balagha"]

    def test_rejects_finish_with_one_section(self):
        """User tries to finish after one section — forced to continue."""
        from intake import collect_science_parts_interactive

        inputs = iter([
            "القسم الأول", "nahw", "علم النحو",
            "",       # try to finish → rejected (< 2 sections)
            "القسم الثاني", "sarf", "علم الصرف",
            "",       # finish → accepted (2 sections)
        ])
        with patch("builtins.input", lambda prompt: next(inputs)):
            result = collect_science_parts_interactive()

        assert len(result) == 2

    def test_rejects_invalid_science_then_accepts_valid(self):
        """User types invalid science, gets prompted again."""
        from intake import collect_science_parts_interactive

        inputs = iter([
            "القسم الأول", "fiqh", "nahw", "علم النحو",  # fiqh rejected, nahw accepted
            "القسم الثاني", "balagha", "علم البلاغة",
            "",
        ])
        with patch("builtins.input", lambda prompt: next(inputs)):
            result = collect_science_parts_interactive()

        assert len(result) == 2
        assert result[0]["science_id"] == "nahw"
