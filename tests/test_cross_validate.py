"""Tests for tools/cross_validate.py — Cross-Validation Layers."""

import json
from pathlib import Path

import pytest

from tools.cross_validate import (
    _check_fields_algorithmic,
    _format_taxonomy_leaves,
    _parse_llm_json,
    validate_cross_book_consistency,
    validate_placement,
    validate_self_containment,
)
from tools.assemble_excerpts import TaxonomyNodeInfo


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_taxonomy_map() -> dict[str, TaxonomyNodeInfo]:
    """Small taxonomy map for testing."""
    return {
        "imlaa": TaxonomyNodeInfo(
            node_id="imlaa", title="علم الإملاء",
            path_ids=["imlaa"], path_titles=["علم الإملاء"],
            is_leaf=False, folder_path="imlaa",
        ),
        "alhamza": TaxonomyNodeInfo(
            node_id="alhamza", title="الهمزة",
            path_ids=["imlaa", "alhamza"], path_titles=["علم الإملاء", "الهمزة"],
            is_leaf=False, folder_path="imlaa/alhamza",
        ),
        "ta3rif_alhamza": TaxonomyNodeInfo(
            node_id="ta3rif_alhamza", title="تعريف الهمزة",
            path_ids=["imlaa", "alhamza", "ta3rif_alhamza"],
            path_titles=["علم الإملاء", "الهمزة", "تعريف الهمزة"],
            is_leaf=True, folder_path="imlaa/alhamza/ta3rif_alhamza",
        ),
        "hamzat_alwasl": TaxonomyNodeInfo(
            node_id="hamzat_alwasl", title="همزة الوصل",
            path_ids=["imlaa", "alhamza", "hamzat_alwasl"],
            path_titles=["علم الإملاء", "الهمزة", "همزة الوصل"],
            is_leaf=True, folder_path="imlaa/alhamza/hamzat_alwasl",
        ),
    }


def _write_extraction_file(ext_dir: Path, passage_id: str, excerpts: list[dict],
                           atoms: list[dict] | None = None):
    """Write a synthetic extraction file."""
    if atoms is None:
        atoms = [
            {"atom_id": "A001", "type": "prose_sentence", "text": "نص عربي للاختبار"},
            {"atom_id": "A002", "type": "prose_sentence", "text": "نص ثاني للاختبار"},
        ]
    passage = {
        "passage_id": passage_id,
        "filename": f"{passage_id}_extraction.json",
        "atoms": atoms,
        "excerpts": excerpts,
        "footnote_excerpts": [],
    }
    (ext_dir / f"{passage_id}_extraction.json").write_text(
        json.dumps(passage, ensure_ascii=False), encoding="utf-8",
    )


def _write_assembly_file(assembly_dir: Path, node_path: str, excerpt_data: dict):
    """Write a synthetic assembled excerpt file."""
    folder = assembly_dir / node_path
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{excerpt_data.get('excerpt_id', 'unknown')}.json"
    (folder / filename).write_text(
        json.dumps(excerpt_data, ensure_ascii=False), encoding="utf-8",
    )


SAMPLE_V1_YAML = """\
taxonomy:
  id: imlaa_v1_0
  title: "علم الإملاء"
  nodes:
    - id: imlaa
      title: "علم الإملاء"
      children:
        - id: alhamza
          title: "الهمزة"
          children:
            - id: ta3rif_alhamza
              title: "تعريف الهمزة"
              leaf: true
            - id: hamzat_alwasl
              title: "همزة الوصل"
              leaf: true
"""


# ==========================================================================
# Helpers tests
# ==========================================================================


class TestFormatTaxonomyLeaves:
    def test_formats_leaves_only(self):
        tax_map = _make_taxonomy_map()
        result = _format_taxonomy_leaves(tax_map)
        assert "ta3rif_alhamza" in result
        assert "hamzat_alwasl" in result
        # Non-leaves should not appear
        assert "- imlaa:" not in result
        assert "- alhamza:" not in result


class TestParseLlmJson:
    def test_parses_from_parsed_key(self):
        result = _parse_llm_json({"parsed": {"key": "value"}})
        assert result == {"key": "value"}

    def test_parses_from_raw_text(self):
        result = _parse_llm_json({"raw_text": '{"key": "value"}'})
        assert result == {"key": "value"}

    def test_handles_markdown_fences(self):
        result = _parse_llm_json({"raw_text": '```json\n{"key": "value"}\n```'})
        assert result == {"key": "value"}

    def test_returns_none_for_none(self):
        assert _parse_llm_json(None) is None

    def test_returns_none_for_invalid_json(self):
        assert _parse_llm_json({"raw_text": "not json"}) is None


