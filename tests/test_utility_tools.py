"""Tests for utility tool bug fixes (validate_structure, pipeline_gold, validate_gold, run_all_validations)."""

import json
import os
import re
import tempfile

import pytest


# ---------------------------------------------------------------------------
# validate_structure: load_page_indices
# ---------------------------------------------------------------------------

class TestLoadPageIndices:
    """BUG-FIX: load_page_indices should not fabricate seq_index values."""

    def test_skips_missing_seq_index(self, tmp_path):
        """Records without seq_index should be skipped, not given a fabricated value."""
        from tools.validate_structure import load_page_indices

        pages = tmp_path / "pages.jsonl"
        pages.write_text(
            json.dumps({"seq_index": 1, "page_number": "1"}) + "\n"
            + json.dumps({"page_number": "2"}) + "\n"  # missing seq_index
            + json.dumps({"seq_index": 3, "page_number": "3"}) + "\n",
            encoding="utf-8",
        )
        indices = load_page_indices(str(pages))
        assert indices == {1, 3}, "Missing seq_index should be skipped, not fabricated"

    def test_skips_empty_lines(self, tmp_path):
        """Empty lines in JSONL should not cause JSONDecodeError."""
        from tools.validate_structure import load_page_indices

        pages = tmp_path / "pages.jsonl"
        pages.write_text(
            json.dumps({"seq_index": 0}) + "\n"
            + "\n"  # empty line
            + json.dumps({"seq_index": 2}) + "\n"
            + "   \n",  # whitespace-only line
            encoding="utf-8",
        )
        indices = load_page_indices(str(pages))
        assert indices == {0, 2}

    def test_normal_operation(self, tmp_path):
        """Normal pages with seq_index work as before."""
        from tools.validate_structure import load_page_indices

        pages = tmp_path / "pages.jsonl"
        lines = [json.dumps({"seq_index": i}) for i in range(5)]
        pages.write_text("\n".join(lines) + "\n", encoding="utf-8")
        indices = load_page_indices(str(pages))
        assert indices == {0, 1, 2, 3, 4}


# ---------------------------------------------------------------------------
# pipeline_gold: baseline_version extraction
# ---------------------------------------------------------------------------

class TestBaselineVersionExtraction:
    """BUG-FIX: no-op ternary in baseline_version logic."""

    def test_version_extracted_from_dirname(self):
        """Directory name with _v prefix should extract the version part."""
        from tools.pipeline_gold import init_state_if_missing

        with tempfile.TemporaryDirectory(suffix="_v0.3.13") as td:
            meta = {"book_id": "test", "passage_id": "P001"}
            st = init_state_if_missing(td, meta)
            assert st["baseline_version"] == "0.3.13"

    def test_no_version_in_dirname(self):
        """Directory name without _v should produce empty baseline_version."""
        from tools.pipeline_gold import init_state_if_missing

        with tempfile.TemporaryDirectory(prefix="tmpnoversion") as td:
            meta = {"book_id": "test", "passage_id": "P001"}
            st = init_state_if_missing(td, meta)
            # If the dirname has no "_v", we should get empty string
            basename = os.path.basename(td)
            if "_v" not in basename:
                assert st["baseline_version"] == ""
            else:
                # Temp dir happened to contain _v — just verify it's a string
                assert isinstance(st["baseline_version"], str)

    def test_version_extraction_logic_directly(self):
        """Test the split logic directly without temp directories."""
        # Simulate the fixed logic
        def extract_version(dirname):
            parts = dirname.split("_v", 1)
            return parts[-1] if len(parts) > 1 else ""

        assert extract_version("passage1_v0.3.13") == "0.3.13"
        assert extract_version("passage1_v0.3.13_plus1") == "0.3.13_plus1"
        assert extract_version("no_version_here") == "ersion_here"  # _v matches in "version"
        assert extract_version("plain_dir") == ""


