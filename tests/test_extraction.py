#!/usr/bin/env python3
"""
Tests for Stage 3+4 Extraction (tools/extract_passages.py)

Run: python -m pytest tests/test_extraction.py -q
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure tools/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from extract_passages import (
    VALID_ATOM_TYPES,
    VALID_CASE_TYPES,
    VALID_CONTEXT_ROLES,
    VALID_CORE_ROLES,
    VALID_EXCERPT_KINDS,
    VALID_EXCLUSION_REASONS,
    VALID_RELATION_TYPES,
    VALID_SOURCE_LAYERS,
    VALID_TRIGGER_IDS,
    ATOM_ID_RE,
    EXCERPT_ID_RE,
    MODEL_PRICING,
    _extract_atom_id,
    _is_openai_model,
    _resolve_key_for_model,
    _normalize_atom_entries,
    _model_short,
    call_llm_dispatch,
    extract_taxonomy_leaves,
    generate_review_md,
    get_model_cost,
    get_passage_footnotes,
    get_passage_text,
    load_gold_example,
    post_process_extraction,
    repair_truncated_json,
    validate_extraction,
)


# ---------------------------------------------------------------------------
# Fixtures — reusable test data
# ---------------------------------------------------------------------------

SAMPLE_TAXONOMY_YAML = """\
al_hamza:
  al_hamza_awwal_al_kalima:
    _leaf: true
  al_hamza_wasat_al_kalima:
    al_hamza_wasat_al_kalima__overview:
      _leaf: true
    al_hala_1_tursam_alifan:
      _leaf: true
    al_hala_2_tursam_wawan:
      _leaf: true
  al_hamza_akhir_al_kalima:
    _leaf: true
al_madd:
  _leaf: true