class TestCheckFieldsAlgorithmic:
    def test_complete_excerpt_passes(self):
        data = {
            "excerpt_id": "E001",
            "full_text": "نص عربي طويل بما فيه الكفاية للاختبار",
            "book_title": "قواعد الإملاء",
            "author": "عبد السلام هارون",
            "taxonomy_path": "imlaa > alhamza > ta3rif_alhamza",
            "taxonomy_node_id": "ta3rif_alhamza",
            "source_pages": "19-20",
        }
        issues = _check_fields_algorithmic(data)
        assert issues == []

    def test_author_field_accepted(self):
        """Assembly uses 'author' not 'author_name' — should be accepted."""
        data = {
            "excerpt_id": "E001",
            "full_text": "نص عربي طويل بما فيه الكفاية للاختبار",
            "book_title": "قواعد الإملاء",
            "author": "عبد السلام هارون",
            "taxonomy_path": "imlaa > alhamza > ta3rif_alhamza",
            "taxonomy_node_id": "ta3rif_alhamza",
            "provenance": {"extraction_passage_id": "P004"},
        }
        issues = _check_fields_algorithmic(data)
        assert not any("author" in i.lower() for i in issues)
        assert not any("page" in i.lower() for i in issues)

    def test_provenance_satisfies_source_ref(self):
        """Provenance with extraction_passage_id should satisfy source ref check."""
        data = {
            "excerpt_id": "E001",
            "full_text": "نص عربي طويل بما فيه الكفاية للاختبار",
            "book_title": "قواعد الإملاء",
            "author": "مؤلف",
            "taxonomy_path": "x",
            "taxonomy_node_id": "x",
            "provenance": {"extraction_passage_id": "P004"},
        }
        issues = _check_fields_algorithmic(data)
        assert not any("page" in i.lower() for i in issues)

    def test_missing_text(self):
        data = {"excerpt_id": "E001", "book_title": "X", "taxonomy_path": "x",
                "taxonomy_node_id": "x", "source_pages": "1"}
        issues = _check_fields_algorithmic(data)
        assert any("text" in i.lower() for i in issues)

    def test_short_text(self):
        data = {"excerpt_id": "E001", "full_text": "قصير", "book_title": "X",
                "taxonomy_path": "x", "taxonomy_node_id": "x", "source_pages": "1"}
        issues = _check_fields_algorithmic(data)
        assert any("short" in i.lower() or "text" in i.lower() for i in issues)

    def test_missing_book_title(self):
        data = {"excerpt_id": "E001", "full_text": "x" * 30,
                "taxonomy_path": "x", "taxonomy_node_id": "x", "source_pages": "1"}
        issues = _check_fields_algorithmic(data)
        assert any("book_title" in i for i in issues)

    def test_missing_taxonomy_path(self):
        data = {"excerpt_id": "E001", "full_text": "x" * 30,
                "book_title": "X", "taxonomy_node_id": "x", "source_pages": "1"}
        issues = _check_fields_algorithmic(data)
        assert any("taxonomy_path" in i for i in issues)

    def test_missing_source_pages(self):
        data = {"excerpt_id": "E001", "full_text": "x" * 30,
                "book_title": "X", "taxonomy_path": "x", "taxonomy_node_id": "x"}
        issues = _check_fields_algorithmic(data)
        assert any("page" in i.lower() for i in issues)

    def test_missing_excerpt_id(self):
        data = {"full_text": "x" * 30, "book_title": "X",
                "taxonomy_path": "x", "taxonomy_node_id": "x", "source_pages": "1"}
        issues = _check_fields_algorithmic(data)
        assert any("excerpt_id" in i for i in issues)


# ==========================================================================
# Placement cross-validation tests
# ==========================================================================