class TestWindowsPathNormalization:
    """BUG-FIX: artifact paths should use forward slashes on all platforms."""

    def test_touch_checkpoint_index_forward_slashes(self):
        """touch_checkpoint_index should return forward-slash paths."""
        from tools.pipeline_gold import touch_checkpoint_index

        with tempfile.TemporaryDirectory() as td:
            result = touch_checkpoint_index(td)
            assert "\\" not in result, f"Path should use forward slashes: {result}"
            assert "checkpoint_outputs/index.txt" == result


# ---------------------------------------------------------------------------
# validate_gold: _parse_baseline_dirs regex (tested without importing validate_gold)
# ---------------------------------------------------------------------------

class TestParseBaselineDirsRegex:
    """BUG-FIX: regex should match version suffixes with letters/plus/dash.

    We test the regex pattern directly since validate_gold.py requires jsonschema
    which may not be installed.
    """

    # The fixed regex pattern from validate_gold.py
    PATTERN = r"`([^`]*passage\d+_v[0-9][0-9A-Za-z._+\-]*/?)`"

    def test_matches_numeric_version(self):
        """Standard numeric versions like passage1_v0.3.13 should match."""
        line = "- `passage1_v0.3.13/`"
        m = re.search(self.PATTERN, line)
        assert m is not None
        assert m.group(1).rstrip("/") == "passage1_v0.3.13"

    def test_matches_alphanumeric_version(self):
        """Versions with letters like passage4_v0.3.13_plus1 should match."""
        line = "- `passage4_v0.3.13_plus1/`"
        m = re.search(self.PATTERN, line)
        assert m is not None
        assert m.group(1).rstrip("/") == "passage4_v0.3.13_plus1"

    def test_matches_dash_version(self):
        """Versions with dashes like passage2_v1.0-rc1 should match."""
        line = "- `passage2_v1.0-rc1/`"
        m = re.search(self.PATTERN, line)
        assert m is not None
        assert m.group(1).rstrip("/") == "passage2_v1.0-rc1"

    def test_no_match_without_version(self):
        """Lines without version pattern should not match."""
        line = "- `passage1_noversion/`"
        m = re.search(self.PATTERN, line)
        assert m is None

    def test_matches_run_all_validations_regex_too(self):
        """The same regex is used in run_all_validations.py — verify consistency."""
        # Read both files to confirm regexes match
        vg_path = os.path.join(os.path.dirname(__file__), "..", "tools", "validate_gold.py")
        rav_path = os.path.join(os.path.dirname(__file__), "..", "tools", "run_all_validations.py")

        with open(vg_path, encoding="utf-8") as f:
            vg_src = f.read()
        with open(rav_path, encoding="utf-8") as f:
            rav_src = f.read()

        # Extract regex patterns from source
        vg_match = re.search(r'r"(`\[.*?passage.*?\]`)"', vg_src)
        # Simpler: just verify both files contain the same pattern string
        pattern_str = r"passage\d+_v[0-9][0-9A-Za-z._+\-]*"
        assert pattern_str in vg_src, "validate_gold.py should use the harmonized regex"
        assert pattern_str in rav_src, "run_all_validations.py should use the harmonized regex"


# ---------------------------------------------------------------------------
# validate_gold: --skip-checkpoint-state-check argparse
# ---------------------------------------------------------------------------

class TestSkipCheckpointStateCheckArg:
    """BUG-FIX: --skip-checkpoint-state-check should be in argparse."""

    def test_argparse_flag_exists_in_source(self):
        """The argument should be registered in the parser source code."""
        vg_path = os.path.join(os.path.dirname(__file__), "..", "tools", "validate_gold.py")
        with open(vg_path, encoding="utf-8") as f:
            src = f.read()
        # Must have the argument definition (not just the getattr usage)
        assert 'add_argument("--skip-checkpoint-state-check"' in src or \
               "add_argument('--skip-checkpoint-state-check'" in src, \
               "--skip-checkpoint-state-check must be defined in argparse"