"""


def _make_atom(atom_id, atom_type="prose_sentence", text="بسم الله الرحمن الرحيم.",
               is_prose_tail=False, bonded_cluster_trigger=None,
               source_layer="matn", book_id="qtest"):
    """Helper: build a well-formed atom record."""
    a = {
        "record_type": "atom",
        "atom_id": atom_id,
        "atom_type": atom_type,
        "source_layer": source_layer,
        "book_id": book_id,
        "text": text,
        "is_prose_tail": is_prose_tail,
        "bonded_cluster_trigger": bonded_cluster_trigger,
    }
    return a


def _make_excerpt(excerpt_id, core_atom_ids, taxonomy_node_id="al_madd",
                  context_atom_ids=None, case_types=None, source_layer="matn",
                  excerpt_title="Test excerpt", book_id="qtest"):
    """Helper: build a well-formed excerpt record."""
    core = [{"atom_id": aid, "role": "author_prose"} for aid in core_atom_ids]
    ctx = [{"atom_id": aid, "role": "preceding_setup"} for aid in (context_atom_ids or [])]
    return {
        "record_type": "excerpt",
        "excerpt_id": excerpt_id,
        "book_id": book_id,
        "excerpt_title": excerpt_title,
        "excerpt_title_reason": "test",
        "source_layer": source_layer,
        "excerpt_kind": "teaching",
        "taxonomy_version": "test_v0_1",
        "taxonomy_node_id": taxonomy_node_id,
        "taxonomy_path": "test > path",
        "heading_path": ["test"],
        "core_atoms": core,
        "context_atoms": ctx,
        "boundary_reasoning": "GROUPING: test. BOUNDARY: test. PLACEMENT: test.",
        "content_type": "prose",
        "case_types": case_types or ["A1_pure_definition", "B1_clean_boundary"],
        "relations": [],
        "status": "auto",
    }


def _well_formed_result():
    """Build a complete, valid extraction result."""
    atoms = [
        _make_atom("qtest:matn:000001", "heading", "باب الهمزة"),
        _make_atom("qtest:matn:000002", "prose_sentence", "للهمزة حالتان."),
        _make_atom("qtest:matn:000003", "bonded_cluster",
                   "1 - أن تكون مفتوحة، نحو: يأمر.",
                   bonded_cluster_trigger={"trigger_id": "T3", "reason": "colon leadin with نحو:"}),
    ]
    excerpts = [
        _make_excerpt("qtest:exc:000001", ["qtest:matn:000002"],
                      taxonomy_node_id="al_madd",
                      excerpt_title="حالتا الهمزة"),
        _make_excerpt("qtest:exc:000002", ["qtest:matn:000003"],
                      taxonomy_node_id="al_hala_1_tursam_alifan",
                      excerpt_title="الحالة الأولى"),
    ]
    exclusions = [
        {"record_type": "exclusion", "atom_id": "qtest:matn:000001",
         "book_id": "qtest", "exclusion_reason": "heading_structural"},
    ]
    return {
        "atoms": atoms,
        "excerpts": excerpts,
        "footnote_excerpts": [],
        "exclusions": exclusions,
        "notes": "",
    }


# ---------------------------------------------------------------------------
# Tests: extract_taxonomy_leaves
# ---------------------------------------------------------------------------

class TestExtractTaxonomyLeaves:
    def test_finds_all_leaves(self):
        leaves = extract_taxonomy_leaves(SAMPLE_TAXONOMY_YAML)
        assert "al_hamza_awwal_al_kalima" in leaves
        assert "al_hamza_wasat_al_kalima__overview" in leaves
        assert "al_hala_1_tursam_alifan" in leaves
        assert "al_hala_2_tursam_wawan" in leaves
        assert "al_hamza_akhir_al_kalima" in leaves
        assert "al_madd" in leaves
        assert len(leaves) == 6

    def test_excludes_non_leaves(self):
        leaves = extract_taxonomy_leaves(SAMPLE_TAXONOMY_YAML)
        assert "al_hamza" not in leaves
        assert "al_hamza_wasat_al_kalima" not in leaves

    def test_empty_yaml(self):
        leaves = extract_taxonomy_leaves("")
        assert leaves == set()

    def test_no_leaves(self):
        yaml_text = "root:\n  child:\n    grandchild: {}\n"
        leaves = extract_taxonomy_leaves(yaml_text)
        assert leaves == set()


# ---------------------------------------------------------------------------
# Tests: load_gold_example
# ---------------------------------------------------------------------------

class TestLoadGoldExample:
    def test_valid_path(self):
        gold_path = str(Path(__file__).resolve().parent.parent /
                        "3_extraction" / "gold" / "P004_gold_excerpt.json")
        if os.path.exists(gold_path):
            result = load_gold_example(gold_path)
            assert result  # non-empty string
            parsed = json.loads(result)
            assert "atoms" in parsed
            assert "excerpts" in parsed

    def test_missing_path(self):
        result = load_gold_example("/nonexistent/path.json")
        assert result == ""

    def test_none_path(self):
        result = load_gold_example(None)
        assert result == ""


# ---------------------------------------------------------------------------
# Tests: get_passage_text
# ---------------------------------------------------------------------------

class TestGetPassageText:
    def test_single_page(self):
        passage = {"start_seq_index": 5, "end_seq_index": 5}
        page_by_seq = {5: {"matn_text": "هذا نص."}}
        result = get_passage_text(passage, page_by_seq)
        assert result == "هذا نص."

    def test_multi_page(self):
        passage = {"start_seq_index": 2, "end_seq_index": 4}
        page_by_seq = {
            2: {"matn_text": "صفحة أولى."},
            3: {"matn_text": "صفحة ثانية."},
            4: {"matn_text": "صفحة ثالثة."},
        }
        result = get_passage_text(passage, page_by_seq)
        assert "صفحة أولى." in result
        assert "صفحة ثانية." in result
        assert "صفحة ثالثة." in result

    def test_missing_page(self):
        passage = {"start_seq_index": 1, "end_seq_index": 3}
        page_by_seq = {1: {"matn_text": "أ."}, 3: {"matn_text": "ج."}}
        result = get_passage_text(passage, page_by_seq)
        assert "أ." in result
        assert "ج." in result

    def test_empty_matn(self):
        passage = {"start_seq_index": 1, "end_seq_index": 1}
        page_by_seq = {1: {"matn_text": ""}}
        result = get_passage_text(passage, page_by_seq)
        assert result == ""


# ---------------------------------------------------------------------------
# Tests: get_passage_footnotes
# ---------------------------------------------------------------------------

class TestGetPassageFootnotes:
    def test_with_footnotes(self):
        passage = {"start_seq_index": 1, "end_seq_index": 1}
        page_by_seq = {1: {"footnotes": [
            {"number": "1", "text": "حاشية أولى"},
            {"number": "2", "text": "حاشية ثانية"},
        ]}}
        result = get_passage_footnotes(passage, page_by_seq)
        assert "[1] حاشية أولى" in result
        assert "[2] حاشية ثانية" in result

    def test_no_footnotes(self):
        passage = {"start_seq_index": 1, "end_seq_index": 1}
        page_by_seq = {1: {"footnotes": []}}
        result = get_passage_footnotes(passage, page_by_seq)
        assert result == "(none)"

    def test_missing_footnotes_key(self):
        passage = {"start_seq_index": 1, "end_seq_index": 1}
        page_by_seq = {1: {}}
        result = get_passage_footnotes(passage, page_by_seq)
        assert result == "(none)"


# ---------------------------------------------------------------------------
# Tests: _extract_atom_id / _normalize_atom_entries
# ---------------------------------------------------------------------------

class TestAtomEntryHelpers:
    def test_extract_from_string(self):
        assert _extract_atom_id("qtest:matn:000001") == "qtest:matn:000001"

    def test_extract_from_dict(self):
        assert _extract_atom_id({"atom_id": "qtest:matn:000001", "role": "evidence"}) == "qtest:matn:000001"

    def test_extract_from_dict_missing_key(self):
        assert _extract_atom_id({"role": "evidence"}) == ""

    def test_normalize_strings(self):
        entries = ["qtest:matn:000001", "qtest:matn:000002"]
        normalized = _normalize_atom_entries(entries, "author_prose")
        assert len(normalized) == 2
        assert normalized[0] == {"atom_id": "qtest:matn:000001", "role": "author_prose"}
        assert normalized[1] == {"atom_id": "qtest:matn:000002", "role": "author_prose"}

    def test_normalize_dicts_preserves_role(self):
        entries = [{"atom_id": "qtest:matn:000001", "role": "evidence"}]
        normalized = _normalize_atom_entries(entries, "author_prose")
        assert normalized[0]["role"] == "evidence"  # preserves, doesn't override

    def test_normalize_dicts_adds_default_role(self):
        entries = [{"atom_id": "qtest:matn:000001"}]
        normalized = _normalize_atom_entries(entries, "author_prose")
        assert normalized[0]["role"] == "author_prose"


# ---------------------------------------------------------------------------
# Tests: post_process_extraction
# ---------------------------------------------------------------------------

class TestPostProcessExtraction:
    def test_fixes_type_to_atom_type(self):
        result = {
            "atoms": [{"type": "prose_sentence", "atom_id": "x:m:000001", "text": "abc"}],
            "excerpts": [],
            "footnote_excerpts": [],
        }
        processed = post_process_extraction(result, "qtest", "imlaa")
        atom = processed["atoms"][0]
        assert "atom_type" in atom
        assert atom["atom_type"] == "prose_sentence"
        assert "type" not in atom

    def test_adds_record_type_and_book_id(self):
        result = {
            "atoms": [{"atom_type": "prose_sentence", "atom_id": "x:m:000001", "text": "abc"}],
            "excerpts": [{"excerpt_id": "x:exc:000001", "core_atoms": []}],
            "footnote_excerpts": [],
        }
        processed = post_process_extraction(result, "qbook", "imlaa")
        assert processed["atoms"][0]["record_type"] == "atom"
        assert processed["atoms"][0]["book_id"] == "qbook"
        assert processed["excerpts"][0]["record_type"] == "excerpt"
        assert processed["excerpts"][0]["book_id"] == "qbook"

    def test_normalizes_string_core_atoms(self):
        result = {
            "atoms": [{"atom_type": "prose_sentence", "atom_id": "x:m:000001", "text": "abc"}],
            "excerpts": [{"excerpt_id": "x:exc:000001",
                          "core_atoms": ["x:m:000001"],
                          "context_atoms": []}],
            "footnote_excerpts": [],
        }
        processed = post_process_extraction(result, "qtest", "imlaa")
        core = processed["excerpts"][0]["core_atoms"]
        assert isinstance(core[0], dict)
        assert core[0]["atom_id"] == "x:m:000001"
        assert core[0]["role"] == "author_prose"

    def test_normalizes_string_context_atoms(self):
        result = {
            "atoms": [{"atom_type": "prose_sentence", "atom_id": "x:m:000001", "text": "abc"}],
            "excerpts": [{"excerpt_id": "x:exc:000001",
                          "core_atoms": [],
                          "context_atoms": ["x:m:000001"]}],
            "footnote_excerpts": [],
        }
        processed = post_process_extraction(result, "qtest", "imlaa")
        ctx = processed["excerpts"][0]["context_atoms"]
        assert isinstance(ctx[0], dict)
        assert ctx[0]["role"] == "preceding_setup"

    def test_generates_heading_exclusion(self):
        result = {
            "atoms": [
                {"atom_type": "heading", "atom_id": "x:m:000001", "text": "باب"},
                {"atom_type": "prose_sentence", "atom_id": "x:m:000002", "text": "abc."},
            ],
            "excerpts": [],
            "footnote_excerpts": [],
        }
        processed = post_process_extraction(result, "qtest", "imlaa")
        exclusions = processed["exclusions"]
        heading_excl = [e for e in exclusions if e["atom_id"] == "x:m:000001"]
        assert len(heading_excl) == 1
        assert heading_excl[0]["exclusion_reason"] == "heading_structural"

    def test_generates_prose_tail_exclusion(self):
        result = {
            "atoms": [
                {"atom_type": "prose_sentence", "atom_id": "x:m:000001",
                 "text": "تابع.", "is_prose_tail": True},
            ],
            "excerpts": [],
            "footnote_excerpts": [],
        }
        processed = post_process_extraction(result, "qtest", "imlaa")
        exclusions = processed["exclusions"]
        tail_excl = [e for e in exclusions if e["atom_id"] == "x:m:000001"]
        assert len(tail_excl) == 1
        assert tail_excl[0]["exclusion_reason"] == "non_scholarly_apparatus"

    def test_does_not_duplicate_existing_exclusions(self):
        result = {
            "atoms": [
                {"atom_type": "heading", "atom_id": "x:m:000001", "text": "باب"},
            ],
            "excerpts": [],
            "footnote_excerpts": [],
            "exclusions": [
                {"atom_id": "x:m:000001", "exclusion_reason": "heading_structural"},
            ],
        }
        processed = post_process_extraction(result, "qtest", "imlaa")
        heading_excl = [e for e in processed["exclusions"]
                        if e["atom_id"] == "x:m:000001"]
        assert len(heading_excl) == 1  # not duplicated

    def test_normalizes_bonding_trigger_string(self):
        result = {
            "atoms": [{"atom_type": "bonded_cluster", "atom_id": "x:m:000001",
                        "text": "abc", "bonding_trigger": "T3"}],
            "excerpts": [],
            "footnote_excerpts": [],
        }
        processed = post_process_extraction(result, "qtest", "imlaa")
        trigger = processed["atoms"][0]["bonded_cluster_trigger"]
        assert isinstance(trigger, dict)
        assert trigger["trigger_id"] == "T3"

    def test_normalizes_old_bonding_trigger_key(self):
        result = {
            "atoms": [{"atom_type": "bonded_cluster", "atom_id": "x:m:000001",
                        "text": "abc", "bonding_trigger": {"trigger_id": "T1", "reason": "test"}}],
            "excerpts": [],
            "footnote_excerpts": [],
        }
        processed = post_process_extraction(result, "qtest", "imlaa")
        atom = processed["atoms"][0]
        assert "bonding_trigger" not in atom
        assert atom["bonded_cluster_trigger"]["trigger_id"] == "T1"

    def test_removes_role_from_atoms(self):
        result = {
            "atoms": [{"atom_type": "prose_sentence", "atom_id": "x:m:000001",
                        "text": "abc", "role": "author_prose"}],
            "excerpts": [],
            "footnote_excerpts": [],
        }
        processed = post_process_extraction(result, "qtest", "imlaa")
        assert "role" not in processed["atoms"][0]

    def test_derives_taxonomy_version(self):
        result = {
            "atoms": [],
            "excerpts": [{"excerpt_id": "x:exc:000001", "core_atoms": [],
                          "context_atoms": []}],
            "footnote_excerpts": [],
        }
        processed = post_process_extraction(result, "qtest", "imlaa",
                                             taxonomy_filename="imlaa_v0.1.yaml")
        assert processed["excerpts"][0]["taxonomy_version"] == "imlaa_v0_1"

    def test_sets_excerpt_defaults(self):
        result = {
            "atoms": [],
            "excerpts": [{"excerpt_id": "x:exc:000001", "core_atoms": [],
                          "context_atoms": []}],
            "footnote_excerpts": [],
        }
        processed = post_process_extraction(result, "qtest", "imlaa")
        exc = processed["excerpts"][0]
        assert exc["status"] == "auto"
        assert exc["source_layer"] == "matn"
        assert exc["cross_science_context"] is False
        assert exc["content_type"] == "prose"
        assert exc["relations"] == []


# ---------------------------------------------------------------------------
# Tests: validate_extraction — all pass
# ---------------------------------------------------------------------------

class TestValidateAllPass:
    def test_well_formed_passes(self):
        result = _well_formed_result()
        leaves = {"al_madd", "al_hala_1_tursam_alifan", "al_hamza_awwal_al_kalima"}
        issues = validate_extraction(result, "P001", leaves)
        assert issues["errors"] == [], f"Unexpected errors: {issues['errors']}"
        assert issues["warnings"] == [], f"Unexpected warnings: {issues['warnings']}"


# ---------------------------------------------------------------------------
# Tests: validate_extraction — individual failures
# ---------------------------------------------------------------------------

class TestValidateAtomRequiredFields:
    def test_missing_atom_id(self):
        result = _well_formed_result()
        # Remove atom_id from one atom
        del result["atoms"][1]["atom_id"]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("missing field 'atom_id'" in e for e in issues["errors"])

    def test_missing_atom_type(self):
        result = _well_formed_result()
        del result["atoms"][1]["atom_type"]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("missing atom_type" in e for e in issues["errors"])


class TestValidateAtomTextNonEmpty:
    def test_empty_text(self):
        result = _well_formed_result()
        result["atoms"][1]["text"] = ""
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("empty text" in e for e in issues["errors"])

    def test_whitespace_text(self):
        result = _well_formed_result()
        result["atoms"][1]["text"] = "   "
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("empty text" in e for e in issues["errors"])


class TestValidateAtomTypeValid:
    def test_invalid_type(self):
        result = _well_formed_result()
        result["atoms"][1]["atom_type"] = "invalid_type"
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("invalid atom_type" in w for w in issues["warnings"])


class TestValidateBondedClusterTrigger:
    def test_missing_trigger_on_bonded_cluster(self):
        result = _well_formed_result()
        result["atoms"][2]["bonded_cluster_trigger"] = None
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("missing bonded_cluster_trigger" in w for w in issues["warnings"])

    def test_invalid_trigger_id(self):
        result = _well_formed_result()
        result["atoms"][2]["bonded_cluster_trigger"] = {
            "trigger_id": "T99", "reason": "bad"
        }
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("invalid trigger_id" in w for w in issues["warnings"])

    def test_missing_reason(self):
        result = _well_formed_result()
        result["atoms"][2]["bonded_cluster_trigger"] = {
            "trigger_id": "T3", "reason": ""
        }
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("missing reason" in w for w in issues["warnings"])


class TestValidateExcerptRequiredFields:
    def test_missing_excerpt_id(self):
        result = _well_formed_result()
        del result["excerpts"][0]["excerpt_id"]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("missing field 'excerpt_id'" in e for e in issues["errors"])

    def test_missing_taxonomy_node_id(self):
        result = _well_formed_result()
        del result["excerpts"][0]["taxonomy_node_id"]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("missing field 'taxonomy_node_id'" in e for e in issues["errors"])

    def test_missing_boundary_reasoning(self):
        result = _well_formed_result()
        del result["excerpts"][0]["boundary_reasoning"]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("missing field 'boundary_reasoning'" in e for e in issues["errors"])

    def test_empty_case_types(self):
        result = _well_formed_result()
        result["excerpts"][0]["case_types"] = []
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("missing or empty case_types" in w for w in issues["warnings"])


class TestValidateReferenceIntegrity:
    def test_unknown_core_atom(self):
        result = _well_formed_result()
        result["excerpts"][0]["core_atoms"] = [
            {"atom_id": "qtest:matn:999999", "role": "author_prose"}
        ]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("unknown atom" in e for e in issues["errors"])

    def test_unknown_context_atom(self):
        result = _well_formed_result()
        result["excerpts"][0]["context_atoms"] = [
            {"atom_id": "qtest:matn:999999", "role": "preceding_setup"}
        ]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("context references unknown atom" in e for e in issues["errors"])


class TestValidateCoverage:
    def test_uncovered_atom(self):
        """Non-heading, non-prose_tail atom not in any excerpt's core_atoms."""
        result = _well_formed_result()
        # Add an atom that no excerpt covers
        result["atoms"].append(
            _make_atom("qtest:matn:000004", "prose_sentence", "نص غير مشمول.")
        )
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("Uncovered atoms" in e for e in issues["errors"])
        assert any("qtest:matn:000004" in e for e in issues["errors"])

    def test_heading_excluded_from_coverage(self):
        """Headings should NOT appear in uncovered atoms."""
        result = _well_formed_result()
        # The heading qtest:matn:000001 is excluded — should be fine
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert not any("qtest:matn:000001" in e for e in issues["errors"])

    def test_prose_tail_excluded_from_coverage(self):
        """Prose tail atoms should NOT appear in uncovered atoms."""
        result = _well_formed_result()
        result["atoms"].append(
            _make_atom("qtest:matn:000004", "prose_sentence",
                       "تابع من الصفحة السابقة.", is_prose_tail=True)
        )
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert not any("qtest:matn:000004" in e for e in issues["errors"])

    def test_footnote_atoms_excluded_from_coverage(self):
        """Footnote-layer atoms are handled by footnote_excerpts, not main excerpts."""
        result = _well_formed_result()
        result["atoms"].append(
            _make_atom("qtest:fn:000001", "prose_sentence",
                       "حاشية علمية.", source_layer="footnote")
        )
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert not any("qtest:fn:000001" in e for e in issues["errors"])


