#!/usr/bin/env python3
"""Tests for Stages 3+4: Extraction (tools/extract_passages.py).

Test strategy:
- Unit tests for file loaders (tempfile-based)
- Unit tests for text assembly (pure functions, inline dict data)
- Unit tests for taxonomy parsing (real + synthetic YAML)
- Validation invariant tests (the 6 checks — most important)
- JSON repair logic (extracted function)
- Review report generation (string containment checks)
- No API calls — only deterministic functions tested

Run: python -m pytest tests/test_extraction.py -v
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from extract_passages import (
    extract_taxonomy_leaves,
    generate_review_md,
    get_context_head,
    get_context_tail,
    get_passage_footnotes,
    get_passage_text,
    load_gold_example,
    load_jsonl,
    load_taxonomy_yaml,
    repair_truncated_json,
    validate_extraction,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = REPO_ROOT / "taxonomy" / "imlaa_v0.1.yaml"


# ---------------------------------------------------------------------------
# Helper functions for building test data
# ---------------------------------------------------------------------------

def make_page(seq_index, matn_text="", footnotes=None):
    return {
        "seq_index": seq_index,
        "volume": 1,
        "page_number_int": seq_index + 1,
        "matn_text": matn_text,
        "footnotes": footnotes or [],
    }


def make_passage(passage_id, start_seq, end_seq, title="test passage"):
    return {
        "passage_id": passage_id,
        "title": title,
        "heading_path": [title],
        "start_seq_index": start_seq,
        "end_seq_index": end_seq,
        "page_count": end_seq - start_seq + 1,
    }


def make_page_index(pages):
    return {p["seq_index"]: p for p in pages}


def make_atom(atom_id, atom_type="prose_sentence", text="نص عربي"):
    return {"atom_id": atom_id, "type": atom_type, "text": text}


def make_excerpt(excerpt_id, core_atoms, taxonomy_node_id, context_atoms=None):
    return {
        "excerpt_id": excerpt_id,
        "taxonomy_node_id": taxonomy_node_id,
        "core_atoms": core_atoms,
        "context_atoms": context_atoms or [],
        "boundary_reasoning": "test reasoning",
    }


def make_extraction_result(atoms, excerpts, footnote_excerpts=None):
    return {
        "atoms": atoms,
        "excerpts": excerpts,
        "footnote_excerpts": footnote_excerpts or [],
    }


# ---------------------------------------------------------------------------
# TestLoadJsonl
# ---------------------------------------------------------------------------

class TestLoadJsonl:
    def test_loads_valid_jsonl(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write('{"a": 1}\n{"b": 2}\n{"c": 3}\n')
            path = f.name
        try:
            result = load_jsonl(path)
            assert len(result) == 3
            assert result[0] == {"a": 1}
            assert result[2] == {"c": 3}
        finally:
            os.unlink(path)

    def test_skips_blank_lines(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write('{"a": 1}\n\n\n{"b": 2}\n   \n')
            path = f.name
        try:
            result = load_jsonl(path)
            assert len(result) == 2
        finally:
            os.unlink(path)

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write("")
            path = f.name
        try:
            result = load_jsonl(path)
            assert result == []
        finally:
            os.unlink(path)

    def test_arabic_text_preserved(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write('{"text": "بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ"}\n')
            path = f.name
        try:
            result = load_jsonl(path)
            assert result[0]["text"] == "بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ"
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# TestLoadTaxonomyYaml
# ---------------------------------------------------------------------------

class TestLoadTaxonomyYaml:
    def test_loads_raw_text(self):
        content = "imlaa:\n  leaf:\n    _leaf: true\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            path = f.name
        try:
            result = load_taxonomy_yaml(path)
            assert result == content
        finally:
            os.unlink(path)

    def test_preserves_comments_and_whitespace(self):
        content = "# Root\nimlaa:  # science\n  node:  # with comment\n    _leaf: true\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            path = f.name
        try:
            result = load_taxonomy_yaml(path)
            assert "# Root" in result
            assert "# science" in result
            assert "# with comment" in result
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# TestLoadGoldExample
# ---------------------------------------------------------------------------

class TestLoadGoldExample:
    def test_returns_empty_for_none(self):
        assert load_gold_example(None) == ""

    def test_returns_empty_for_missing_file(self):
        assert load_gold_example("/nonexistent/path/gold.json") == ""

    def test_loads_and_formats_gold(self):
        gold = {
            "atoms": [{"atom_id": "a1", "type": "heading", "text": "عنوان"}],
            "excerpts": [{"excerpt_id": "e1"}],
            "footnote_excerpts": [],
            "_comment": "should be excluded",
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(gold, f, ensure_ascii=False)
            path = f.name
        try:
            result = load_gold_example(path)
            parsed = json.loads(result)
            assert "atoms" in parsed
            assert "excerpts" in parsed
            assert "footnote_excerpts" in parsed
            assert "_comment" not in parsed
            assert parsed["atoms"][0]["text"] == "عنوان"
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# TestTextAssembly
# ---------------------------------------------------------------------------

class TestTextAssembly:
    # --- get_passage_text ---

    def test_single_page(self):
        pages = [make_page(5, matn_text="محتوى الصفحة")]
        passage = make_passage("P001", 5, 5)
        result = get_passage_text(passage, make_page_index(pages))
        assert result == "محتوى الصفحة"

    def test_multi_page_join(self):
        pages = [
            make_page(3, matn_text="صفحة ثلاثة"),
            make_page(4, matn_text="صفحة أربعة"),
            make_page(5, matn_text="صفحة خمسة"),
        ]
        passage = make_passage("P001", 3, 5)
        result = get_passage_text(passage, make_page_index(pages))
        assert result == "صفحة ثلاثة\n\nصفحة أربعة\n\nصفحة خمسة"

    def test_missing_page_skipped(self):
        pages = [make_page(3, matn_text="only page")]
        passage = make_passage("P001", 3, 5)  # pages 4,5 missing
        result = get_passage_text(passage, make_page_index(pages))
        assert result == "only page"

    def test_empty_matn_skipped(self):
        pages = [
            make_page(0, matn_text="real text"),
            make_page(1, matn_text=""),
            make_page(2, matn_text="more text"),
        ]
        passage = make_passage("P001", 0, 2)
        result = get_passage_text(passage, make_page_index(pages))
        assert result == "real text\n\nmore text"

    # --- get_passage_footnotes ---

    def test_collects_footnotes(self):
        pages = [
            make_page(0, footnotes=[
                {"number": 1, "text": "حاشية أولى"},
                {"number": 2, "text": "حاشية ثانية"},
            ]),
        ]
        passage = make_passage("P001", 0, 0)
        result = get_passage_footnotes(passage, make_page_index(pages))
        assert "[1] حاشية أولى" in result
        assert "[2] حاشية ثانية" in result

    def test_no_footnotes_returns_none_marker(self):
        pages = [make_page(0)]
        passage = make_passage("P001", 0, 0)
        result = get_passage_footnotes(passage, make_page_index(pages))
        assert result == "(none)"

    def test_multi_page_footnotes(self):
        pages = [
            make_page(0, footnotes=[{"number": 1, "text": "fn1"}]),
            make_page(1, footnotes=[]),
            make_page(2, footnotes=[{"number": 2, "text": "fn2"}]),
        ]
        passage = make_passage("P001", 0, 2)
        result = get_passage_footnotes(passage, make_page_index(pages))
        assert "[1] fn1" in result
        assert "[2] fn2" in result

    # --- get_context_tail ---

    def test_first_passage_returns_start_marker(self):
        passages = [make_passage("P001", 0, 0)]
        result = get_context_tail(passages, 0, {})
        assert result == "(start of book)"

    def test_tail_returns_last_n_chars(self):
        long_text = "أ" * 500
        pages = [make_page(0, matn_text=long_text)]
        passages = [make_passage("P001", 0, 0), make_passage("P002", 1, 1)]
        result = get_context_tail(passages, 1, make_page_index(pages), chars=300)
        assert len(result) == 300

    def test_tail_short_text_returned_in_full(self):
        pages = [make_page(0, matn_text="نص قصير")]
        passages = [make_passage("P001", 0, 0), make_passage("P002", 1, 1)]
        result = get_context_tail(passages, 1, make_page_index(pages))
        assert result == "نص قصير"

    # --- get_context_head ---

    def test_last_passage_returns_end_marker(self):
        passages = [make_passage("P001", 0, 0)]
        result = get_context_head(passages, 0, {})
        assert result == "(end of book)"

    def test_head_returns_first_n_chars(self):
        long_text = "ب" * 500
        pages = [make_page(1, matn_text=long_text)]
        passages = [make_passage("P001", 0, 0), make_passage("P002", 1, 1)]
        result = get_context_head(passages, 0, make_page_index(pages), chars=300)
        assert len(result) == 300


# ---------------------------------------------------------------------------
# TestExtractTaxonomyLeaves
# ---------------------------------------------------------------------------

class TestExtractTaxonomyLeaves:
    def test_simple_leaf(self):
        yaml = "root:\n  leaf_id:\n    _leaf: true\n"
        leaves = extract_taxonomy_leaves(yaml)
        assert leaves == {"leaf_id"}

    def test_multiple_leaves(self):
        yaml = (
            "root:\n"
            "  leaf1:\n"
            "    _leaf: true\n"
            "  parent:\n"
            "    leaf2:\n"
            "      _leaf: true\n"
            "    leaf3:\n"
            "      _leaf: true\n"
        )
        leaves = extract_taxonomy_leaves(yaml)
        assert leaves == {"leaf1", "leaf2", "leaf3"}

    def test_no_leaves_returns_empty(self):
        yaml = "root:\n  parent:\n    child:\n      _description: not a leaf\n"
        leaves = extract_taxonomy_leaves(yaml)
        assert leaves == set()

    def test_strips_comments(self):
        yaml = "root:\n  leaf_id:  # comment here\n    _leaf: true  # another\n"
        leaves = extract_taxonomy_leaves(yaml)
        assert "leaf_id" in leaves

    def test_skips_underscore_prefixed_keys(self):
        yaml = (
            "root:\n"
            "  real_leaf:\n"
            "    _description: blah\n"
            "    _leaf: true\n"
        )
        leaves = extract_taxonomy_leaves(yaml)
        assert "real_leaf" in leaves
        assert "_description" not in leaves

    def test_real_taxonomy_has_44_leaves(self):
        yaml_text = load_taxonomy_yaml(str(TAXONOMY_PATH))
        leaves = extract_taxonomy_leaves(yaml_text)
        assert len(leaves) == 44, f"Expected 44 leaves, got {len(leaves)}: {sorted(leaves)}"


# ---------------------------------------------------------------------------
# TestValidateExtraction — THE 6 INVARIANTS
# ---------------------------------------------------------------------------

class TestValidateExtraction:
    """Tests for the 6 validation invariants."""

    LEAVES = {"leaf_a", "leaf_b", "leaf_c"}

    # --- Invariant 1: Atom field completeness ---

    def test_valid_atoms_pass(self):
        result = make_extraction_result(
            atoms=[make_atom("a1")],
            excerpts=[make_excerpt("e1", ["a1"], "leaf_a")],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert len(issues) == 0

    def test_missing_atom_field_reported(self):
        result = make_extraction_result(
            atoms=[{"atom_id": "a1", "text": "text"}],  # missing 'type'
            excerpts=[make_excerpt("e1", ["a1"], "leaf_a")],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert any("missing field" in i.lower() or "type" in i for i in issues)

    # --- Invariant 2: Excerpt reference integrity ---

    def test_valid_references_pass(self):
        result = make_extraction_result(
            atoms=[make_atom("a1"), make_atom("a2", atom_type="heading")],
            excerpts=[make_excerpt("e1", ["a1"], "leaf_a", context_atoms=["a2"])],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert len(issues) == 0

    def test_unknown_core_atom_reported(self):
        result = make_extraction_result(
            atoms=[make_atom("a1")],
            excerpts=[make_excerpt("e1", ["a1", "a999"], "leaf_a")],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert any("a999" in i for i in issues)

    def test_unknown_context_atom_reported(self):
        result = make_extraction_result(
            atoms=[make_atom("a1")],
            excerpts=[make_excerpt("e1", ["a1"], "leaf_a", context_atoms=["a999"])],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert any("a999" in i for i in issues)

    # --- Invariant 3: Atom coverage ---

    def test_full_coverage_passes(self):
        result = make_extraction_result(
            atoms=[make_atom("a1"), make_atom("a2")],
            excerpts=[
                make_excerpt("e1", ["a1"], "leaf_a"),
                make_excerpt("e2", ["a2"], "leaf_b"),
            ],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert len(issues) == 0

    def test_uncovered_atom_reported(self):
        result = make_extraction_result(
            atoms=[make_atom("a1"), make_atom("a2")],
            excerpts=[make_excerpt("e1", ["a1"], "leaf_a")],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert any("Uncovered" in i or "uncovered" in i for i in issues)

    def test_heading_and_tail_excluded_from_coverage(self):
        """Headings and prose_tails should NOT trigger uncovered-atom issues."""
        result = make_extraction_result(
            atoms=[
                make_atom("a1", atom_type="heading", text="عنوان"),
                make_atom("a2", atom_type="prose_tail", text="ذيل"),
                make_atom("a3", atom_type="prose_sentence", text="جملة"),
            ],
            excerpts=[make_excerpt("e1", ["a3"], "leaf_a")],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert len(issues) == 0

    def test_placeholder_excluded_from_coverage(self):
        """Placeholder atoms (ellipses, OCR gaps) should NOT trigger uncovered-atom issues."""
        result = make_extraction_result(
            atoms=[
                make_atom("a1", atom_type="placeholder", text="…"),
                make_atom("a2", atom_type="prose_sentence", text="جملة"),
            ],
            excerpts=[make_excerpt("e1", ["a2"], "leaf_a")],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert len(issues) == 0

    def test_context_atom_counts_as_covered(self):
        """Atoms in context_atoms should count as covered (not trigger uncovered-atom issue)."""
        result = make_extraction_result(
            atoms=[make_atom("a1"), make_atom("a2")],
            excerpts=[make_excerpt("e1", ["a1"], "leaf_a", context_atoms=["a2"])],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert not any("Uncovered" in i or "uncovered" in i for i in issues)

    # --- Invariant 4: No double-counting ---

    def test_no_duplication_passes(self):
        result = make_extraction_result(
            atoms=[make_atom("a1"), make_atom("a2")],
            excerpts=[
                make_excerpt("e1", ["a1"], "leaf_a"),
                make_excerpt("e2", ["a2"], "leaf_b"),
            ],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert len(issues) == 0

    def test_double_core_reported(self):
        result = make_extraction_result(
            atoms=[make_atom("a1")],
            excerpts=[
                make_excerpt("e1", ["a1"], "leaf_a"),
                make_excerpt("e2", ["a1"], "leaf_b"),
            ],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert any("core in both" in i.lower() or "a1" in i for i in issues)

    # --- Invariant 5: Taxonomy leaf placement ---

    def test_valid_leaf_passes(self):
        result = make_extraction_result(
            atoms=[make_atom("a1")],
            excerpts=[make_excerpt("e1", ["a1"], "leaf_a")],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert len(issues) == 0

    def test_non_leaf_placement_reported(self):
        result = make_extraction_result(
            atoms=[make_atom("a1")],
            excerpts=[make_excerpt("e1", ["a1"], "nonexistent_parent")],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert any("non-leaf" in i.lower() or "nonexistent_parent" in i for i in issues)

    def test_path_style_id_auto_fixed(self):
        """Path-style IDs like 'root:parent:leaf_a' should be auto-fixed to 'leaf_a'."""
        result = make_extraction_result(
            atoms=[make_atom("a1")],
            excerpts=[make_excerpt("e1", ["a1"], "root:parent:leaf_a")],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        # Should NOT report a non-leaf issue (auto-fixed)
        assert not any("non-leaf" in i.lower() for i in issues)
        # The node ID should be auto-corrected
        assert result["excerpts"][0]["taxonomy_node_id"] == "leaf_a"

    def test_unmapped_is_allowed(self):
        result = make_extraction_result(
            atoms=[make_atom("a1")],
            excerpts=[make_excerpt("e1", ["a1"], "_unmapped")],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        # _unmapped should not trigger a leaf-placement issue
        assert not any("non-leaf" in i.lower() for i in issues)

    # --- Invariant 6: Excerpt field completeness ---

    def test_complete_excerpt_passes(self):
        result = make_extraction_result(
            atoms=[make_atom("a1")],
            excerpts=[make_excerpt("e1", ["a1"], "leaf_a")],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert len(issues) == 0

    def test_missing_excerpt_field_reported(self):
        result = make_extraction_result(
            atoms=[make_atom("a1")],
            excerpts=[{
                "excerpt_id": "e1",
                "taxonomy_node_id": "leaf_a",
                "core_atoms": ["a1"],
                # missing boundary_reasoning
            }],
        )
        issues = validate_extraction(result, "P001", self.LEAVES)
        assert any("missing field" in i.lower() or "boundary_reasoning" in i for i in issues)


# ---------------------------------------------------------------------------
# TestRepairTruncatedJson
# ---------------------------------------------------------------------------

class TestRepairTruncatedJson:
    def test_valid_json_unchanged(self):
        text = '{"atoms": [{"id": "a1"}]}'
        repaired = repair_truncated_json(text)
        assert json.loads(repaired) == json.loads(text)

    def test_closes_unclosed_string(self):
        text = '{"key": "hello'
        repaired = repair_truncated_json(text)
        parsed = json.loads(repaired)
        assert parsed["key"] == "hello"

    def test_closes_unclosed_brace(self):
        text = '{"a": {"b": 1}'
        repaired = repair_truncated_json(text)
        parsed = json.loads(repaired)
        assert parsed["a"]["b"] == 1

    def test_closes_unclosed_bracket(self):
        text = '{"items": [1, 2'
        repaired = repair_truncated_json(text)
        parsed = json.loads(repaired)
        assert parsed["items"] == [1, 2]

    def test_complex_truncation(self):
        """Simulate real LLM truncation at a comma boundary."""
        text = '{"atoms": [{"atom_id": "a1"}, {"atom_id": "a2"}'
        repaired = repair_truncated_json(text)
        parsed = json.loads(repaired)
        assert len(parsed["atoms"]) == 2

    def test_nested_structures(self):
        text = '{"atoms": [{"id": "a1"}'
        repaired = repair_truncated_json(text)
        parsed = json.loads(repaired)
        assert parsed["atoms"][0]["id"] == "a1"


# ---------------------------------------------------------------------------
# TestGenerateReviewMd
# ---------------------------------------------------------------------------

class TestGenerateReviewMd:
    def _make_inputs(self, issues=None):
        passage = make_passage("P004", 9, 9, title="الحالة الأولى")
        result = make_extraction_result(
            atoms=[
                make_atom("a1", "heading", "عنوان"),
                make_atom("a2", "prose_sentence", "جملة نثرية"),
                make_atom("a3", "bonded_cluster", "مجموعة مترابطة"),
            ],
            excerpts=[
                make_excerpt("e1", ["a2"], "leaf_a"),
                make_excerpt("e2", ["a3"], "leaf_b"),
            ],
        )
        cost = {"input_tokens": 5000, "output_tokens": 1500, "total_cost": 0.0375}
        return passage, result, issues or [], cost

    def test_contains_passage_header(self):
        passage, result, issues, cost = self._make_inputs()
        md = generate_review_md(passage, result, issues, cost)
        assert "# Extraction Review: P004" in md

    def test_contains_atom_markers(self):
        passage, result, issues, cost = self._make_inputs()
        md = generate_review_md(passage, result, issues, cost)
        assert "[heading]" in md
        assert "[prose_sentence]" in md
        assert "[bonded_cluster]" in md

    def test_validation_pass_section(self):
        passage, result, issues, cost = self._make_inputs(issues=[])
        md = generate_review_md(passage, result, issues, cost)
        assert "All checks passed" in md

    def test_validation_fail_section(self):
        issues = ["Uncovered atom a5", "Non-leaf placement at parent"]
        passage, result, _, cost = self._make_inputs()
        md = generate_review_md(passage, result, issues, cost)
        assert "Validation Issues (2)" in md
        assert "Uncovered atom a5" in md
        assert "Non-leaf placement at parent" in md