class TestValidatePlacement:
    """Tests for validate_placement with mock LLM."""

    def test_agreement(self, tmp_path):
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()
        _write_extraction_file(ext_dir, "P001", [
            {
                "excerpt_id": "E001",
                "excerpt_title": "تعريف الهمزة",
                "taxonomy_node_id": "ta3rif_alhamza",
                "taxonomy_path": "imlaa > alhamza > ta3rif_alhamza",
                "core_atoms": ["A001"],
                "context_atoms": [],
            },
        ])

        tax_path = tmp_path / "taxonomy.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {
                "parsed": {
                    "chosen_node_id": "ta3rif_alhamza",
                    "chosen_node_path": "imlaa > alhamza > ta3rif_alhamza",
                    "confidence": "certain",
                    "reasoning": "Matches perfectly",
                },
                "input_tokens": 100,
                "output_tokens": 50,
            }

        report = validate_placement(
            extraction_dir=str(ext_dir),
            taxonomy_path=str(tax_path),
            science="imlaa",
            output_dir=str(tmp_path / "output"),
            call_llm_fn=mock_llm,
        )

        assert report["agreements"] == 1
        assert report["disagreements"] == 0
        assert report["results"][0]["status"] == "agreement"

        # Check report was saved
        assert (tmp_path / "output" / "placement_validation.json").exists()

    def test_disagreement(self, tmp_path):
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()
        _write_extraction_file(ext_dir, "P001", [
            {
                "excerpt_id": "E001",
                "excerpt_title": "همزة الوصل",
                "taxonomy_node_id": "ta3rif_alhamza",
                "taxonomy_path": "imlaa > alhamza > ta3rif_alhamza",
                "core_atoms": ["A001"],
                "context_atoms": [],
            },
        ])

        tax_path = tmp_path / "taxonomy.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {
                "parsed": {
                    "chosen_node_id": "hamzat_alwasl",
                    "chosen_node_path": "imlaa > alhamza > hamzat_alwasl",
                    "confidence": "likely",
                    "reasoning": "Discusses wasl hamza, not definition",
                },
                "input_tokens": 100,
                "output_tokens": 50,
            }

        report = validate_placement(
            extraction_dir=str(ext_dir),
            taxonomy_path=str(tax_path),
            science="imlaa",
            output_dir=str(tmp_path / "output"),
            call_llm_fn=mock_llm,
        )

        assert report["agreements"] == 0
        assert report["disagreements"] == 1
        assert report["results"][0]["status"] == "disagreement"
        assert report["results"][0]["validation_node"] == "hamzat_alwasl"

    def test_empty_extraction(self, tmp_path):
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()

        tax_path = tmp_path / "taxonomy.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        report = validate_placement(
            extraction_dir=str(ext_dir),
            taxonomy_path=str(tax_path),
            science="imlaa",
            output_dir=str(tmp_path / "output"),
        )
        assert report["status"] == "no_data"

    def test_llm_error_handling(self, tmp_path):
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()
        _write_extraction_file(ext_dir, "P001", [
            {
                "excerpt_id": "E001",
                "excerpt_title": "Test",
                "taxonomy_node_id": "ta3rif_alhamza",
                "core_atoms": ["A001"],
                "context_atoms": [],
            },
        ])

        tax_path = tmp_path / "taxonomy.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        def mock_llm_fail(system, user, model, key, openrouter_key=None, openai_key=None):
            raise RuntimeError("API error")

        report = validate_placement(
            extraction_dir=str(ext_dir),
            taxonomy_path=str(tax_path),
            science="imlaa",
            output_dir=str(tmp_path / "output"),
            call_llm_fn=mock_llm_fail,
        )
        assert report["error_count"] == 1
        assert report["results"][0]["status"] == "llm_error"

    def test_excerpt_id_filter(self, tmp_path):
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()
        _write_extraction_file(ext_dir, "P001", [
            {
                "excerpt_id": "E001",
                "excerpt_title": "A",
                "taxonomy_node_id": "ta3rif_alhamza",
                "core_atoms": ["A001"],
                "context_atoms": [],
            },
            {
                "excerpt_id": "E002",
                "excerpt_title": "B",
                "taxonomy_node_id": "hamzat_alwasl",
                "core_atoms": ["A002"],
                "context_atoms": [],
            },
        ])

        tax_path = tmp_path / "taxonomy.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        call_count = {"n": 0}

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            call_count["n"] += 1
            return {
                "parsed": {
                    "chosen_node_id": "ta3rif_alhamza",
                    "confidence": "certain",
                    "reasoning": "OK",
                },
                "input_tokens": 50,
                "output_tokens": 30,
            }

        report = validate_placement(
            extraction_dir=str(ext_dir),
            taxonomy_path=str(tax_path),
            science="imlaa",
            output_dir=str(tmp_path / "output"),
            call_llm_fn=mock_llm,
            excerpt_ids=["E001"],  # Only validate E001
        )
        assert call_count["n"] == 1
        assert report["total_excerpts"] == 1