class TestValidateMultiCore:
    def test_atom_in_two_excerpts(self):
        result = _well_formed_result()
        # Put same atom in both excerpts
        result["excerpts"][1]["core_atoms"] = [
            {"atom_id": "qtest:matn:000002", "role": "author_prose"}
        ]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("core in both" in e for e in issues["errors"])


class TestValidateHeadingNeverInExcerpt:
    def test_heading_as_core(self):
        result = _well_formed_result()
        result["excerpts"][0]["core_atoms"].append(
            {"atom_id": "qtest:matn:000001", "role": "author_prose"}
        )
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("Heading atom" in e and "core" in e for e in issues["errors"])

    def test_heading_as_context(self):
        result = _well_formed_result()
        result["excerpts"][0]["context_atoms"].append(
            {"atom_id": "qtest:matn:000001", "role": "preceding_setup"}
        )
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("Heading atom" in e and "context" in e for e in issues["errors"])


class TestValidateLeafOnlyPlacement:
    def test_non_leaf_placement(self):
        result = _well_formed_result()
        result["excerpts"][0]["taxonomy_node_id"] = "al_hamza"  # a branch, not leaf
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("non-leaf" in w for w in issues["warnings"])

    def test_unmapped_allowed(self):
        result = _well_formed_result()
        result["excerpts"][0]["taxonomy_node_id"] = "_unmapped"
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert not any("non-leaf" in w for w in issues["warnings"])