# ==========================================================================
# Self-containment validation tests
# ==========================================================================


class TestValidateSelfContainment:
    """Tests for validate_self_containment."""

    def test_algorithmic_pass(self, tmp_path):
        assembly_dir = tmp_path / "assembled"
        _write_assembly_file(assembly_dir, "imlaa/alhamza/ta3rif_alhamza", {
            "excerpt_id": "E001",
            "full_text": "الهمزة هي حرف من حروف الهجاء العربية وتعريفها يشمل أنواعاً متعددة",
            "book_title": "قواعد الإملاء",
            "author_name": "عبد السلام هارون",
            "taxonomy_path": "imlaa > alhamza > ta3rif_alhamza",
            "taxonomy_node_id": "ta3rif_alhamza",
            "source_pages": "19-20",
        })

        report = validate_self_containment(
            assembly_dir=str(assembly_dir),
            output_dir=str(tmp_path / "output"),
        )

        assert report["pass_count"] == 1
        assert report["fail_count"] == 0
        assert report["results"][0]["status"] == "pass"
        assert (tmp_path / "output" / "self_containment_validation.json").exists()

    def test_algorithmic_fail_missing_fields(self, tmp_path):
        assembly_dir = tmp_path / "assembled"
        _write_assembly_file(assembly_dir, "imlaa/alhamza/ta3rif_alhamza", {
            "excerpt_id": "E001",
            # Missing full_text, book_title, taxonomy_path, etc.
        })

        report = validate_self_containment(
            assembly_dir=str(assembly_dir),
            output_dir=str(tmp_path / "output"),
        )

        assert report["fail_count"] == 1
        assert len(report["results"][0]["algorithmic_issues"]) > 0

    def test_llm_check_passes(self, tmp_path):
        assembly_dir = tmp_path / "assembled"
        _write_assembly_file(assembly_dir, "imlaa/alhamza/ta3rif_alhamza", {
            "excerpt_id": "E001",
            "full_text": "الهمزة هي حرف من حروف الهجاء العربية وتعريفها يشمل أنواعاً متعددة",
            "book_title": "قواعد الإملاء",
            "author_name": "عبد السلام هارون",
            "taxonomy_path": "imlaa > alhamza > ta3rif_alhamza",
            "taxonomy_node_id": "ta3rif_alhamza",
            "source_pages": "19-20",
        })

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {
                "parsed": {
                    "is_self_contained": True,
                    "issues": [],
                    "confidence": "certain",
                },
                "input_tokens": 100,
                "output_tokens": 50,
            }

        report = validate_self_containment(
            assembly_dir=str(assembly_dir),
            output_dir=str(tmp_path / "output"),
            model="test-model",
            call_llm_fn=mock_llm,
        )

        assert report["pass_count"] == 1
        assert report["results"][0]["llm_self_contained"] is True

    def test_llm_check_fails(self, tmp_path):
        assembly_dir = tmp_path / "assembled"
        _write_assembly_file(assembly_dir, "imlaa/alhamza/ta3rif_alhamza", {
            "excerpt_id": "E001",
            "full_text": "الهمزة هي حرف من حروف الهجاء العربية وتعريفها يشمل أنواعاً متعددة",
            "book_title": "قواعد الإملاء",
            "author_name": "عبد السلام هارون",
            "taxonomy_path": "imlaa > alhamza > ta3rif_alhamza",
            "taxonomy_node_id": "ta3rif_alhamza",
            "source_pages": "19-20",
        })

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {
                "parsed": {
                    "is_self_contained": False,
                    "issues": ["Missing scholarly context", "No school identified"],
                    "confidence": "likely",
                },
                "input_tokens": 100,
                "output_tokens": 50,
            }

        report = validate_self_containment(
            assembly_dir=str(assembly_dir),
            output_dir=str(tmp_path / "output"),
            model="test-model",
            call_llm_fn=mock_llm,
        )

        assert report["fail_count"] == 1
        assert len(report["results"][0]["llm_issues"]) == 2

    def test_nonexistent_assembly_dir(self, tmp_path):
        report = validate_self_containment(
            assembly_dir=str(tmp_path / "nonexistent"),
            output_dir=str(tmp_path / "output"),
        )
        assert report["status"] == "no_data"

    def test_skips_non_excerpt_files(self, tmp_path):
        assembly_dir = tmp_path / "assembled"
        assembly_dir.mkdir(parents=True)

        # Write a non-excerpt JSON file (no excerpt_id)
        (assembly_dir / "manifest.json").write_text(
            json.dumps({"type": "manifest", "version": "1.0"}),
            encoding="utf-8",
        )

        report = validate_self_containment(
            assembly_dir=str(assembly_dir),
            output_dir=str(tmp_path / "output"),
        )
        assert report["total_excerpts"] == 0