class TestValidateCoreAtomRoles:
    def test_invalid_core_role(self):
        result = _well_formed_result()
        result["excerpts"][0]["core_atoms"] = [
            {"atom_id": "qtest:matn:000002", "role": "preceding_setup"}
        ]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("invalid role" in w for w in issues["warnings"])

    def test_missing_core_role(self):
        result = _well_formed_result()
        result["excerpts"][0]["core_atoms"] = [
            {"atom_id": "qtest:matn:000002", "role": ""}
        ]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("missing role" in w for w in issues["warnings"])


class TestValidateContextAtomRoles:
    def test_invalid_context_role(self):
        result = _well_formed_result()
        result["excerpts"][0]["context_atoms"] = [
            {"atom_id": "qtest:matn:000002", "role": "author_prose"}
        ]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("invalid role" in w for w in issues["warnings"])


class TestValidateCaseTypes:
    def test_invalid_case_type(self):
        result = _well_formed_result()
        result["excerpts"][0]["case_types"] = ["Z9_nonexistent"]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("invalid case_type" in w for w in issues["warnings"])

    def test_valid_case_types_pass(self):
        result = _well_formed_result()
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert not any("case_type" in w for w in issues["warnings"])


class TestValidateLayerIsolation:
    def test_mixed_layers(self):
        result = _well_formed_result()
        # Atom 000002 is matn; make excerpt footnote layer
        result["excerpts"][0]["source_layer"] = "footnote"
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("different layer" in w for w in issues["warnings"])


class TestValidateIdFormats:
    def test_bad_atom_id_format(self):
        result = _well_formed_result()
        result["atoms"][1]["atom_id"] = "bad-format"
        # Also update the excerpt reference
        result["excerpts"][0]["core_atoms"] = [
            {"atom_id": "bad-format", "role": "author_prose"}
        ]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("doesn't match expected format" in i for i in issues["info"])

    def test_bad_excerpt_id_format(self):
        result = _well_formed_result()
        result["excerpts"][0]["excerpt_id"] = "BAD-FORMAT"
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("doesn't match expected format" in i for i in issues["info"])


class TestValidateRelationTypes:
    def test_invalid_relation_type(self):
        result = _well_formed_result()
        result["excerpts"][0]["relations"] = [
            {"type": "nonexistent_relation", "target_excerpt_id": "qtest:exc:000002"}
        ]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert any("unknown relation type" in i for i in issues["info"])

    def test_valid_relation_type_passes(self):
        result = _well_formed_result()
        result["excerpts"][0]["relations"] = [
            {"type": "split_continues_in", "target_excerpt_id": "qtest:exc:000002"}
        ]
        issues = validate_extraction(result, "P001", {"al_madd", "al_hala_1_tursam_alifan"})
        assert not any("relation type" in i for i in issues["info"])


# ---------------------------------------------------------------------------
# Tests: gold P004 validates
# ---------------------------------------------------------------------------

class TestGoldP004Validates:
    def test_gold_passes_validation(self):
        gold_path = Path(__file__).resolve().parent.parent / \
                    "3_extraction" / "gold" / "P004_gold_excerpt.json"
        if not gold_path.exists():
            pytest.skip("Gold P004 file not found")

        with open(gold_path, encoding="utf-8") as f:
            gold = json.load(f)

        # Get taxonomy leaves
        tax_path = Path(__file__).resolve().parent.parent / "taxonomy" / "imlaa_v0.1.yaml"
        if not tax_path.exists():
            pytest.skip("Taxonomy file not found")
        with open(tax_path, encoding="utf-8") as f:
            tax_yaml = f.read()
        leaves = extract_taxonomy_leaves(tax_yaml)

        issues = validate_extraction(gold, "P004", leaves)
        # Gold should have zero errors
        assert issues["errors"] == [], \
            f"Gold P004 has validation errors: {issues['errors']}"
        # Warnings are acceptable in gold (info-level quirks)
        # but let's check there aren't many
        if issues["warnings"]:
            print(f"Gold P004 warnings (acceptable): {issues['warnings']}")