# ==========================================================================
# Cross-book consistency tests
# ==========================================================================


class TestValidateCrossBookConsistency:
    """Tests for validate_cross_book_consistency."""

    def test_coherent_node(self, tmp_path):
        assembly_dir = tmp_path / "assembled"

        # Two excerpts from different books at same node
        _write_assembly_file(assembly_dir, "imlaa/alhamza/ta3rif_alhamza", {
            "excerpt_id": "E001",
            "book_id": "book_a",
            "book_title": "كتاب أ",
            "taxonomy_node_id": "ta3rif_alhamza",
            "taxonomy_path": "imlaa > alhamza > ta3rif_alhamza",
            "full_text": "الهمزة حرف من حروف العربية",
        })
        _write_assembly_file(assembly_dir, "imlaa/alhamza/ta3rif_alhamza", {
            "excerpt_id": "E002",
            "book_id": "book_b",
            "book_title": "كتاب ب",
            "taxonomy_node_id": "ta3rif_alhamza",
            "taxonomy_path": "imlaa > alhamza > ta3rif_alhamza",
            "full_text": "تعريف الهمزة في اللغة",
        })

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {
                "parsed": {
                    "is_coherent": True,
                    "outlier_excerpt_ids": [],
                    "topic_description": "Definition of hamza",
                    "reasoning": "Both discuss hamza definition",
                },
                "input_tokens": 200,
                "output_tokens": 80,
            }

        report = validate_cross_book_consistency(
            assembly_dir=str(assembly_dir),
            output_dir=str(tmp_path / "output"),
            call_llm_fn=mock_llm,
        )

        assert report["coherent_count"] == 1
        assert report["incoherent_count"] == 0
        assert report["results"][0]["status"] == "coherent"
        assert (tmp_path / "output" / "cross_book_validation.json").exists()

    def test_incoherent_node(self, tmp_path):
        assembly_dir = tmp_path / "assembled"

        _write_assembly_file(assembly_dir, "imlaa/alhamza/ta3rif_alhamza", {
            "excerpt_id": "E001",
            "book_id": "book_a",
            "book_title": "كتاب أ",
            "taxonomy_node_id": "ta3rif_alhamza",
            "taxonomy_path": "imlaa > alhamza > ta3rif_alhamza",
            "full_text": "الهمزة حرف",
        })
        _write_assembly_file(assembly_dir, "imlaa/alhamza/ta3rif_alhamza", {
            "excerpt_id": "E002",
            "book_id": "book_b",
            "book_title": "كتاب ب",
            "taxonomy_node_id": "ta3rif_alhamza",
            "taxonomy_path": "imlaa > alhamza > ta3rif_alhamza",
            "full_text": "أحكام التاء المربوطة",
        })

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {
                "parsed": {
                    "is_coherent": False,
                    "outlier_excerpt_ids": ["E002"],
                    "topic_description": "Hamza definition",
                    "reasoning": "E002 discusses ta marbuta, not hamza",
                },
                "input_tokens": 200,
                "output_tokens": 80,
            }

        report = validate_cross_book_consistency(
            assembly_dir=str(assembly_dir),
            output_dir=str(tmp_path / "output"),
            call_llm_fn=mock_llm,
        )

        assert report["incoherent_count"] == 1
        assert report["results"][0]["outlier_excerpt_ids"] == ["E002"]

    def test_single_book_node_skipped(self, tmp_path):
        """Nodes with only one book should not be checked."""
        assembly_dir = tmp_path / "assembled"

        # Two excerpts but from same book
        _write_assembly_file(assembly_dir, "imlaa/alhamza/ta3rif_alhamza", {
            "excerpt_id": "E001",
            "book_id": "book_a",
            "book_title": "كتاب أ",
            "taxonomy_node_id": "ta3rif_alhamza",
            "full_text": "text 1",
        })
        _write_assembly_file(assembly_dir, "imlaa/alhamza/ta3rif_alhamza", {
            "excerpt_id": "E002",
            "book_id": "book_a",  # Same book
            "book_title": "كتاب أ",
            "taxonomy_node_id": "ta3rif_alhamza",
            "full_text": "text 2",
        })

        call_count = {"n": 0}

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            call_count["n"] += 1
            return {"parsed": {"is_coherent": True}}

        report = validate_cross_book_consistency(
            assembly_dir=str(assembly_dir),
            output_dir=str(tmp_path / "output"),
            call_llm_fn=mock_llm,
        )

        # Should not make any LLM calls
        assert call_count["n"] == 0
        assert report["total_nodes_checked"] == 0

    def test_empty_assembly(self, tmp_path):
        report = validate_cross_book_consistency(
            assembly_dir=str(tmp_path / "nonexistent"),
            output_dir=str(tmp_path / "output"),
        )
        assert report["status"] == "no_data"

    def test_llm_error_handling(self, tmp_path):
        assembly_dir = tmp_path / "assembled"

        _write_assembly_file(assembly_dir, "imlaa/alhamza/ta3rif_alhamza", {
            "excerpt_id": "E001",
            "book_id": "book_a",
            "taxonomy_node_id": "ta3rif_alhamza",
            "full_text": "text",
        })
        _write_assembly_file(assembly_dir, "imlaa/alhamza/ta3rif_alhamza", {
            "excerpt_id": "E002",
            "book_id": "book_b",
            "taxonomy_node_id": "ta3rif_alhamza",
            "full_text": "text",
        })

        def mock_llm_fail(system, user, model, key, openrouter_key=None, openai_key=None):
            raise RuntimeError("API error")

        report = validate_cross_book_consistency(
            assembly_dir=str(assembly_dir),
            output_dir=str(tmp_path / "output"),
            call_llm_fn=mock_llm_fail,
        )

        assert report["error_count"] == 1
        assert report["results"][0]["status"] == "llm_error"