# ---------------------------------------------------------------------------
# Tests: generate_review_md
# ---------------------------------------------------------------------------

class TestGenerateReviewMd:
    def test_basic_output(self):
        result = _well_formed_result()
        passage = {
            "passage_id": "P001",
            "title": "Test Passage",
            "start_seq_index": 5,
            "end_seq_index": 6,
            "page_count": 2,
        }
        issues = {"errors": [], "warnings": [], "info": []}
        cost = {"input_tokens": 1000, "output_tokens": 500, "total_cost": 0.01}
        md = generate_review_md(passage, result, issues, cost)
        assert "# Extraction Review: P001" in md
        assert "All checks passed" in md
        assert "Atoms" in md
        assert "Excerpts" in md

    def test_shows_errors(self):
        result = _well_formed_result()
        passage = {
            "passage_id": "P001", "title": "Test",
            "start_seq_index": 1, "end_seq_index": 1, "page_count": 1,
        }
        issues = {
            "errors": ["Atom X missing field"],
            "warnings": ["Bad case_type"],
            "info": ["ID format hint"],
        }
        cost = {"input_tokens": 100, "output_tokens": 50, "total_cost": 0.001}
        md = generate_review_md(passage, result, issues, cost)
        assert "[ERROR]" in md
        assert "[WARN]" in md
        assert "[INFO]" in md

    def test_shows_retries(self):
        result = _well_formed_result()
        passage = {
            "passage_id": "P001", "title": "Test",
            "start_seq_index": 1, "end_seq_index": 1, "page_count": 1,
        }
        issues = {"errors": [], "warnings": [], "info": []}
        cost = {"input_tokens": 100, "output_tokens": 50, "total_cost": 0.001}
        md = generate_review_md(passage, result, issues, cost, retries=2)
        assert "Correction retries: 2" in md

    def test_shows_exclusions(self):
        result = _well_formed_result()
        passage = {
            "passage_id": "P001", "title": "Test",
            "start_seq_index": 1, "end_seq_index": 1, "page_count": 1,
        }
        issues = {"errors": [], "warnings": [], "info": []}
        cost = {"input_tokens": 100, "output_tokens": 50, "total_cost": 0.001}
        md = generate_review_md(passage, result, issues, cost)
        assert "Exclusions" in md
        assert "heading_structural" in md


# ---------------------------------------------------------------------------
# Tests: constants consistency
# ---------------------------------------------------------------------------

class TestConstants:
    def test_atom_id_regex(self):
        assert ATOM_ID_RE.match("qimlaa:matn:000001")
        assert ATOM_ID_RE.match("qtest:fn:000099")
        assert not ATOM_ID_RE.match("bad-format")
        assert not ATOM_ID_RE.match("qimlaa:matn:0001")  # too short
        assert not ATOM_ID_RE.match("")

    def test_excerpt_id_regex(self):
        assert EXCERPT_ID_RE.match("qimlaa:exc:000001")
        assert not EXCERPT_ID_RE.match("qimlaa:matn:000001")
        assert not EXCERPT_ID_RE.match("bad")

    def test_valid_atom_types_non_empty(self):
        assert len(VALID_ATOM_TYPES) >= 6

    def test_valid_trigger_ids(self):
        assert VALID_TRIGGER_IDS == {"T1", "T2", "T3", "T4", "T5", "T6"}

    def test_valid_core_roles(self):
        assert "author_prose" in VALID_CORE_ROLES
        assert "evidence" in VALID_CORE_ROLES

    def test_valid_context_roles(self):
        assert "preceding_setup" in VALID_CONTEXT_ROLES
        assert "classification_frame" in VALID_CONTEXT_ROLES

    def test_case_types_cover_all_series(self):
        prefixes = {ct[0] for ct in VALID_CASE_TYPES}
        assert prefixes == {"A", "B", "C", "D", "E"}

    def test_valid_excerpt_kinds(self):
        assert VALID_EXCERPT_KINDS == {"teaching", "exercise", "apparatus"}

    def test_valid_source_layers(self):
        assert "matn" in VALID_SOURCE_LAYERS
        assert "footnote" in VALID_SOURCE_LAYERS


# ---------------------------------------------------------------------------
# Tests: Multi-model support helpers
# ---------------------------------------------------------------------------

class TestGetModelCost:
    def test_claude_sonnet_cost(self):
        cost = get_model_cost("claude-sonnet-4-5-20250929", 1000, 500)
        expected = 1000 * 3 / 1_000_000 + 500 * 15 / 1_000_000
        assert abs(cost - expected) < 0.0001

    def test_openrouter_gpt4o_cost(self):
        cost = get_model_cost("openai/gpt-4o", 1000, 500)
        expected = 1000 * 2.5 / 1_000_000 + 500 * 10 / 1_000_000
        assert abs(cost - expected) < 0.0001

    def test_unknown_model_uses_default(self):
        cost = get_model_cost("unknown/model", 1000, 500)
        # Default is (3.0, 15.0) — same as Claude Sonnet
        expected = 1000 * 3 / 1_000_000 + 500 * 15 / 1_000_000
        assert abs(cost - expected) < 0.0001

    def test_zero_tokens(self):
        assert get_model_cost("claude-sonnet-4-5-20250929", 0, 0) == 0.0