# ==========================================================================
# Integration test
# ==========================================================================


class TestCrossValidationReportsStructure:
    """Verify all reports produce structured output consumable by human gate."""

    def test_placement_report_structure(self, tmp_path):
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()
        _write_extraction_file(ext_dir, "P001", [
            {
                "excerpt_id": "E001",
                "excerpt_title": "Test",
                "taxonomy_node_id": "ta3rif_alhamza",
                "core_atoms": ["A001"],
                "context_atoms": [],
            },
        ])

        tax_path = tmp_path / "taxonomy.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {"parsed": {"chosen_node_id": "ta3rif_alhamza",
                               "confidence": "certain", "reasoning": "OK"}}

        report = validate_placement(
            extraction_dir=str(ext_dir), taxonomy_path=str(tax_path),
            science="imlaa", output_dir=str(tmp_path / "output"),
            call_llm_fn=mock_llm,
        )

        # Verify structured keys
        assert "validation_type" in report
        assert "timestamp" in report
        assert "model" in report
        assert "results" in report
        assert isinstance(report["results"], list)
        for r in report["results"]:
            assert "excerpt_id" in r
            assert "status" in r

    def test_self_containment_report_structure(self, tmp_path):
        assembly_dir = tmp_path / "assembled"
        _write_assembly_file(assembly_dir, "x", {
            "excerpt_id": "E001", "full_text": "x" * 30,
            "book_title": "X", "taxonomy_path": "x",
            "taxonomy_node_id": "x", "source_pages": "1",
        })

        report = validate_self_containment(
            assembly_dir=str(assembly_dir),
            output_dir=str(tmp_path / "output"),
        )

        assert "validation_type" in report
        assert report["validation_type"] == "self_containment"
        assert "results" in report
        for r in report["results"]:
            assert "excerpt_id" in r
            assert "status" in r
            assert "algorithmic_issues" in r

    def test_cross_book_report_structure(self, tmp_path):
        assembly_dir = tmp_path / "assembled"
        for book_id in ["book_a", "book_b"]:
            _write_assembly_file(assembly_dir, "imlaa/alhamza/ta3rif_alhamza", {
                "excerpt_id": f"E-{book_id}",
                "book_id": book_id,
                "taxonomy_node_id": "ta3rif_alhamza",
                "full_text": "text",
            })

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {"parsed": {"is_coherent": True, "outlier_excerpt_ids": [],
                               "topic_description": "test", "reasoning": "OK"}}

        report = validate_cross_book_consistency(
            assembly_dir=str(assembly_dir),
            output_dir=str(tmp_path / "output"),
            call_llm_fn=mock_llm,
        )

        assert "validation_type" in report
        assert report["validation_type"] == "cross_book_consistency"
        assert "results" in report
        for r in report["results"]:
            assert "node_id" in r
            assert "status" in r