class TestModelShort:
    def test_basic_truncation(self):
        short = _model_short("anthropic/claude-sonnet-4-5-20250929")
        assert len(short) <= 25
        assert "/" not in short
        assert "-" not in short

    def test_simple_model(self):
        short = _model_short("gpt-4o")
        assert short == "gpt4o"

    def test_model_with_slashes(self):
        short = _model_short("openai/gpt-4o")
        assert short == "openai_gpt4o"


class TestModelPricingRegistry:
    def test_all_entries_have_two_floats(self):
        for model, (inp, out) in MODEL_PRICING.items():
            assert isinstance(inp, (int, float)), f"{model} input not numeric"
            assert isinstance(out, (int, float)), f"{model} output not numeric"
            assert inp >= 0, f"{model} input price negative"
            assert out >= 0, f"{model} output price negative"

    def test_known_models_present(self):
        assert "claude-sonnet-4-5-20250929" in MODEL_PRICING
        assert "openai/gpt-4o" in MODEL_PRICING
        assert "anthropic/claude-sonnet-4-5-20250929" in MODEL_PRICING


# ========================================================================
# G02: extract_taxonomy_leaves handles v1 YAML format
# ========================================================================

class TestExtractTaxonomyLeavesV1:
    """G02: Leaf extraction must work with both v0 and v1 taxonomy YAML."""

    def test_v1_format(self):
        yaml_text = (
            "taxonomy:\n"
            "  id: imlaa_v1_0\n"
            "  nodes:\n"
            "  - id: muqaddimat\n"
            "    title: مقدمات\n"
            "    children:\n"
            "    - id: ta3rif_alimlaa_lugha\n"
            "      title: تعريف الإملاء لغة\n"
            "      leaf: true\n"
            "    - id: ta3rif_alimlaa_istilah\n"
            "      title: تعريف الإملاء اصطلاحا\n"
            "      leaf: true\n"
            "    - id: branch_node\n"
            "      title: فرع\n"
            "      children:\n"
            "      - id: deep_leaf\n"
            "        title: ورقة عميقة\n"
            "        leaf: true\n"
        )
        leaves = extract_taxonomy_leaves(yaml_text)
        assert "ta3rif_alimlaa_lugha" in leaves
        assert "ta3rif_alimlaa_istilah" in leaves
        assert "deep_leaf" in leaves
        # Branch nodes should NOT be leaves
        assert "muqaddimat" not in leaves
        assert "branch_node" not in leaves

    def test_v0_format_still_works(self):
        yaml_text = (
            "ta3rif_alimlaa_lugha:\n"
            "  _leaf: true\n"
            "mawdu3_alimlaa:\n"
            "  _leaf: true\n"
            "branch:\n"
            "  children:\n"
        )
        leaves = extract_taxonomy_leaves(yaml_text)
        assert "ta3rif_alimlaa_lugha" in leaves
        assert "mawdu3_alimlaa" in leaves
        assert "branch" not in leaves

    def test_real_v1_taxonomy_file(self):
        """Test against the actual imlaa v1 taxonomy file."""
        import os
        path = os.path.join("taxonomy", "imlaa", "imlaa_v1_0.yaml")
        if not os.path.exists(path):
            import pytest
            pytest.skip("v1 taxonomy file not found")
        with open(path, encoding="utf-8") as f:
            yaml_text = f.read()
        leaves = extract_taxonomy_leaves(yaml_text)
        # v1 imlaa has 105 leaves per CLAUDE.md
        assert len(leaves) >= 100, f"Expected ~105 leaves, got {len(leaves)}"
        # Spot check known leaves
        assert "ta3rif_alimlaa_lugha" in leaves

    def test_empty_yaml(self):
        assert extract_taxonomy_leaves("") == set()
        assert extract_taxonomy_leaves("# just a comment\n") == set()


# ========================================================================
# G04: repair_truncated_json backslash edge case
# ========================================================================

class TestRepairTruncatedJsonBackslash:
    """G04: Truncation right after a backslash inside a JSON string
    must not produce escaped-quote that breaks JSON."""

    def test_truncated_after_backslash(self):
        # Truncated right after \ inside a string
        text = '{"text": "some text\\'
        repaired = repair_truncated_json(text)
        # Should be parseable JSON
        import json
        parsed = json.loads(repaired)
        assert "text" in parsed

    def test_truncated_after_backslash_n(self):
        # \n is a complete escape — truncation after \n is fine
        text = '{"text": "line1\\nline2'
        repaired = repair_truncated_json(text)
        import json
        parsed = json.loads(repaired)
        assert "line1\nline2" == parsed["text"]

    def test_truncated_with_arabic_and_backslash(self):
        text = '{"atom_id": "q:m:001", "text": "وقد اختلف العلماء في هذ\\'
        repaired = repair_truncated_json(text)
        import json
        parsed = json.loads(repaired)
        assert "atom_id" in parsed


# ========================================================================
# G05: Correction prompt includes passage text
# ========================================================================

class TestCorrectionPromptHasPassageText:
    """G05: The correction prompt template must include passage_text."""

    def test_template_has_passage_text_field(self):
        from tools.extract_passages import CORRECTION_PROMPT
        assert "{passage_text}" in CORRECTION_PROMPT

    def test_attempt_correction_accepts_passage_text(self):
        """The function signature accepts passage_text parameter."""
        import inspect
        from tools.extract_passages import attempt_correction
        sig = inspect.signature(attempt_correction)
        assert "passage_text" in sig.parameters


# ========================================================================
# OpenAI direct API routing
# ========================================================================

class TestIsOpenaiModel:
    """_is_openai_model correctly identifies OpenAI model names."""

    def test_gpt4o(self):
        assert _is_openai_model("gpt-4o") is True

    def test_gpt4o_dated(self):
        assert _is_openai_model("gpt-4o-2024-08-06") is True

    def test_gpt41(self):
        assert _is_openai_model("gpt-4.1") is True

    def test_gpt41_mini(self):
        assert _is_openai_model("gpt-4.1-mini") is True

    def test_o1_prefix(self):
        assert _is_openai_model("o1-preview") is True

    def test_o3_prefix(self):
        assert _is_openai_model("o3-mini") is True

    def test_o4_prefix(self):
        assert _is_openai_model("o4-mini") is True

    def test_claude_not_openai(self):
        assert _is_openai_model("claude-sonnet-4-5-20250929") is False

    def test_openrouter_prefixed_not_detected(self):
        """OpenRouter-prefixed models should NOT match bare prefix check."""
        assert _is_openai_model("openai/gpt-4o") is False

    def test_anthropic_prefixed_not_detected(self):
        assert _is_openai_model("anthropic/claude-sonnet-4-5-20250929") is False


class TestOpenAIPricing:
    """MODEL_PRICING has entries for bare OpenAI model names."""

    def test_gpt4o_in_pricing(self):
        assert "gpt-4o" in MODEL_PRICING

    def test_gpt41_in_pricing(self):
        assert "gpt-4.1" in MODEL_PRICING

    def test_gpt4o_mini_in_pricing(self):
        assert "gpt-4o-mini" in MODEL_PRICING

    def test_cost_calculation(self):
        cost = get_model_cost("gpt-4o", 1000, 500)
        assert cost > 0


class TestCallLlmDispatchRouting:
    """call_llm_dispatch routes to the correct provider based on model name."""

    def test_openrouter_route_takes_priority(self):
        """OpenRouter-prefixed models route to OpenRouter when key present."""
        from unittest.mock import patch, MagicMock
        mock_resp = {"parsed": {}, "input_tokens": 0,
                     "output_tokens": 0, "stop_reason": "stop"}
        with patch("extract_passages.call_llm_openrouter",
                   return_value=mock_resp) as mock_or:
            call_llm_dispatch("sys", "usr", "anthropic/claude-sonnet-4-5-20250929",
                              "ant-key", openrouter_key="or-key")
            mock_or.assert_called_once()

    def test_openai_route(self):
        """Bare gpt-* models route to OpenAI when openai_key present."""
        from unittest.mock import patch, MagicMock
        mock_resp = {"parsed": {}, "input_tokens": 0,
                     "output_tokens": 0, "stop_reason": "stop"}
        with patch("extract_passages.call_llm_openai",
                   return_value=mock_resp) as mock_oa:
            call_llm_dispatch("sys", "usr", "gpt-4o", "ant-key",
                              openai_key="oa-key")
            mock_oa.assert_called_once_with("sys", "usr", "gpt-4o", "oa-key")

    def test_anthropic_fallback(self):
        """Non-OpenAI, non-OpenRouter models route to Anthropic."""
        from unittest.mock import patch, MagicMock
        mock_resp = {"parsed": {}, "input_tokens": 0,
                     "output_tokens": 0, "stop_reason": "stop"}
        with patch("extract_passages.call_llm",
                   return_value=mock_resp) as mock_ant:
            call_llm_dispatch("sys", "usr", "claude-sonnet-4-5-20250929",
                              "ant-key")
            mock_ant.assert_called_once_with("sys", "usr",
                                             "claude-sonnet-4-5-20250929",
                                             "ant-key")

    def test_openai_without_key_falls_to_anthropic(self):
        """If no openai_key, a gpt-* model falls through to Anthropic."""
        from unittest.mock import patch
        mock_resp = {"parsed": {}, "input_tokens": 0,
                     "output_tokens": 0, "stop_reason": "stop"}
        with patch("extract_passages.call_llm",
                   return_value=mock_resp) as mock_ant:
            call_llm_dispatch("sys", "usr", "gpt-4o", "ant-key")
            mock_ant.assert_called_once()


class TestAttemptCorrectionAcceptsOpenaiKey:
    """attempt_correction signature includes openai_key."""

    def test_signature_has_openai_key(self):
        import inspect
        from tools.extract_passages import attempt_correction
        sig = inspect.signature(attempt_correction)
        assert "openai_key" in sig.parameters


class TestExtractSingleModelAcceptsOpenaiKey:
    """extract_single_model signature includes openai_key."""

    def test_signature_has_openai_key(self):
        import inspect
        from tools.extract_passages import extract_single_model
        sig = inspect.signature(extract_single_model)
        assert "openai_key" in sig.parameters


class TestResolveKeyForModel:
    """_resolve_key_for_model returns the correct key per provider."""

    def test_anthropic_model_gets_anthropic_key(self):
        key = _resolve_key_for_model(
            "claude-sonnet-4-5-20250929", "ant-key",
            openrouter_key=None, openai_key="oa-key")
        assert key == "ant-key"

    def test_openai_model_gets_openai_key(self):
        key = _resolve_key_for_model(
            "gpt-4o", "ant-key",
            openrouter_key=None, openai_key="oa-key")
        assert key == "oa-key"

    def test_openrouter_model_gets_openrouter_key(self):
        key = _resolve_key_for_model(
            "anthropic/claude-sonnet-4-5-20250929", "ant-key",
            openrouter_key="or-key", openai_key="oa-key")
        assert key == "or-key"

    def test_openai_model_without_key_falls_to_anthropic(self):
        key = _resolve_key_for_model(
            "gpt-4o", "ant-key",
            openrouter_key=None, openai_key=None)
        assert key == "ant-key"

    def test_o1_model_gets_openai_key(self):
        key = _resolve_key_for_model(
            "o1-preview", "ant-key",
            openrouter_key=None, openai_key="oa-key")
        assert key == "oa-key"
