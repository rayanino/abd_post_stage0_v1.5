"""
Tests for Multi-Model Consensus Engine (tools/consensus.py)

Run: python -m pytest tests/test_consensus.py -q
"""

import json
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tools.consensus import (
    strip_diacritics,
    normalize_for_comparison,
    char_ngrams,
    text_overlap_ratio,
    build_atom_lookup,
    compute_excerpt_text_span,
    match_excerpts,
    compute_coverage_agreement,
    compare_footnote_excerpts,
    compare_exclusions,
    compare_context_atoms,
    merge_footnote_excerpts,
    _normalize_confidence,
    _UNMAPPED_NODES,
    _model_tag,
    _remap_atom_refs,
    _merge_atoms_for_consensus,
    _optimal_assignment,
    _compute_arbiter_cost,
    build_consensus,
    generate_consensus_review_section,
    _extract_taxonomy_context,
    resolve_placement_disagreement,
)


# ---------------------------------------------------------------------------
# Test helpers — build well-formed extraction data
# ---------------------------------------------------------------------------

def _make_atom(atom_id, atom_type, text, **kwargs):
    """Build a minimal well-formed atom record."""
    atom = {
        "atom_id": atom_id,
        "atom_type": atom_type,
        "text": text,
        "source_layer": kwargs.get("source_layer", "matn"),
        "is_prose_tail": kwargs.get("is_prose_tail", False),
    }
    if atom_type == "bonded_cluster":
        atom["bonded_cluster_trigger"] = kwargs.get(
            "bonded_cluster_trigger",
            {"trigger_id": "T3", "reason": "test"},
        )
    atom.update({k: v for k, v in kwargs.items()
                 if k not in ("source_layer", "is_prose_tail", "bonded_cluster_trigger")})
    return atom


def _make_excerpt(excerpt_id, core_atom_ids, taxonomy_node_id="test_leaf", **kwargs):
    """Build a minimal well-formed excerpt record."""
    exc = {
        "excerpt_id": excerpt_id,
        "excerpt_title": kwargs.get("excerpt_title", "test excerpt"),
        "source_layer": kwargs.get("source_layer", "matn"),
        "excerpt_kind": kwargs.get("excerpt_kind", "teaching"),
        "taxonomy_node_id": taxonomy_node_id,
        "taxonomy_path": kwargs.get("taxonomy_path", f"science > {taxonomy_node_id}"),
        "core_atoms": [{"atom_id": aid, "role": "author_prose"} for aid in core_atom_ids],
        "context_atoms": kwargs.get("context_atoms", []),
        "boundary_reasoning": kwargs.get("boundary_reasoning", "test"),
        "content_type": kwargs.get("content_type", "prose"),
        "case_types": kwargs.get("case_types", ["A1_pure_definition"]),
        "relations": kwargs.get("relations", []),
    }
    exc.update({k: v for k, v in kwargs.items()
                if k not in ("excerpt_title", "source_layer", "excerpt_kind",
                             "taxonomy_path", "context_atoms", "boundary_reasoning",
                             "content_type", "case_types", "relations")})
    return exc


def _make_result(atoms, excerpts, footnote_excerpts=None, exclusions=None):
    """Build a minimal extraction result."""
    return {
        "atoms": atoms,
        "excerpts": excerpts,
        "footnote_excerpts": footnote_excerpts or [],
        "exclusions": exclusions or [],
        "notes": "",
    }


# ---------------------------------------------------------------------------
# Arabic test strings
# ---------------------------------------------------------------------------

# Simple Arabic text with diacritics
ARABIC_WITH_DIACRITICS = "بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ"
ARABIC_NO_DIACRITICS = "بسم الله الرحمن الرحيم"

# Longer passage segments
TEXT_HAMZA_OVERVIEW = "للهمزة حالتان في وسط الكلمة: أن تكون ساكنة، وأن تكون متحركة."
TEXT_HAMZA_CASE_1 = "الحالة الأولى: أن تكون الهمزة ساكنة بعد فتح، فتكتب على ألف."
TEXT_HAMZA_CASE_2 = "الحالة الثانية: أن تكون الهمزة ساكنة بعد ضم، فتكتب على واو."


# ---------------------------------------------------------------------------
# Tests: strip_diacritics
# ---------------------------------------------------------------------------

class TestStripDiacritics:
    def test_removes_fathah_kasrah_dammah(self):
        result = strip_diacritics(ARABIC_WITH_DIACRITICS)
        assert result == ARABIC_NO_DIACRITICS

    def test_no_diacritics_unchanged(self):
        text = "بسم الله"
        assert strip_diacritics(text) == text

    def test_empty_string(self):
        assert strip_diacritics("") == ""

    def test_removes_tatweel(self):
        assert strip_diacritics("كتـاب") == "كتاب"

    def test_non_arabic_unchanged(self):
        assert strip_diacritics("hello world") == "hello world"


# ---------------------------------------------------------------------------
# Tests: normalize_for_comparison
# ---------------------------------------------------------------------------

class TestNormalizeForComparison:
    def test_strips_diacritics_and_collapses_whitespace(self):
        text = "بِسْمِ   اللَّهِ   الرَّحْمَنِ"
        result = normalize_for_comparison(text)
        assert "بسم الله الرحمن" == result

    def test_trims_whitespace(self):
        assert normalize_for_comparison("  بسم  ") == "بسم"

    def test_empty(self):
        assert normalize_for_comparison("") == ""


# ---------------------------------------------------------------------------
# Tests: char_ngrams
# ---------------------------------------------------------------------------

class TestCharNgrams:
    def test_basic_ngrams(self):
        grams = char_ngrams("abcde", 3)
        assert grams == {"abc", "bcd", "cde"}

    def test_text_shorter_than_n(self):
        grams = char_ngrams("ab", 5)
        assert grams == {"ab"}

    def test_empty_string(self):
        assert char_ngrams("", 5) == set()

    def test_whitespace_collapsed(self):
        grams_a = char_ngrams("abc de", 3)
        grams_b = char_ngrams("abcde", 3)
        assert grams_a == grams_b

    def test_arabic_text(self):
        grams = char_ngrams("بسم الله", 3)
        # Whitespace collapsed: "بسمالله" -> 5 trigrams
        assert len(grams) == 5


# ---------------------------------------------------------------------------
# Tests: text_overlap_ratio
# ---------------------------------------------------------------------------

class TestTextOverlapRatio:
    def test_identical_texts(self):
        ratio = text_overlap_ratio(TEXT_HAMZA_OVERVIEW, TEXT_HAMZA_OVERVIEW)
        assert ratio == 1.0

    def test_completely_different(self):
        ratio = text_overlap_ratio("بسم الله الرحمن", "abcdefghij")
        assert ratio == 0.0

    def test_empty_a(self):
        assert text_overlap_ratio("", "some text") == 0.0

    def test_empty_b(self):
        assert text_overlap_ratio("some text", "") == 0.0

    def test_both_empty(self):
        assert text_overlap_ratio("", "") == 0.0

    def test_partial_overlap(self):
        text_a = "للهمزة حالتان في وسط الكلمة"
        text_b = "للهمزة حالتان في أول الكلمة"
        ratio = text_overlap_ratio(text_a, text_b)
        assert 0.3 < ratio < 0.9  # significant but not full overlap

    def test_diacritics_dont_tank_score(self):
        """Same text with/without diacritics should have ratio ~1.0."""
        ratio = text_overlap_ratio(ARABIC_WITH_DIACRITICS, ARABIC_NO_DIACRITICS)
        assert ratio > 0.95

    def test_same_text_different_whitespace(self):
        text_a = "بسم  الله   الرحمن"
        text_b = "بسم الله الرحمن"
        ratio = text_overlap_ratio(text_a, text_b)
        assert ratio == 1.0


# ---------------------------------------------------------------------------
# Tests: build_atom_lookup
# ---------------------------------------------------------------------------

class TestBuildAtomLookup:
    def test_builds_correct_mapping(self):
        atoms = [
            _make_atom("qa:matn:000001", "heading", "باب"),
            _make_atom("qa:matn:000002", "prose_sentence", "نص"),
        ]
        lookup = build_atom_lookup({"atoms": atoms})
        assert "qa:matn:000001" in lookup
        assert "qa:matn:000002" in lookup
        assert lookup["qa:matn:000002"]["text"] == "نص"

    def test_empty_atoms(self):
        assert build_atom_lookup({"atoms": []}) == {}

    def test_missing_atoms_key(self):
        assert build_atom_lookup({}) == {}


# ---------------------------------------------------------------------------
# Tests: compute_excerpt_text_span
# ---------------------------------------------------------------------------

class TestComputeExcerptTextSpan:
    def test_single_core_atom(self):
        atoms = {"a1": {"text": "نص عربي"}}
        exc = {"core_atoms": [{"atom_id": "a1", "role": "author_prose"}]}
        assert compute_excerpt_text_span(exc, atoms) == "نص عربي"

    def test_multiple_core_atoms(self):
        atoms = {
            "a1": {"text": "أولاً"},
            "a2": {"text": "ثانياً"},
        }
        exc = {"core_atoms": [
            {"atom_id": "a1", "role": "author_prose"},
            {"atom_id": "a2", "role": "evidence"},
        ]}
        assert compute_excerpt_text_span(exc, atoms) == "أولاً ثانياً"

    def test_missing_atom_skipped(self):
        atoms = {"a1": {"text": "found"}}
        exc = {"core_atoms": [
            {"atom_id": "a1", "role": "author_prose"},
            {"atom_id": "a2", "role": "author_prose"},  # missing
        ]}
        assert compute_excerpt_text_span(exc, atoms) == "found"

    def test_empty_core_atoms(self):
        assert compute_excerpt_text_span({"core_atoms": []}, {}) == ""

    def test_string_atom_ids(self):
        """Some outputs may have bare string IDs instead of objects."""
        atoms = {"a1": {"text": "text"}}
        exc = {"core_atoms": ["a1"]}
        assert compute_excerpt_text_span(exc, atoms) == "text"


# ---------------------------------------------------------------------------
# Tests: match_excerpts
# ---------------------------------------------------------------------------

def _make_model_a_result():
    """Model A: 3 atoms, 2 excerpts about hamza."""
    atoms = [
        _make_atom("qa:matn:000001", "heading", "باب الهمزة"),
        _make_atom("qa:matn:000002", "prose_sentence", TEXT_HAMZA_OVERVIEW),
        _make_atom("qa:matn:000003", "prose_sentence", TEXT_HAMZA_CASE_1),
    ]
    excerpts = [
        _make_excerpt("qa:exc:000001", ["qa:matn:000002"],
                       taxonomy_node_id="al_hamza_wasat__overview"),
        _make_excerpt("qa:exc:000002", ["qa:matn:000003"],
                       taxonomy_node_id="al_hala_1_tursam_alifan"),
    ]
    return _make_result(
        atoms, excerpts,
        exclusions=[{"atom_id": "qa:matn:000001", "exclusion_reason": "heading_structural"}],
    )


def _make_model_b_result_same_taxonomy():
    """Model B: different atom IDs, same text, same taxonomy placements."""
    atoms = [
        _make_atom("qb:matn:000001", "heading", "باب الهمزة"),
        _make_atom("qb:matn:000002", "prose_sentence", TEXT_HAMZA_OVERVIEW),
        _make_atom("qb:matn:000003", "prose_sentence", TEXT_HAMZA_CASE_1),
    ]
    excerpts = [
        _make_excerpt("qb:exc:000001", ["qb:matn:000002"],
                       taxonomy_node_id="al_hamza_wasat__overview"),
        _make_excerpt("qb:exc:000002", ["qb:matn:000003"],
                       taxonomy_node_id="al_hala_1_tursam_alifan"),
    ]
    return _make_result(
        atoms, excerpts,
        exclusions=[{"atom_id": "qb:matn:000001", "exclusion_reason": "heading_structural"}],
    )


def _make_model_b_result_different_taxonomy():
    """Model B: same text but DIFFERENT taxonomy placements."""
    atoms = [
        _make_atom("qb:matn:000001", "heading", "باب الهمزة"),
        _make_atom("qb:matn:000002", "prose_sentence", TEXT_HAMZA_OVERVIEW),
        _make_atom("qb:matn:000003", "prose_sentence", TEXT_HAMZA_CASE_1),
    ]
    excerpts = [
        _make_excerpt("qb:exc:000001", ["qb:matn:000002"],
                       taxonomy_node_id="al_hamza_wasat__overview"),  # same
        _make_excerpt("qb:exc:000002", ["qb:matn:000003"],
                       taxonomy_node_id="al_hala_2_tursam_wawan"),  # DIFFERENT
    ]
    return _make_result(
        atoms, excerpts,
        exclusions=[{"atom_id": "qb:matn:000001", "exclusion_reason": "heading_structural"}],
    )


def _make_model_b_result_extra_excerpt():
    """Model B: same as A plus an extra excerpt A didn't find."""
    atoms = [
        _make_atom("qb:matn:000001", "heading", "باب الهمزة"),
        _make_atom("qb:matn:000002", "prose_sentence", TEXT_HAMZA_OVERVIEW),
        _make_atom("qb:matn:000003", "prose_sentence", TEXT_HAMZA_CASE_1),
        _make_atom("qb:matn:000004", "prose_sentence", TEXT_HAMZA_CASE_2),
    ]
    excerpts = [
        _make_excerpt("qb:exc:000001", ["qb:matn:000002"],
                       taxonomy_node_id="al_hamza_wasat__overview"),
        _make_excerpt("qb:exc:000002", ["qb:matn:000003"],
                       taxonomy_node_id="al_hala_1_tursam_alifan"),
        _make_excerpt("qb:exc:000003", ["qb:matn:000004"],
                       taxonomy_node_id="al_hala_2_tursam_wawan"),
    ]
    return _make_result(atoms, excerpts)


class TestMatchExcerpts:
    def test_identical_outputs_all_matched(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_same_taxonomy()
        atoms_a = build_atom_lookup(ra)
        atoms_b = build_atom_lookup(rb)

        matched, un_a, un_b = match_excerpts(
            ra["excerpts"], rb["excerpts"], atoms_a, atoms_b
        )
        assert len(matched) == 2
        assert len(un_a) == 0
        assert len(un_b) == 0
        # Both should have same_taxonomy=True
        assert all(m["same_taxonomy"] for m in matched)

    def test_same_text_different_taxonomy(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_different_taxonomy()
        atoms_a = build_atom_lookup(ra)
        atoms_b = build_atom_lookup(rb)

        matched, un_a, un_b = match_excerpts(
            ra["excerpts"], rb["excerpts"], atoms_a, atoms_b
        )
        assert len(matched) == 2
        # First pair same taxonomy, second pair different
        tax_agreements = [m["same_taxonomy"] for m in matched]
        assert True in tax_agreements
        assert False in tax_agreements

    def test_extra_excerpt_in_model_b(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_extra_excerpt()
        atoms_a = build_atom_lookup(ra)
        atoms_b = build_atom_lookup(rb)

        matched, un_a, un_b = match_excerpts(
            ra["excerpts"], rb["excerpts"], atoms_a, atoms_b
        )
        assert len(matched) == 2
        assert len(un_a) == 0
        assert len(un_b) == 1  # the extra excerpt
        assert un_b[0]["excerpt_id"] == "qb:exc:000003"

    def test_completely_different_texts_no_match(self):
        atoms_a = [_make_atom("a1", "prose_sentence", "بسم الله الرحمن الرحيم")]
        atoms_b = [_make_atom("b1", "prose_sentence", "الحمد لله رب العالمين الرحمن الرحيم")]
        exc_a = [_make_excerpt("ea:001", ["a1"])]
        exc_b = [_make_excerpt("eb:001", ["b1"])]
        lookup_a = build_atom_lookup({"atoms": atoms_a})
        lookup_b = build_atom_lookup({"atoms": atoms_b})

        matched, un_a, un_b = match_excerpts(exc_a, exc_b, lookup_a, lookup_b)
        # These are different enough that they shouldn't match above threshold
        assert len(un_a) + len(un_b) >= 1

    def test_threshold_respected(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_same_taxonomy()
        atoms_a = build_atom_lookup(ra)
        atoms_b = build_atom_lookup(rb)

        # With threshold=0.99 and identical text, should still match
        matched, _, _ = match_excerpts(
            ra["excerpts"], rb["excerpts"], atoms_a, atoms_b, threshold=0.99
        )
        assert len(matched) == 2

    def test_empty_excerpts(self):
        matched, un_a, un_b = match_excerpts([], [], {}, {})
        assert matched == []
        assert un_a == []
        assert un_b == []

    def test_different_atom_boundaries_same_text(self):
        """Model A has 1 atom, Model B splits the same text into 2 atoms."""
        full_text = TEXT_HAMZA_CASE_1
        half1 = full_text[:len(full_text) // 2]
        half2 = full_text[len(full_text) // 2:]

        atoms_a = [_make_atom("a1", "prose_sentence", full_text)]
        atoms_b = [
            _make_atom("b1", "prose_sentence", half1),
            _make_atom("b2", "prose_sentence", half2),
        ]
        exc_a = [_make_excerpt("ea:001", ["a1"])]
        exc_b = [_make_excerpt("eb:001", ["b1", "b2"])]
        lookup_a = build_atom_lookup({"atoms": atoms_a})
        lookup_b = build_atom_lookup({"atoms": atoms_b})

        matched, un_a, un_b = match_excerpts(exc_a, exc_b, lookup_a, lookup_b)
        assert len(matched) == 1
        assert matched[0]["text_overlap"] > 0.8


# ---------------------------------------------------------------------------
# Tests: compute_coverage_agreement
# ---------------------------------------------------------------------------

class TestComputeCoverageAgreement:
    def test_identical_results(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_same_taxonomy()
        cov = compute_coverage_agreement(ra, rb)
        assert cov["coverage_agreement_ratio"] == 1.0

    def test_no_overlap(self):
        ra = _make_result(
            [_make_atom("a1", "prose_sentence", "بسم الله الرحمن الرحيم")],
            [_make_excerpt("ea:001", ["a1"])],
        )
        rb = _make_result(
            [_make_atom("b1", "prose_sentence", "abcdefghij klmnopqrst")],
            [_make_excerpt("eb:001", ["b1"])],
        )
        cov = compute_coverage_agreement(ra, rb)
        assert cov["coverage_agreement_ratio"] == 0.0

    def test_partial_overlap(self):
        shared = TEXT_HAMZA_OVERVIEW
        unique = TEXT_HAMZA_CASE_2

        ra = _make_result(
            [_make_atom("a1", "prose_sentence", shared)],
            [_make_excerpt("ea:001", ["a1"])],
        )
        rb = _make_result(
            [
                _make_atom("b1", "prose_sentence", shared),
                _make_atom("b2", "prose_sentence", unique),
            ],
            [_make_excerpt("eb:001", ["b1", "b2"])],
        )
        cov = compute_coverage_agreement(ra, rb)
        assert 0.0 < cov["coverage_agreement_ratio"] < 1.0

    def test_empty_results(self):
        ra = _make_result([], [])
        rb = _make_result([], [])
        cov = compute_coverage_agreement(ra, rb)
        assert cov["coverage_agreement_ratio"] == 1.0


# ---------------------------------------------------------------------------
# Tests: build_consensus
# ---------------------------------------------------------------------------

class TestBuildConsensusFullAgreement:
    def test_identical_outputs_high_confidence(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_same_taxonomy()
        issues_a = {"errors": [], "warnings": [], "info": []}
        issues_b = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o",
            issues_a, issues_b,
        )

        assert consensus["passage_id"] == "P004"
        assert len(consensus["excerpts"]) == 2
        meta = consensus["consensus_meta"]
        assert meta["full_agreement_count"] == 2
        assert meta["placement_disagreement_count"] == 0
        assert meta["unmatched_a_count"] == 0
        assert meta["unmatched_b_count"] == 0

        # All should be high confidence
        for pe in meta["per_excerpt"]:
            assert pe["confidence"] == "high"

    def test_winning_model_used_for_atoms(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_same_taxonomy()
        issues_a = {"errors": [], "warnings": [], "info": []}
        issues_b = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o",
            issues_a, issues_b,
        )
        # Default winning model is model_a (claude) since equal issues
        assert consensus["consensus_meta"]["winning_model"] == "claude"
        # Atoms should come from model A
        assert consensus["atoms"][0]["atom_id"].startswith("qa:")


class TestBuildConsensusPlacementDisagreement:
    def test_flags_placement_disagreement(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_different_taxonomy()
        issues_a = {"errors": [], "warnings": [], "info": []}
        issues_b = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o",
            issues_a, issues_b,
        )
        meta = consensus["consensus_meta"]
        assert meta["placement_disagreement_count"] == 1
        assert len(meta["disagreements"]) == 1
        assert meta["disagreements"][0]["type"] == "placement_disagreement"

    def test_no_arbiter_defaults_to_preferred(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_different_taxonomy()
        issues_a = {"errors": [], "warnings": [], "info": []}
        issues_b = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o",
            issues_a, issues_b,
            # No call_llm_fn → no arbiter
        )
        # H05: Disagreement with no arbiter should have "low" confidence
        # (uncertain decisions must surface in human review)
        meta = consensus["consensus_meta"]
        disagreement_excerpts = [
            pe for pe in meta["per_excerpt"]
            if pe["agreement"] == "placement_disagreement"
        ]
        assert len(disagreement_excerpts) == 1
        assert disagreement_excerpts[0]["confidence"] == "low"


class TestBuildConsensusUnmatchedExcerpts:
    def test_extra_excerpt_flagged(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_extra_excerpt()
        issues_a = {"errors": [], "warnings": [], "info": []}
        issues_b = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o",
            issues_a, issues_b,
        )
        meta = consensus["consensus_meta"]
        assert meta["unmatched_b_count"] == 1

        # The unmatched excerpt should be in the output with low confidence
        unmatched = [
            pe for pe in meta["per_excerpt"]
            if pe["agreement"] == "unmatched"
        ]
        assert len(unmatched) == 1
        assert unmatched[0]["confidence"] == "low"
        assert "gpt4o" in unmatched[0]["flags"][0]


class TestBuildConsensusModelPreference:
    def test_fewer_issues_wins(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_same_taxonomy()
        issues_a = {"errors": ["some error"], "warnings": [], "info": []}
        issues_b = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o",
            issues_a, issues_b,
        )
        assert consensus["consensus_meta"]["winning_model"] == "gpt4o"

    def test_explicit_prefer_overrides(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_same_taxonomy()
        issues_a = {"errors": ["error"], "warnings": [], "info": []}
        issues_b = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o",
            issues_a, issues_b,
            prefer_model="claude",
        )
        assert consensus["consensus_meta"]["winning_model"] == "claude"

    def test_tie_goes_to_model_a(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_same_taxonomy()
        issues_a = {"errors": [], "warnings": [], "info": []}
        issues_b = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o",
            issues_a, issues_b,
        )
        assert consensus["consensus_meta"]["winning_model"] == "claude"


class TestBuildConsensusWithArbiter:
    def test_arbiter_resolves_placement(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_different_taxonomy()
        issues_a = {"errors": [], "warnings": [], "info": []}
        issues_b = {"errors": [], "warnings": [], "info": []}

        # Mock arbiter that always picks model B's placement
        def mock_llm(system, user, model, api_key):
            return {
                "parsed": {
                    "correct_placement": "al_hala_2_tursam_wawan",
                    "reasoning": "Model B is correct because...",
                    "confidence": "certain",
                },
                "input_tokens": 100,
                "output_tokens": 50,
                "stop_reason": "end_turn",
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o",
            issues_a, issues_b,
            call_llm_fn=mock_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
            taxonomy_yaml="test:\n  al_hala_2_tursam_wawan:\n",
        )

        meta = consensus["consensus_meta"]
        # The arbiter should have resolved the disagreement
        assert len(meta["disagreements"]) == 1
        resolution = meta["disagreements"][0]["arbiter_resolution"]
        assert resolution["correct_placement"] == "al_hala_2_tursam_wawan"
        assert resolution["confidence"] == "certain"

    def test_arbiter_resolves_unmatched_keep(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_extra_excerpt()
        issues_a = {"errors": [], "warnings": [], "info": []}
        issues_b = {"errors": [], "warnings": [], "info": []}

        def mock_llm(system, user, model, api_key):
            return {
                "parsed": {
                    "verdict": "keep",
                    "reasoning": "This is a valid teaching unit.",
                    "confidence": "certain",
                },
                "input_tokens": 80,
                "output_tokens": 40,
                "stop_reason": "end_turn",
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o",
            issues_a, issues_b,
            call_llm_fn=mock_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
        )

        # Extra excerpt should still be in output (verdict=keep)
        assert len(consensus["excerpts"]) == 3  # 2 matched + 1 unmatched kept

    def test_arbiter_resolves_unmatched_discard(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_extra_excerpt()
        issues_a = {"errors": [], "warnings": [], "info": []}
        issues_b = {"errors": [], "warnings": [], "info": []}

        def mock_llm(system, user, model, api_key):
            return {
                "parsed": {
                    "verdict": "discard",
                    "reasoning": "Not a valid teaching unit.",
                    "confidence": "certain",
                },
                "input_tokens": 80,
                "output_tokens": 40,
                "stop_reason": "end_turn",
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o",
            issues_a, issues_b,
            call_llm_fn=mock_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
        )

        # Extra excerpt should NOT be in output (verdict=discard)
        assert len(consensus["excerpts"]) == 2  # only matched excerpts

    def test_arbiter_failure_falls_back(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_different_taxonomy()
        issues_a = {"errors": [], "warnings": [], "info": []}
        issues_b = {"errors": [], "warnings": [], "info": []}

        def failing_llm(system, user, model, api_key):
            raise RuntimeError("API error")

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o",
            issues_a, issues_b,
            call_llm_fn=failing_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
        )

        # Should still produce output, falling back to preferred model
        assert len(consensus["excerpts"]) == 2
        meta = consensus["consensus_meta"]
        resolution = meta["disagreements"][0]["arbiter_resolution"]
        assert resolution["confidence"] == "uncertain"
        assert "failed" in resolution["reasoning"].lower()


# ---------------------------------------------------------------------------
# Tests: generate_consensus_review_section
# ---------------------------------------------------------------------------

class TestGenerateConsensusReviewSection:
    def test_high_confidence_all_agreed(self):
        meta = {
            "mode": "consensus",
            "model_a": "claude",
            "model_b": "gpt4o",
            "winning_model": "claude",
            "matched_count": 2,
            "full_agreement_count": 2,
            "placement_disagreement_count": 0,
            "unmatched_a_count": 0,
            "unmatched_b_count": 0,
            "coverage_agreement": {"coverage_agreement_ratio": 1.0},
            "arbiter_cost": {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0},
            "disagreements": [],
            "per_excerpt": [
                {"excerpt_id": "e1", "confidence": "high", "source_model": "claude",
                 "agreement": "full", "flags": []},
                {"excerpt_id": "e2", "confidence": "high", "source_model": "claude",
                 "agreement": "full", "flags": []},
            ],
        }
        md = generate_consensus_review_section(meta)
        assert "Multi-Model Consensus" in md
        assert "Full agreement" in md
        assert "100.0%" in md

    def test_mixed_confidence_with_disagreements(self):
        meta = {
            "mode": "consensus",
            "model_a": "claude",
            "model_b": "gpt4o",
            "winning_model": "claude",
            "matched_count": 2,
            "full_agreement_count": 1,
            "placement_disagreement_count": 1,
            "unmatched_a_count": 0,
            "unmatched_b_count": 1,
            "coverage_agreement": {"coverage_agreement_ratio": 0.85},
            "arbiter_cost": {"input_tokens": 100, "output_tokens": 50, "total_cost": 0.001},
            "disagreements": [
                {
                    "type": "placement_disagreement",
                    "model_a_placement": "node_a",
                    "model_b_placement": "node_b",
                    "text_overlap": 0.92,
                    "arbiter_resolution": {
                        "correct_placement": "node_b",
                        "reasoning": "because...",
                        "confidence": "certain",
                    },
                },
            ],
            "per_excerpt": [
                {"excerpt_id": "e1", "confidence": "high", "source_model": "claude",
                 "agreement": "full", "flags": []},
                {"excerpt_id": "e2", "confidence": "high", "source_model": "gpt4o",
                 "agreement": "placement_disagreement",
                 "flags": ["Placement disagreement"]},
            ],
        }
        md = generate_consensus_review_section(meta)
        assert "Disagreement Details" in md
        assert "placement_disagreement" in md
        assert "Arbiter Cost" in md

    def test_empty_consensus(self):
        meta = {
            "mode": "consensus",
            "model_a": "claude",
            "model_b": "gpt4o",
            "winning_model": "claude",
            "matched_count": 0,
            "full_agreement_count": 0,
            "placement_disagreement_count": 0,
            "unmatched_a_count": 0,
            "unmatched_b_count": 0,
            "coverage_agreement": {"coverage_agreement_ratio": 1.0},
            "arbiter_cost": {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0},
            "disagreements": [],
            "per_excerpt": [],
        }
        md = generate_consensus_review_section(meta)
        assert "Multi-Model Consensus" in md


# ---------------------------------------------------------------------------
# Tests: _extract_taxonomy_context
# ---------------------------------------------------------------------------

class TestExtractTaxonomyContext:
    def test_extracts_surrounding_lines(self):
        yaml = "root:\n  branch_a:\n    leaf_x:\n    leaf_y:\n  branch_b:\n    leaf_z:"
        ctx = _extract_taxonomy_context(yaml, "leaf_x", "leaf_z")
        assert "leaf_x" in ctx
        assert "leaf_z" in ctx

    def test_missing_nodes(self):
        yaml = "root:\n  branch:\n    leaf:"
        ctx = _extract_taxonomy_context(yaml, "nonexistent_a", "nonexistent_b")
        assert "not found" in ctx


# ---------------------------------------------------------------------------
# Tests: consensus_meta structure
# ---------------------------------------------------------------------------

class TestConsensusMetaStructure:
    def test_contains_required_fields(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_same_taxonomy()
        issues = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        meta = consensus["consensus_meta"]

        required_fields = [
            "mode", "model_a", "model_b", "winning_model",
            "matched_count", "full_agreement_count",
            "placement_disagreement_count", "unmatched_a_count",
            "unmatched_b_count", "coverage_agreement",
            "arbiter_cost", "disagreements", "per_excerpt",
        ]
        for field in required_fields:
            assert field in meta, f"Missing field: {field}"

    def test_serializable_to_json(self):
        """consensus_meta must be JSON-serializable."""
        import json
        ra = _make_model_a_result()
        rb = _make_model_b_result_extra_excerpt()
        issues = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        # This should not raise
        json_str = json.dumps(consensus, ensure_ascii=False)
        assert len(json_str) > 0

    def test_new_hardened_fields_present(self):
        """consensus_meta must include hardened fields."""
        ra = _make_model_a_result()
        rb = _make_model_b_result_same_taxonomy()
        issues = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        meta = consensus["consensus_meta"]

        hardened_fields = [
            "both_unmapped_count", "discarded_excerpts",
            "footnote_comparison", "exclusion_comparison",
            "case_type_disagreements",
        ]
        for field in hardened_fields:
            assert field in meta, f"Missing hardened field: {field}"


# ===========================================================================
# STRESS TESTS — hardened edge cases
# ===========================================================================

# ---------------------------------------------------------------------------
# Stress: null / missing core_atoms
# ---------------------------------------------------------------------------

class TestExcerptWithNullCoreAtoms:
    """compute_excerpt_text_span must handle None and missing core_atoms."""

    def test_core_atoms_is_none(self):
        exc = {"core_atoms": None}
        assert compute_excerpt_text_span(exc, {}) == ""

    def test_core_atoms_key_missing(self):
        exc = {}  # no core_atoms key at all
        assert compute_excerpt_text_span(exc, {}) == ""

    def test_consensus_with_null_core_atoms_excerpt(self):
        """build_consensus should not crash when an excerpt has null core_atoms."""
        atoms_a = [_make_atom("a1", "prose_sentence", TEXT_HAMZA_OVERVIEW)]
        exc_a_ok = _make_excerpt("ea:001", ["a1"], taxonomy_node_id="leaf_a")
        exc_a_null = {
            "excerpt_id": "ea:002",
            "taxonomy_node_id": "leaf_b",
            "core_atoms": None,
        }
        ra = _make_result(atoms_a, [exc_a_ok, exc_a_null])

        atoms_b = [_make_atom("b1", "prose_sentence", TEXT_HAMZA_OVERVIEW)]
        exc_b = _make_excerpt("eb:001", ["b1"], taxonomy_node_id="leaf_a")
        rb = _make_result(atoms_b, [exc_b])

        issues = {"errors": [], "warnings": [], "info": []}
        # Should not raise
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        assert "excerpts" in consensus


# ---------------------------------------------------------------------------
# Stress: both models _unmapped
# ---------------------------------------------------------------------------

class TestBothModelsUnmapped:
    """When both models place at _unmapped, it's a classification failure."""

    def test_both_unmapped_flagged(self):
        atoms_a = [_make_atom("a1", "prose_sentence", TEXT_HAMZA_OVERVIEW)]
        atoms_b = [_make_atom("b1", "prose_sentence", TEXT_HAMZA_OVERVIEW)]
        exc_a = _make_excerpt("ea:001", ["a1"], taxonomy_node_id="_unmapped")
        exc_b = _make_excerpt("eb:001", ["b1"], taxonomy_node_id="_unmapped")
        ra = _make_result(atoms_a, [exc_a])
        rb = _make_result(atoms_b, [exc_b])

        issues = {"errors": [], "warnings": [], "info": []}
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        meta = consensus["consensus_meta"]
        assert meta["both_unmapped_count"] == 1
        assert meta["full_agreement_count"] == 0  # NOT counted as real agreement

        # Per-excerpt should have low confidence and both_unmapped agreement
        pe = meta["per_excerpt"][0]
        assert pe["agreement"] == "both_unmapped"
        assert pe["confidence"] == "low"
        assert "classification failure" in pe["flags"][0].lower()

    def test_unmapped_variants_all_detected(self):
        """All variants: _unmapped, __unmapped, unmapped."""
        for node_id in _UNMAPPED_NODES:
            atoms_a = [_make_atom("a1", "prose_sentence", "نص")]
            atoms_b = [_make_atom("b1", "prose_sentence", "نص")]
            exc_a = _make_excerpt("ea:001", ["a1"], taxonomy_node_id=node_id)
            exc_b = _make_excerpt("eb:001", ["b1"], taxonomy_node_id=node_id)
            ra = _make_result(atoms_a, [exc_a])
            rb = _make_result(atoms_b, [exc_b])

            issues = {"errors": [], "warnings": [], "info": []}
            consensus = build_consensus(
                "TEST", ra, rb, "a", "b", issues, issues,
            )
            assert consensus["consensus_meta"]["both_unmapped_count"] == 1, \
                f"Failed to detect unmapped variant: {node_id}"


# ---------------------------------------------------------------------------
# Stress: footnote excerpt comparison
# ---------------------------------------------------------------------------

class TestFootnoteExcerptComparison:
    def test_identical_footnotes_all_matched(self):
        fn_text = "هذا حاشية مفيدة في هذا الباب"
        ra = _make_result([], [], footnote_excerpts=[
            {"excerpt_id": "fn:a:001", "text": fn_text},
        ])
        rb = _make_result([], [], footnote_excerpts=[
            {"excerpt_id": "fn:b:001", "text": fn_text},
        ])
        result = compare_footnote_excerpts(ra, rb, "claude", "gpt4o")
        assert result["matched_count"] == 1
        assert result["unmatched_a_count"] == 0
        assert result["unmatched_b_count"] == 0

    def test_extra_footnote_in_one_model(self):
        fn_text = "هذا حاشية مفيدة في هذا الباب"
        ra = _make_result([], [], footnote_excerpts=[
            {"excerpt_id": "fn:a:001", "text": fn_text},
        ])
        rb = _make_result([], [], footnote_excerpts=[
            {"excerpt_id": "fn:b:001", "text": fn_text},
            {"excerpt_id": "fn:b:002", "text": "حاشية ثانية فريدة لم يجدها النموذج الأول"},
        ])
        result = compare_footnote_excerpts(ra, rb, "claude", "gpt4o")
        assert result["matched_count"] == 1
        assert result["unmatched_b_count"] == 1
        assert len(result["disagreements"]) == 1
        assert result["disagreements"][0]["found_by"] == "gpt4o"

    def test_no_footnotes_both_models(self):
        ra = _make_result([], [])
        rb = _make_result([], [])
        result = compare_footnote_excerpts(ra, rb, "claude", "gpt4o")
        assert result["matched_count"] == 0
        assert result["disagreements"] == []

    def test_footnotes_in_consensus_meta(self):
        """Footnote comparison result should appear in consensus_meta."""
        fn_text = "هذا حاشية مفيدة في هذا الباب"
        ra = _make_model_a_result()
        ra["footnote_excerpts"] = [{"excerpt_id": "fn:a:001", "text": fn_text}]
        rb = _make_model_b_result_same_taxonomy()
        rb["footnote_excerpts"] = [{"excerpt_id": "fn:b:001", "text": fn_text}]

        issues = {"errors": [], "warnings": [], "info": []}
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        fn_meta = consensus["consensus_meta"]["footnote_comparison"]
        assert fn_meta["matched_count"] == 1


# ---------------------------------------------------------------------------
# Stress: exclusion comparison
# ---------------------------------------------------------------------------

class TestExclusionComparison:
    def test_same_exclusions_agree(self):
        ra = _make_model_a_result()  # has exclusion for "باب الهمزة"
        rb = _make_model_b_result_same_taxonomy()  # same exclusion text
        result = compare_exclusions(ra, rb, "claude", "gpt4o")
        assert result["agreed_count"] == 1
        assert result["a_only_count"] == 0
        assert result["b_only_count"] == 0

    def test_different_exclusion_decisions(self):
        atoms_a = [
            _make_atom("a1", "heading", "عنوان"),
            _make_atom("a2", "prose_sentence", TEXT_HAMZA_OVERVIEW),
        ]
        atoms_b = [
            _make_atom("b1", "heading", "عنوان"),
            _make_atom("b2", "prose_sentence", TEXT_HAMZA_OVERVIEW),
        ]
        ra = _make_result(
            atoms_a,
            [_make_excerpt("ea:001", ["a2"])],
            exclusions=[{"atom_id": "a1", "exclusion_reason": "heading_structural"}],
        )
        # Model B does NOT exclude the heading
        rb = _make_result(
            atoms_b,
            [_make_excerpt("eb:001", ["b2"]),
             _make_excerpt("eb:002", ["b1"])],
        )
        result = compare_exclusions(ra, rb, "claude", "gpt4o")
        assert result["a_only_count"] == 1
        assert len(result["disagreements"]) == 1
        assert result["disagreements"][0]["excluded_by"] == "claude"

    def test_exclusions_in_consensus_meta(self):
        """Exclusion comparison should appear in consensus_meta."""
        ra = _make_model_a_result()
        rb = _make_model_b_result_same_taxonomy()
        issues = {"errors": [], "warnings": [], "info": []}
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        excl_meta = consensus["consensus_meta"]["exclusion_comparison"]
        assert "agreed_count" in excl_meta


# ---------------------------------------------------------------------------
# Stress: case_types comparison
# ---------------------------------------------------------------------------

class TestCaseTypesComparison:
    def test_different_case_types_flagged(self):
        atoms_a = [_make_atom("a1", "prose_sentence", TEXT_HAMZA_OVERVIEW)]
        atoms_b = [_make_atom("b1", "prose_sentence", TEXT_HAMZA_OVERVIEW)]
        exc_a = _make_excerpt("ea:001", ["a1"], taxonomy_node_id="leaf",
                              case_types=["A1_pure_definition"])
        exc_b = _make_excerpt("eb:001", ["b1"], taxonomy_node_id="leaf",
                              case_types=["A2_rule_statement", "A1_pure_definition"])
        ra = _make_result(atoms_a, [exc_a])
        rb = _make_result(atoms_b, [exc_b])

        issues = {"errors": [], "warnings": [], "info": []}
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        ct_dis = consensus["consensus_meta"]["case_type_disagreements"]
        assert len(ct_dis) == 1
        assert "A1_pure_definition" in ct_dis[0]["shared"]
        assert "A2_rule_statement" in ct_dis[0]["b_only"]

    def test_same_case_types_no_disagreement(self):
        atoms_a = [_make_atom("a1", "prose_sentence", TEXT_HAMZA_OVERVIEW)]
        atoms_b = [_make_atom("b1", "prose_sentence", TEXT_HAMZA_OVERVIEW)]
        exc_a = _make_excerpt("ea:001", ["a1"], taxonomy_node_id="leaf",
                              case_types=["A1_pure_definition"])
        exc_b = _make_excerpt("eb:001", ["b1"], taxonomy_node_id="leaf",
                              case_types=["A1_pure_definition"])
        ra = _make_result(atoms_a, [exc_a])
        rb = _make_result(atoms_b, [exc_b])

        issues = {"errors": [], "warnings": [], "info": []}
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        assert consensus["consensus_meta"]["case_type_disagreements"] == []


# ---------------------------------------------------------------------------
# Stress: discarded excerpt tracking
# ---------------------------------------------------------------------------

class TestDiscardedExcerptTracking:
    def test_discarded_excerpts_tracked_in_meta(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_extra_excerpt()
        issues = {"errors": [], "warnings": [], "info": []}

        def discard_llm(system, user, model, api_key):
            return {
                "parsed": {
                    "verdict": "discard",
                    "reasoning": "Not a valid teaching unit.",
                    "confidence": "certain",
                },
                "input_tokens": 80,
                "output_tokens": 40,
                "stop_reason": "end_turn",
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
            call_llm_fn=discard_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
        )
        discarded = consensus["consensus_meta"]["discarded_excerpts"]
        assert len(discarded) == 1
        assert discarded[0]["excerpt_id"] == "qb:exc:000003"
        assert discarded[0]["source_model"] == "gpt4o"
        assert "Not a valid" in discarded[0]["reason"]

    def test_kept_excerpts_not_in_discarded(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_extra_excerpt()
        issues = {"errors": [], "warnings": [], "info": []}

        def keep_llm(system, user, model, api_key):
            return {
                "parsed": {
                    "verdict": "keep",
                    "reasoning": "Valid.",
                    "confidence": "certain",
                },
                "input_tokens": 80,
                "output_tokens": 40,
                "stop_reason": "end_turn",
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
            call_llm_fn=keep_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
        )
        assert consensus["consensus_meta"]["discarded_excerpts"] == []
        assert len(consensus["excerpts"]) == 3  # 2 matched + 1 kept


# ---------------------------------------------------------------------------
# Stress: very short text n-gram handling
# ---------------------------------------------------------------------------

class TestShortTextNgrams:
    def test_two_char_text_produces_bigram(self):
        grams = char_ngrams("اب", 5)
        assert len(grams) == 1
        assert "اب" in grams

    def test_three_char_text_produces_trigrams(self):
        grams = char_ngrams("ابت", 5)
        # effective_n = min(5, max(2, 3)) = 3
        # "ابت" -> one 3-gram
        assert len(grams) == 1

    def test_four_char_text_produces_quadgrams(self):
        grams = char_ngrams("ابتث", 5)
        # effective_n = min(5, max(2, 4)) = 4
        # "ابتث" -> one 4-gram
        assert len(grams) == 1

    def test_short_text_overlap_ratio_works(self):
        """Two very short overlapping texts should produce nonzero overlap."""
        ratio = text_overlap_ratio("كتب", "كتب")
        assert ratio == 1.0

    def test_short_different_texts_low_overlap(self):
        ratio = text_overlap_ratio("كتب", "درس")
        assert ratio == 0.0

    def test_single_char_text(self):
        grams = char_ngrams("ا", 5)
        # len < effective_n (max(2,1)=2), returns {clean}
        assert grams == {"ا"}


# ---------------------------------------------------------------------------
# Stress: arbiter confidence normalization
# ---------------------------------------------------------------------------

class TestNormalizeConfidence:
    def test_standard_values_unchanged(self):
        assert _normalize_confidence("certain") == "certain"
        assert _normalize_confidence("likely") == "likely"
        assert _normalize_confidence("uncertain") == "uncertain"

    def test_case_insensitive(self):
        assert _normalize_confidence("CERTAIN") == "certain"
        assert _normalize_confidence("Likely") == "likely"

    def test_high_maps_to_certain(self):
        assert _normalize_confidence("high") == "certain"

    def test_medium_maps_to_likely(self):
        assert _normalize_confidence("medium") == "likely"

    def test_unknown_maps_to_uncertain(self):
        assert _normalize_confidence("whatever") == "uncertain"
        assert _normalize_confidence("low") == "uncertain"

    def test_none_maps_to_uncertain(self):
        assert _normalize_confidence(None) == "uncertain"

    def test_empty_string_maps_to_uncertain(self):
        assert _normalize_confidence("") == "uncertain"

    def test_non_string_maps_to_uncertain(self):
        assert _normalize_confidence(42) == "uncertain"

    def test_whitespace_stripped(self):
        assert _normalize_confidence("  certain  ") == "certain"


# ---------------------------------------------------------------------------
# Stress: arbiter invalid placement fallback
# ---------------------------------------------------------------------------

class TestArbiterInvalidPlacementFallback:
    def test_invalid_placement_falls_back_to_model_a(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_different_taxonomy()
        issues = {"errors": [], "warnings": [], "info": []}

        def bad_placement_llm(system, user, model, api_key):
            return {
                "parsed": {
                    "correct_placement": "completely_wrong_node",
                    "reasoning": "I picked something invalid.",
                    "confidence": "certain",
                },
                "input_tokens": 100,
                "output_tokens": 50,
                "stop_reason": "end_turn",
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
            call_llm_fn=bad_placement_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
        )
        meta = consensus["consensus_meta"]
        # The invalid placement should fall back to model A's placement
        for d in meta["disagreements"]:
            if d["type"] == "placement_disagreement":
                assert d["arbiter_resolution"]["correct_placement"] in (
                    "al_hala_1_tursam_alifan", "al_hala_2_tursam_wawan"
                )


# ---------------------------------------------------------------------------
# Stress: arbiter malformed JSON graceful fallback
# ---------------------------------------------------------------------------

class TestArbiterMalformedJsonFallback:
    def test_non_dict_response_falls_back(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_different_taxonomy()
        issues = {"errors": [], "warnings": [], "info": []}

        def bad_llm(system, user, model, api_key):
            return {
                "parsed": "just a string, not a dict",
                "input_tokens": 50,
                "output_tokens": 20,
                "stop_reason": "end_turn",
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
            call_llm_fn=bad_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
        )
        # Should not crash; arbiter falls back gracefully
        assert len(consensus["excerpts"]) == 2
        meta = consensus["consensus_meta"]
        for d in meta["disagreements"]:
            if d["type"] == "placement_disagreement":
                assert d["arbiter_resolution"]["confidence"] == "uncertain"

    def test_none_parsed_falls_back(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_different_taxonomy()
        issues = {"errors": [], "warnings": [], "info": []}

        def none_llm(system, user, model, api_key):
            return {
                "parsed": None,
                "input_tokens": 50,
                "output_tokens": 20,
                "stop_reason": "end_turn",
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
            call_llm_fn=none_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
        )
        assert len(consensus["excerpts"]) == 2


# ---------------------------------------------------------------------------
# Stress: reordered atoms produce same content
# ---------------------------------------------------------------------------

class TestReorderedAtomsSameContent:
    def test_reordered_core_atoms_still_match(self):
        """If two models reference the same text but atom order differs, overlap still high."""
        text1 = "أن تكون الهمزة ساكنة"
        text2 = "بعد فتح فتكتب على ألف"

        atoms_a = [
            _make_atom("a1", "prose_sentence", text1),
            _make_atom("a2", "prose_sentence", text2),
        ]
        atoms_b = [
            _make_atom("b1", "prose_sentence", text2),  # reversed order
            _make_atom("b2", "prose_sentence", text1),
        ]
        exc_a = _make_excerpt("ea:001", ["a1", "a2"], taxonomy_node_id="leaf")
        exc_b = _make_excerpt("eb:001", ["b2", "b1"], taxonomy_node_id="leaf")

        lookup_a = build_atom_lookup({"atoms": atoms_a})
        lookup_b = build_atom_lookup({"atoms": atoms_b})

        matched, un_a, un_b = match_excerpts(
            [exc_a], [exc_b], lookup_a, lookup_b,
        )
        # Text is same content just reordered — n-gram overlap should be very high
        assert len(matched) == 1
        assert matched[0]["text_overlap"] > 0.7


# ---------------------------------------------------------------------------
# Stress: both models produce empty excerpts
# ---------------------------------------------------------------------------

class TestBothModelsEmptyResults:
    def test_both_empty_no_crash(self):
        ra = _make_result([], [])
        rb = _make_result([], [])
        issues = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        assert consensus["excerpts"] == []
        meta = consensus["consensus_meta"]
        assert meta["matched_count"] == 0
        assert meta["full_agreement_count"] == 0

    def test_one_empty_one_populated(self):
        ra = _make_model_a_result()
        rb = _make_result([], [])
        issues = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        # All of model A's excerpts should be unmatched
        meta = consensus["consensus_meta"]
        assert meta["unmatched_a_count"] == 2
        assert meta["matched_count"] == 0


# ---------------------------------------------------------------------------
# Stress: consensus meta full JSON roundtrip
# ---------------------------------------------------------------------------

class TestConsensusMetaJsonRoundtrip:
    def test_full_roundtrip_with_all_features(self):
        """Build a consensus with all features and verify JSON roundtrip."""
        import json

        # Build a scenario with: matched, unmatched, footnotes, exclusions, case_types
        atoms_a = [
            _make_atom("a1", "prose_sentence", TEXT_HAMZA_OVERVIEW),
            _make_atom("a2", "prose_sentence", TEXT_HAMZA_CASE_1),
            _make_atom("a3", "heading", "باب"),
        ]
        atoms_b = [
            _make_atom("b1", "prose_sentence", TEXT_HAMZA_OVERVIEW),
            _make_atom("b2", "prose_sentence", TEXT_HAMZA_CASE_2),  # different text
            _make_atom("b3", "heading", "باب"),
        ]
        exc_a = [
            _make_excerpt("ea:001", ["a1"], taxonomy_node_id="leaf_a",
                          case_types=["A1_pure_definition"]),
            _make_excerpt("ea:002", ["a2"], taxonomy_node_id="leaf_b"),
        ]
        exc_b = [
            _make_excerpt("eb:001", ["b1"], taxonomy_node_id="leaf_a",
                          case_types=["A2_rule_statement"]),
            _make_excerpt("eb:002", ["b2"], taxonomy_node_id="leaf_c"),
        ]
        ra = _make_result(
            atoms_a, exc_a,
            footnote_excerpts=[{"excerpt_id": "fn:a:001", "text": "حاشية"}],
            exclusions=[{"atom_id": "a3", "exclusion_reason": "heading"}],
        )
        rb = _make_result(
            atoms_b, exc_b,
            footnote_excerpts=[{"excerpt_id": "fn:b:001", "text": "حاشية مختلفة جديدة"}],
            exclusions=[],
        )

        issues = {"errors": [], "warnings": [], "info": []}
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )

        # Full JSON roundtrip
        json_str = json.dumps(consensus, ensure_ascii=False, indent=2)
        roundtripped = json.loads(json_str)
        assert roundtripped["passage_id"] == "P004"
        assert "consensus_meta" in roundtripped
        meta = roundtripped["consensus_meta"]
        assert isinstance(meta["footnote_comparison"], dict)
        assert isinstance(meta["exclusion_comparison"], dict)
        assert isinstance(meta["case_type_disagreements"], list)
        assert isinstance(meta["discarded_excerpts"], list)


# ---------------------------------------------------------------------------
# Stress: review section with hardened features
# ---------------------------------------------------------------------------

class TestReviewSectionHardenedFeatures:
    def test_both_unmapped_shown_in_review(self):
        meta = {
            "mode": "consensus",
            "model_a": "claude", "model_b": "gpt4o",
            "winning_model": "claude",
            "matched_count": 1, "full_agreement_count": 0,
            "both_unmapped_count": 1,
            "placement_disagreement_count": 0,
            "unmatched_a_count": 0, "unmatched_b_count": 0,
            "coverage_agreement": {"coverage_agreement_ratio": 1.0},
            "footnote_comparison": {"matched_count": 0, "unmatched_a_count": 0, "unmatched_b_count": 0},
            "exclusion_comparison": {"agreed_count": 0, "a_only_count": 0, "b_only_count": 0},
            "case_type_disagreements": [],
            "discarded_excerpts": [{"excerpt_id": "e1", "source_model": "gpt4o", "reason": "invalid"}],
            "arbiter_cost": {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0},
            "disagreements": [{"type": "both_unmapped", "text_overlap": 0.95, "arbiter_resolution": None}],
            "per_excerpt": [
                {"excerpt_id": "e1", "confidence": "low", "source_model": "claude",
                 "agreement": "both_unmapped", "flags": ["Both models placed at _unmapped"]},
            ],
        }
        md = generate_consensus_review_section(meta)
        assert "classification failure" in md.lower()
        assert "Discarded by arbiter" in md

    def test_footnote_section_shown_when_disagreements(self):
        meta = {
            "mode": "consensus",
            "model_a": "claude", "model_b": "gpt4o",
            "winning_model": "claude",
            "matched_count": 0, "full_agreement_count": 0,
            "both_unmapped_count": 0,
            "placement_disagreement_count": 0,
            "unmatched_a_count": 0, "unmatched_b_count": 0,
            "coverage_agreement": {"coverage_agreement_ratio": 1.0},
            "footnote_comparison": {"matched_count": 1, "unmatched_a_count": 0, "unmatched_b_count": 1},
            "exclusion_comparison": {"agreed_count": 0, "a_only_count": 1, "b_only_count": 0},
            "case_type_disagreements": [
                {"excerpt_a_id": "e1", "a_only": ["X"], "b_only": ["Y"], "shared": ["Z"]},
            ],
            "discarded_excerpts": [],
            "arbiter_cost": {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0},
            "disagreements": [],
            "per_excerpt": [],
        }
        md = generate_consensus_review_section(meta)
        assert "Footnote Excerpt Comparison" in md
        assert "Exclusion Comparison" in md
        assert "Case Type Disagreements" in md


# ---------------------------------------------------------------------------
# Stress: passage text truncation at word boundary
# ---------------------------------------------------------------------------

class TestPassageTextTruncation:
    def test_long_passage_truncated_for_arbiter(self):
        """resolve_unmatched_excerpt should truncate at word boundary."""
        from tools.consensus import resolve_unmatched_excerpt

        long_text = "كلمة " * 500  # ~2500 chars
        atom = {"text": "نص المقتطف"}
        exc = {
            "excerpt_id": "e1",
            "taxonomy_node_id": "leaf",
            "taxonomy_path": "science > leaf",
            "core_atoms": [{"atom_id": "a1", "role": "author_prose"}],
        }
        atom_lookup = {"a1": atom}

        call_count = [0]
        captured_prompt = [None]

        def capture_llm(system, user, model, api_key):
            call_count[0] += 1
            captured_prompt[0] = user
            return {
                "parsed": {"verdict": "keep", "reasoning": "ok", "confidence": "certain"},
                "input_tokens": 50,
                "output_tokens": 25,
                "stop_reason": "end_turn",
            }

        result = resolve_unmatched_excerpt(
            exc, atom_lookup, "claude", "gpt4o", long_text,
            capture_llm, "arbiter", "key",
        )
        assert result["verdict"] == "keep"
        assert call_count[0] == 1
        # The passage context inside the prompt should be truncated to ~2000 chars,
        # not the full 2500 chars. Check that the full raw passage is NOT embedded.
        assert long_text not in captured_prompt[0]
        # The truncated context should be shorter than the original
        assert captured_prompt[0].count("كلمة") < 500


# ===========================================================================
# AUDIT FIX TESTS — verify all 16 audit findings are fixed
# ===========================================================================

# ---------------------------------------------------------------------------
# Audit: _model_tag
# ---------------------------------------------------------------------------

class TestModelTag:
    def test_simple_model_name(self):
        assert _model_tag("claude") == "claude"

    def test_openrouter_path_strips_prefix(self):
        assert _model_tag("anthropic/claude-sonnet-4-5-20250929") == "claude-son"

    def test_truncates_at_10(self):
        assert len(_model_tag("a-very-long-model-name")) == 10


# ---------------------------------------------------------------------------
# Audit: _remap_atom_refs
# ---------------------------------------------------------------------------

class TestRemapAtomRefs:
    def test_remaps_dict_entries(self):
        exc = {
            "core_atoms": [{"atom_id": "a1", "role": "author_prose"}],
            "context_atoms": [{"atom_id": "a2", "role": "context"}],
        }
        _remap_atom_refs(exc, {"a1": "a1:gpt", "a2": "a2:gpt"})
        assert exc["core_atoms"][0]["atom_id"] == "a1:gpt"
        assert exc["context_atoms"][0]["atom_id"] == "a2:gpt"

    def test_remaps_string_entries(self):
        exc = {
            "core_atoms": ["a1", "a2"],
            "context_atoms": [],
        }
        _remap_atom_refs(exc, {"a1": "a1:gpt"})
        assert exc["core_atoms"][0] == "a1:gpt"
        assert exc["core_atoms"][1] == "a2"  # not in remap

    def test_no_remap_needed(self):
        exc = {
            "core_atoms": [{"atom_id": "a1", "role": "author_prose"}],
        }
        _remap_atom_refs(exc, {})
        assert exc["core_atoms"][0]["atom_id"] == "a1"

    def test_none_fields_handled(self):
        exc = {"core_atoms": None, "context_atoms": None}
        _remap_atom_refs(exc, {"a1": "a1:gpt"})  # should not crash


# ---------------------------------------------------------------------------
# Audit: _merge_atoms_for_consensus (CRITICAL fix: cross-model atom refs)
# ---------------------------------------------------------------------------

class TestMergeAtomsForConsensus:
    def test_all_winning_model_no_merge_needed(self):
        """When all excerpts come from winning model, just return its atoms."""
        ra = _make_model_a_result()
        rb = _make_model_b_result_same_taxonomy()
        consensus_excerpts = [
            {"excerpt": ra["excerpts"][0], "source_model": "claude"},
            {"excerpt": ra["excerpts"][1], "source_model": "claude"},
        ]
        merged = _merge_atoms_for_consensus(
            ra, rb, consensus_excerpts, "claude", "gpt4o", "claude",
        )
        # Should just be model A's atoms
        ids = {a["atom_id"] for a in merged}
        assert all(aid.startswith("qa:") for aid in ids)

    def test_losing_model_excerpt_atoms_included(self):
        """When arbiter picks losing model's excerpt, its atoms must be merged."""
        ra = _make_model_a_result()
        rb = _make_model_b_result_same_taxonomy()
        # Simulate arbiter picking model B's first excerpt
        consensus_excerpts = [
            {"excerpt": rb["excerpts"][0], "source_model": "gpt4o"},  # from losing model
            {"excerpt": ra["excerpts"][1], "source_model": "claude"},
        ]
        merged = _merge_atoms_for_consensus(
            ra, rb, consensus_excerpts, "claude", "gpt4o", "claude",
        )
        ids = {a["atom_id"] for a in merged}
        # Model B's atom qb:matn:000002 should be present (needed by its excerpt)
        # It may be remapped if there's a collision
        assert len(merged) >= 3  # at least model A's 3 + any needed from B

    def test_collision_disambiguation(self):
        """Same atom_id different text → disambiguated with model tag."""
        atoms_a = [_make_atom("shared:001", "prose_sentence", "Text version A")]
        atoms_b = [_make_atom("shared:001", "prose_sentence", "Text version B")]
        exc_b = _make_excerpt("eb:001", ["shared:001"])
        ra = _make_result(atoms_a, [])
        rb = _make_result(atoms_b, [exc_b])
        consensus_excerpts = [
            {"excerpt": exc_b, "source_model": "gpt4o"},
        ]
        merged = _merge_atoms_for_consensus(
            ra, rb, consensus_excerpts, "claude", "gpt4o", "claude",
        )
        ids = {a["atom_id"] for a in merged}
        # shared:001 is in winning (A), collision means B's gets tagged
        assert "shared:001" in ids  # A's version
        # G03: disambiguation uses _tag suffix (not :tag) to keep valid ID format
        tagged = [aid for aid in ids if "_gpt4o" in aid]
        assert len(tagged) == 1  # B's version disambiguated
        assert tagged[0] == "shared:001_gpt4o"
        # The consensus_excerpts entry should have been deep-copied and remapped
        # (original exc_b is not mutated thanks to F03 deep-copy fix)
        ce_exc = consensus_excerpts[0]["excerpt"]
        ce_ref = ce_exc["core_atoms"][0]
        remapped_id = ce_ref["atom_id"] if isinstance(ce_ref, dict) else ce_ref
        assert "gpt4o" in remapped_id
        # Original should be UNCHANGED (F03: deep-copy protects originals)
        orig_ref = exc_b["core_atoms"][0]
        orig_id = orig_ref["atom_id"] if isinstance(orig_ref, dict) else orig_ref
        assert orig_id == "shared:001"

    def test_no_collision_same_text(self):
        """Same atom_id same text → no disambiguation needed."""
        atoms_a = [_make_atom("shared:001", "prose_sentence", "Same text")]
        atoms_b = [_make_atom("shared:001", "prose_sentence", "Same text")]
        exc_b = _make_excerpt("eb:001", ["shared:001"])
        ra = _make_result(atoms_a, [])
        rb = _make_result(atoms_b, [exc_b])
        consensus_excerpts = [
            {"excerpt": exc_b, "source_model": "gpt4o"},
        ]
        merged = _merge_atoms_for_consensus(
            ra, rb, consensus_excerpts, "claude", "gpt4o", "claude",
        )
        ids = [a["atom_id"] for a in merged]
        # No disambiguation → only shared:001 appears (once from A)
        assert ids.count("shared:001") == 1

    def test_source_model_tag_on_merged_atoms(self):
        """Atoms from losing model should have _source_model marker."""
        atoms_a = [_make_atom("a1", "prose_sentence", "A text")]
        atoms_b = [_make_atom("b1", "prose_sentence", "B text")]
        exc_b = _make_excerpt("eb:001", ["b1"])
        ra = _make_result(atoms_a, [])
        rb = _make_result(atoms_b, [exc_b])
        consensus_excerpts = [
            {"excerpt": exc_b, "source_model": "gpt4o"},
        ]
        merged = _merge_atoms_for_consensus(
            ra, rb, consensus_excerpts, "claude", "gpt4o", "claude",
        )
        b_atom = next(a for a in merged if a["atom_id"] == "b1")
        assert b_atom["_source_model"] == "gpt4o"


# ---------------------------------------------------------------------------
# Audit: _optimal_assignment (replaces greedy)
# ---------------------------------------------------------------------------

class TestOptimalAssignment:
    def test_simple_1_to_1(self):
        matrix = [[0.9]]
        pairs = _optimal_assignment(matrix, 0.5)
        assert pairs == [(0, 0)]

    def test_obvious_matching(self):
        # 2x2: optimal is (0,0) and (1,1) with total 1.8
        matrix = [
            [0.9, 0.1],
            [0.1, 0.9],
        ]
        pairs = _optimal_assignment(matrix, 0.5)
        assert set(pairs) == {(0, 0), (1, 1)}

    def test_suboptimal_greedy_case(self):
        """Greedy would pick (0,0)=0.8 first, leaving (1,1)=0.4 below threshold.
        Optimal picks (0,1)=0.6 and (1,0)=0.7 → total 1.3 vs greedy 0.8."""
        matrix = [
            [0.8, 0.6],
            [0.7, 0.4],
        ]
        pairs = _optimal_assignment(matrix, 0.5)
        # Optimal should match both rows (total 1.3)
        assert len(pairs) == 2
        pair_set = set(pairs)
        assert pair_set == {(0, 1), (1, 0)}

    def test_no_matches_below_threshold(self):
        matrix = [
            [0.3, 0.2],
            [0.1, 0.4],
        ]
        pairs = _optimal_assignment(matrix, 0.5)
        assert pairs == []

    def test_empty_matrix(self):
        pairs = _optimal_assignment([], 0.5)
        assert pairs == []

    def test_more_rows_than_cols(self):
        matrix = [
            [0.9, 0.1],
            [0.1, 0.9],
            [0.5, 0.5],  # extra row, no column left
        ]
        pairs = _optimal_assignment(matrix, 0.5)
        # Should match 2 rows, 1 unmatched
        assert len(pairs) == 2

    def test_more_cols_than_rows(self):
        matrix = [
            [0.9, 0.1, 0.5],
        ]
        pairs = _optimal_assignment(matrix, 0.5)
        # Should match the best column
        assert len(pairs) == 1
        assert pairs[0] == (0, 0)  # 0.9 is highest

    def test_fallback_for_large_n(self):
        """When SMALLER dimension > 20, should return None for greedy fallback.
        The algorithm transposes to bitmask over the smaller side, so both
        dimensions must exceed 20 to trigger the fallback."""
        n = 21
        # 21x21 matrix — smaller dimension is 21 > 20
        matrix = [[0.6 if i == j else 0.1 for j in range(n)] for i in range(n)]
        result = _optimal_assignment(matrix, 0.5)
        assert result is None


# ---------------------------------------------------------------------------
# Audit: merge_footnote_excerpts (CRITICAL fix: footnotes not dropped)
# ---------------------------------------------------------------------------

class TestMergeFootnoteExcerpts:
    def test_winning_model_footnotes_included(self):
        ra = _make_result([], [], footnote_excerpts=[
            {"excerpt_id": "fn:a:001", "text": "footnote A"},
        ])
        rb = _make_result([], [], footnote_excerpts=[
            {"excerpt_id": "fn:b:001", "text": "footnote A"},  # matched
        ])
        comparison = compare_footnote_excerpts(ra, rb, "claude", "gpt4o")
        merged = merge_footnote_excerpts(
            ra, rb, "claude", "gpt4o", "claude", comparison,
        )
        assert len(merged) == 1
        assert merged[0]["excerpt_id"] == "fn:a:001"

    def test_unmatched_from_other_model_included(self):
        ra = _make_result([], [], footnote_excerpts=[
            {"excerpt_id": "fn:a:001", "text": "shared footnote text for matching"},
        ])
        rb = _make_result([], [], footnote_excerpts=[
            {"excerpt_id": "fn:b:001", "text": "shared footnote text for matching"},
            {"excerpt_id": "fn:b:002", "text": "unique footnote only in model B different text"},
        ])
        comparison = compare_footnote_excerpts(ra, rb, "claude", "gpt4o")
        merged = merge_footnote_excerpts(
            ra, rb, "claude", "gpt4o", "claude", comparison,
        )
        # Should include winning's matched + other's unmatched
        assert len(merged) == 2
        ids = {fn["excerpt_id"] for fn in merged}
        assert "fn:a:001" in ids  # winning's matched
        assert "fn:b:002" in ids  # other's unmatched
        # Unmatched should be flagged
        b_fn = next(fn for fn in merged if fn["excerpt_id"] == "fn:b:002")
        assert "_consensus_flag" in b_fn
        assert "gpt4o" in b_fn["_consensus_flag"]

    def test_empty_footnotes(self):
        ra = _make_result([], [])
        rb = _make_result([], [])
        comparison = compare_footnote_excerpts(ra, rb, "claude", "gpt4o")
        merged = merge_footnote_excerpts(
            ra, rb, "claude", "gpt4o", "claude", comparison,
        )
        assert merged == []


# ---------------------------------------------------------------------------
# Audit: compare_context_atoms
# ---------------------------------------------------------------------------

class TestCompareContextAtoms:
    def test_same_context_atoms_no_disagreement(self):
        atoms_a = {"a_ctx": {"text": "سياق مشترك"}}
        atoms_b = {"b_ctx": {"text": "سياق مشترك"}}  # same text, different ID
        matched = [{
            "excerpt_a": {"excerpt_id": "ea:001",
                          "context_atoms": [{"atom_id": "a_ctx"}]},
            "excerpt_b": {"excerpt_id": "eb:001",
                          "context_atoms": [{"atom_id": "b_ctx"}]},
        }]
        result = compare_context_atoms(matched, atoms_a, atoms_b)
        assert result == []

    def test_different_context_atoms_flagged(self):
        atoms_a = {"a_ctx": {"text": "سياق خاص بالنموذج الأول فقط"}}
        atoms_b = {"b_ctx": {"text": "سياق مختلف تماما عن الأول"}}
        matched = [{
            "excerpt_a": {"excerpt_id": "ea:001",
                          "context_atoms": [{"atom_id": "a_ctx"}]},
            "excerpt_b": {"excerpt_id": "eb:001",
                          "context_atoms": [{"atom_id": "b_ctx"}]},
        }]
        result = compare_context_atoms(matched, atoms_a, atoms_b)
        assert len(result) == 1
        assert result[0]["excerpt_a_id"] == "ea:001"
        assert result[0]["a_count"] == 1
        assert result[0]["b_count"] == 1
        assert result[0]["a_only_count"] == 1
        assert result[0]["b_only_count"] == 1

    def test_one_model_no_context_atoms(self):
        atoms_a = {"a_ctx": {"text": "سياق"}}
        matched = [{
            "excerpt_a": {"excerpt_id": "ea:001",
                          "context_atoms": [{"atom_id": "a_ctx"}]},
            "excerpt_b": {"excerpt_id": "eb:001",
                          "context_atoms": []},
        }]
        result = compare_context_atoms(matched, atoms_a, {})
        assert len(result) == 1
        assert result[0]["a_count"] == 1
        assert result[0]["b_count"] == 0

    def test_no_matched_pairs_no_disagreements(self):
        assert compare_context_atoms([], {}, {}) == []


# ---------------------------------------------------------------------------
# Audit: _compute_arbiter_cost (fix: hardcoded wrong pricing)
# ---------------------------------------------------------------------------

class TestComputeArbiterCost:
    def test_default_pricing(self):
        cost = _compute_arbiter_cost(1_000_000, 100_000)
        # Default: $3/M in + $15/M out = $3 + $1.5 = $4.5
        assert abs(cost - 4.5) < 0.001

    def test_custom_pricing(self):
        cost = _compute_arbiter_cost(1_000_000, 100_000,
                                      arbiter_pricing=(2.5, 10.0))
        # $2.5/M in + $10/M out on 100k = $2.5 + $1.0 = $3.5
        assert abs(cost - 3.5) < 0.001

    def test_zero_tokens(self):
        assert _compute_arbiter_cost(0, 0) == 0.0

    def test_pricing_passed_through_build_consensus(self):
        """arbiter_pricing should propagate to arbiter calls."""
        ra = _make_model_a_result()
        rb = _make_model_b_result_different_taxonomy()
        issues = {"errors": [], "warnings": [], "info": []}

        def mock_llm(system, user, model, api_key):
            return {
                "parsed": {
                    "correct_placement": "al_hala_2_tursam_wawan",
                    "reasoning": "correct",
                    "confidence": "certain",
                },
                "input_tokens": 1000,
                "output_tokens": 200,
                "stop_reason": "end_turn",
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
            call_llm_fn=mock_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
            arbiter_pricing=(2.5, 10.0),
        )
        cost = consensus["consensus_meta"]["arbiter_cost"]["total_cost"]
        # 1000 * 2.5/1M + 200 * 10.0/1M = 0.0025 + 0.002 = 0.0045
        assert abs(cost - 0.0045) < 0.0001


# ---------------------------------------------------------------------------
# Audit: arbiter "neither" response (DESIGN fix)
# ---------------------------------------------------------------------------

class TestArbiterNeitherResponse:
    def test_neither_placement_low_confidence(self):
        ra = _make_model_a_result()
        rb = _make_model_b_result_different_taxonomy()
        issues = {"errors": [], "warnings": [], "info": []}

        def neither_llm(system, user, model, api_key):
            return {
                "parsed": {
                    "correct_placement": "neither",
                    "reasoning": "Both placements are wrong.",
                    "confidence": "certain",
                },
                "input_tokens": 100,
                "output_tokens": 50,
                "stop_reason": "end_turn",
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
            call_llm_fn=neither_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
        )
        meta = consensus["consensus_meta"]
        # The disagreement excerpt should have low confidence
        pe_dis = [pe for pe in meta["per_excerpt"]
                  if pe["agreement"] == "placement_disagreement"]
        assert len(pe_dis) == 1
        assert pe_dis[0]["confidence"] == "low"
        # Should have the "both wrong" flag
        flags_joined = " ".join(pe_dis[0]["flags"])
        assert "BOTH" in flags_joined or "neither" in flags_joined.lower()

    def test_neither_in_review_section(self):
        meta = {
            "mode": "consensus",
            "model_a": "claude", "model_b": "gpt4o",
            "winning_model": "claude",
            "matched_count": 1, "full_agreement_count": 0,
            "placement_disagreement_count": 1,
            "unmatched_a_count": 0, "unmatched_b_count": 0,
            "coverage_agreement": {"coverage_agreement_ratio": 0.9},
            "arbiter_cost": {"input_tokens": 100, "output_tokens": 50, "total_cost": 0.001},
            "disagreements": [{
                "type": "placement_disagreement",
                "model_a_placement": "node_a",
                "model_b_placement": "node_b",
                "text_overlap": 0.95,
                "arbiter_resolution": {
                    "correct_placement": "neither",
                    "reasoning": "both wrong",
                    "confidence": "certain",
                },
            }],
            "per_excerpt": [{
                "excerpt_id": "e1", "confidence": "low",
                "source_model": "claude",
                "agreement": "placement_disagreement",
                "flags": ["Arbiter: BOTH placements are wrong"],
            }],
        }
        md = generate_consensus_review_section(meta)
        assert "NEITHER" in md
        assert "both wrong" in md.lower()


# ---------------------------------------------------------------------------
# Audit: disagreements list mutation isolation (MEDIUM fix)
# ---------------------------------------------------------------------------

class TestDisagreementsListMutationIsolation:
    def test_disagreements_snapshot_not_mutated(self):
        """Disagreements in consensus_meta should not change after build."""
        ra = _make_model_a_result()
        # Model B has different taxonomy AND extra excerpt → 2 types of disagreements
        atoms_b = [
            _make_atom("qb:matn:000001", "heading", "باب الهمزة"),
            _make_atom("qb:matn:000002", "prose_sentence", TEXT_HAMZA_OVERVIEW),
            _make_atom("qb:matn:000003", "prose_sentence", TEXT_HAMZA_CASE_1),
            _make_atom("qb:matn:000004", "prose_sentence", TEXT_HAMZA_CASE_2),
        ]
        exc_b = [
            _make_excerpt("qb:exc:000001", ["qb:matn:000002"],
                           taxonomy_node_id="al_hamza_wasat__overview"),  # same
            _make_excerpt("qb:exc:000002", ["qb:matn:000003"],
                           taxonomy_node_id="al_hala_2_tursam_wawan"),  # DIFFERENT
            _make_excerpt("qb:exc:000003", ["qb:matn:000004"],
                           taxonomy_node_id="al_hala_2_tursam_wawan"),  # EXTRA
        ]
        rb = _make_result(
            atoms_b, exc_b,
            footnote_excerpts=[{"excerpt_id": "fn:b:001",
                                "text": "حاشية فريدة لم يجدها النموذج الأول"}],
        )
        issues = {"errors": [], "warnings": [], "info": []}
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        meta = consensus["consensus_meta"]
        # Capture count at snapshot
        snapshot_count = len(meta["disagreements"])
        # Disagreements should include placement + unmatched + footnote
        assert snapshot_count >= 2  # at least placement + unmatched
        # Access again — should be same
        assert len(meta["disagreements"]) == snapshot_count


# ---------------------------------------------------------------------------
# Audit: compare_footnote_excerpts returns unmatched lists
# ---------------------------------------------------------------------------

class TestFootnoteComparisonUnmatchedLists:
    def test_unmatched_lists_returned(self):
        ra = _make_result([], [], footnote_excerpts=[
            {"excerpt_id": "fn:a:001", "text": "shared text long enough to match"},
        ])
        rb = _make_result([], [], footnote_excerpts=[
            {"excerpt_id": "fn:b:001", "text": "shared text long enough to match"},
            {"excerpt_id": "fn:b:002", "text": "unique unmatched footnote text here"},
        ])
        result = compare_footnote_excerpts(ra, rb, "claude", "gpt4o")
        assert "unmatched_a" in result
        assert "unmatched_b" in result
        assert len(result["unmatched_a"]) == 0
        assert len(result["unmatched_b"]) == 1
        assert result["unmatched_b"][0]["excerpt_id"] == "fn:b:002"

    def test_unmatched_lists_stripped_from_meta(self):
        """consensus_meta.footnote_comparison should NOT contain unmatched lists."""
        fn_text = "حاشية مفيدة طويلة بما يكفي"
        ra = _make_model_a_result()
        ra["footnote_excerpts"] = [{"excerpt_id": "fn:a:001", "text": fn_text}]
        rb = _make_model_b_result_same_taxonomy()
        rb["footnote_excerpts"] = [
            {"excerpt_id": "fn:b:001", "text": fn_text},
            {"excerpt_id": "fn:b:002", "text": "unique footnote from model B only different"},
        ]
        issues = {"errors": [], "warnings": [], "info": []}
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        fn_meta = consensus["consensus_meta"]["footnote_comparison"]
        assert "unmatched_a" not in fn_meta
        assert "unmatched_b" not in fn_meta
        # But counts should be there
        assert "unmatched_b_count" in fn_meta


# ---------------------------------------------------------------------------
# Audit: context_atom_disagreements in consensus_meta
# ---------------------------------------------------------------------------

class TestContextAtomDisagreementsInMeta:
    def test_disagreements_captured(self):
        atoms_a = [
            _make_atom("a1", "prose_sentence", TEXT_HAMZA_OVERVIEW),
            _make_atom("a_ctx", "prose_sentence", "سياق من النموذج الأول فقط"),
        ]
        atoms_b = [
            _make_atom("b1", "prose_sentence", TEXT_HAMZA_OVERVIEW),
            _make_atom("b_ctx", "prose_sentence", "سياق مختلف تماما عن الأول"),
        ]
        exc_a = _make_excerpt("ea:001", ["a1"], taxonomy_node_id="leaf",
                              context_atoms=[{"atom_id": "a_ctx"}])
        exc_b = _make_excerpt("eb:001", ["b1"], taxonomy_node_id="leaf",
                              context_atoms=[{"atom_id": "b_ctx"}])
        ra = _make_result(atoms_a, [exc_a])
        rb = _make_result(atoms_b, [exc_b])
        issues = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        ctx_dis = consensus["consensus_meta"]["context_atom_disagreements"]
        assert len(ctx_dis) == 1
        assert ctx_dis[0]["a_only_count"] == 1
        assert ctx_dis[0]["b_only_count"] == 1

    def test_no_disagreements_when_same_context(self):
        shared_text = "سياق مشترك للنموذجين"
        atoms_a = [
            _make_atom("a1", "prose_sentence", TEXT_HAMZA_OVERVIEW),
            _make_atom("a_ctx", "prose_sentence", shared_text),
        ]
        atoms_b = [
            _make_atom("b1", "prose_sentence", TEXT_HAMZA_OVERVIEW),
            _make_atom("b_ctx", "prose_sentence", shared_text),
        ]
        exc_a = _make_excerpt("ea:001", ["a1"], taxonomy_node_id="leaf",
                              context_atoms=[{"atom_id": "a_ctx"}])
        exc_b = _make_excerpt("eb:001", ["b1"], taxonomy_node_id="leaf",
                              context_atoms=[{"atom_id": "b_ctx"}])
        ra = _make_result(atoms_a, [exc_a])
        rb = _make_result(atoms_b, [exc_b])
        issues = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        assert consensus["consensus_meta"]["context_atom_disagreements"] == []


# ---------------------------------------------------------------------------
# Audit: consensus output uses merged atoms not just winning
# ---------------------------------------------------------------------------

class TestConsensusOutputAtomIntegrity:
    def test_arbiter_picks_losing_model_atoms_present(self):
        """When arbiter picks model B's excerpt, model B's atoms must be in output."""
        ra = _make_model_a_result()
        rb = _make_model_b_result_different_taxonomy()
        issues = {"errors": [], "warnings": [], "info": []}

        def pick_b_llm(system, user, model, api_key):
            return {
                "parsed": {
                    "correct_placement": "al_hala_2_tursam_wawan",
                    "reasoning": "B is right",
                    "confidence": "certain",
                },
                "input_tokens": 100,
                "output_tokens": 50,
                "stop_reason": "end_turn",
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
            call_llm_fn=pick_b_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
        )

        # The picked excerpt references model B's atoms
        atom_ids = {a["atom_id"] for a in consensus["atoms"]}
        for exc in consensus["excerpts"]:
            for ca in exc.get("core_atoms", []):
                aid = ca["atom_id"] if isinstance(ca, dict) else ca
                assert aid in atom_ids or any(
                    a_id.startswith(aid.split(":")[0]) for a_id in atom_ids
                ), f"Atom {aid} referenced by excerpt but not in atoms list"


# ---------------------------------------------------------------------------
# Audit: footnotes in consensus output include unmatched
# ---------------------------------------------------------------------------

class TestConsensusOutputFootnotes:
    def test_unmatched_footnotes_in_consensus_output(self):
        fn_text = "حاشية مشتركة بين النموذجين طويلة بما يكفي"
        ra = _make_model_a_result()
        ra["footnote_excerpts"] = [{"excerpt_id": "fn:a:001", "text": fn_text}]
        rb = _make_model_b_result_same_taxonomy()
        rb["footnote_excerpts"] = [
            {"excerpt_id": "fn:b:001", "text": fn_text},
            {"excerpt_id": "fn:b:002", "text": "حاشية فريدة من النموذج الثاني فقط جديدة"},
        ]
        issues = {"errors": [], "warnings": [], "info": []}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        fn_ids = {fn["excerpt_id"] for fn in consensus["footnote_excerpts"]}
        # Winning model (claude → model A) has fn:a:001
        assert "fn:a:001" in fn_ids
        # Model B's unmatched footnote should also be present
        assert "fn:b:002" in fn_ids


# ---------------------------------------------------------------------------
# Audit: context atom disagreements shown in review section
# ---------------------------------------------------------------------------

class TestReviewSectionContextAtoms:
    def test_context_atoms_shown(self):
        meta = {
            "mode": "consensus",
            "model_a": "claude", "model_b": "gpt4o",
            "winning_model": "claude",
            "matched_count": 1, "full_agreement_count": 1,
            "placement_disagreement_count": 0,
            "unmatched_a_count": 0, "unmatched_b_count": 0,
            "coverage_agreement": {"coverage_agreement_ratio": 1.0},
            "footnote_comparison": {"matched_count": 0, "unmatched_a_count": 0,
                                     "unmatched_b_count": 0},
            "exclusion_comparison": {"agreed_count": 0, "a_only_count": 0,
                                      "b_only_count": 0},
            "context_atom_disagreements": [{
                "excerpt_a_id": "ea:001",
                "excerpt_b_id": "eb:001",
                "a_count": 2,
                "b_count": 1,
                "a_only_count": 1,
                "b_only_count": 0,
            }],
            "case_type_disagreements": [],
            "discarded_excerpts": [],
            "arbiter_cost": {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0},
            "disagreements": [],
            "per_excerpt": [{
                "excerpt_id": "e1", "confidence": "high",
                "source_model": "claude", "agreement": "full", "flags": [],
            }],
        }
        md = generate_consensus_review_section(meta)
        assert "Context Atom Disagreements" in md
        assert "ea:001" in md


# ===========================================================================
# AUDIT ROUND 2 TESTS — verify F01-F26 fixes
# ===========================================================================

# ---------------------------------------------------------------------------
# F01: Stack-based JSON repair
# ---------------------------------------------------------------------------

class TestRepairTruncatedJson:
    """Test that the new stack-based repair handles brackets inside strings."""

    def test_brackets_inside_strings_not_counted(self):
        from tools.extract_passages import repair_truncated_json
        # Arabic text with [1] inside a string, then truncated
        text = '{"atoms": [{"text": "أقسام [1]", "id": "a1"'
        repaired = repair_truncated_json(text)
        parsed = json.loads(repaired)
        assert parsed["atoms"][0]["text"] == "أقسام [1]"
        assert parsed["atoms"][0]["id"] == "a1"

    def test_truncated_mid_string(self):
        from tools.extract_passages import repair_truncated_json
        text = '{"key": "value", "trunc": "abc'
        repaired = repair_truncated_json(text)
        parsed = json.loads(repaired)
        assert parsed["key"] == "value"
        assert "abc" in parsed["trunc"]

    def test_nested_structures(self):
        from tools.extract_passages import repair_truncated_json
        text = '{"a": [{"b": [1, 2'
        repaired = repair_truncated_json(text)
        parsed = json.loads(repaired)
        assert parsed["a"][0]["b"] == [1, 2]

    def test_already_complete_json(self):
        from tools.extract_passages import repair_truncated_json
        text = '{"key": "value"}'
        assert repair_truncated_json(text) == text

    def test_escaped_quotes(self):
        from tools.extract_passages import repair_truncated_json
        text = '{"key": "val\\"ue'
        repaired = repair_truncated_json(text)
        parsed = json.loads(repaired)
        assert 'val"ue' in parsed["key"]


# ---------------------------------------------------------------------------
# F03: Deep-copy protects original model results from remap mutation
# ---------------------------------------------------------------------------

class TestDeepCopyProtectsOriginals:
    def test_original_result_not_mutated_by_consensus(self):
        """After consensus, original per_model_results should be unchanged."""
        atoms_a = [_make_atom("shared:001", "prose_sentence", "Text A version")]
        atoms_b = [_make_atom("shared:001", "prose_sentence", "Text B different")]
        exc_a = _make_excerpt("ea:001", ["shared:001"], taxonomy_node_id="leaf_a")
        exc_b = _make_excerpt("eb:001", ["shared:001"], taxonomy_node_id="leaf_b")
        ra = _make_result(atoms_a, [exc_a])
        rb = _make_result(atoms_b, [exc_b])
        issues = {"errors": [], "warnings": [], "info": []}

        # Save original state of model B's excerpt
        orig_b_atom_id = rb["excerpts"][0]["core_atoms"][0]["atom_id"]

        def pick_b_llm(system, user, model, api_key):
            return {
                "parsed": {
                    "correct_placement": "leaf_b",
                    "reasoning": "B is right",
                    "confidence": "certain",
                },
                "input_tokens": 100,
                "output_tokens": 50,
                "stop_reason": "end_turn",
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
            call_llm_fn=pick_b_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
        )

        # Original model B result should NOT have remapped atom IDs
        assert rb["excerpts"][0]["core_atoms"][0]["atom_id"] == orig_b_atom_id


# ---------------------------------------------------------------------------
# F05: _unmapped variant mismatch doesn't trigger arbiter
# ---------------------------------------------------------------------------

class TestUnmappedVariantMismatch:
    def test_different_unmapped_variants_no_arbiter(self):
        """_unmapped vs __unmapped should be both_unmapped, not placement_disagreement."""
        atoms_a = [_make_atom("a1", "prose_sentence", TEXT_HAMZA_OVERVIEW)]
        atoms_b = [_make_atom("b1", "prose_sentence", TEXT_HAMZA_OVERVIEW)]
        exc_a = _make_excerpt("ea:001", ["a1"], taxonomy_node_id="_unmapped")
        exc_b = _make_excerpt("eb:001", ["b1"], taxonomy_node_id="__unmapped")
        ra = _make_result(atoms_a, [exc_a])
        rb = _make_result(atoms_b, [exc_b])

        arbiter_called = [False]

        def spy_llm(system, user, model, api_key):
            arbiter_called[0] = True
            return {
                "parsed": {"correct_placement": "_unmapped",
                           "reasoning": "test", "confidence": "certain"},
                "input_tokens": 10, "output_tokens": 5, "stop_reason": "end_turn",
            }

        issues = {"errors": [], "warnings": [], "info": []}
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
            call_llm_fn=spy_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
        )
        meta = consensus["consensus_meta"]
        assert meta["both_unmapped_count"] == 1
        assert meta["placement_disagreement_count"] == 0
        # Arbiter should NOT have been called
        assert not arbiter_called[0]


# ---------------------------------------------------------------------------
# F09: Consensus output atoms are filtered to referenced-only
# ---------------------------------------------------------------------------

class TestConsensusAtomFiltering:
    def test_unreferenced_atoms_removed(self):
        """Winning model atoms not in any consensus excerpt should be filtered out."""
        ra = _make_model_a_result()
        rb = _make_model_b_result_different_taxonomy()
        issues = {"errors": [], "warnings": [], "info": []}

        def pick_b_llm(system, user, model, api_key):
            return {
                "parsed": {
                    "correct_placement": "al_hala_2_tursam_wawan",
                    "reasoning": "B is right",
                    "confidence": "certain",
                },
                "input_tokens": 100,
                "output_tokens": 50,
                "stop_reason": "end_turn",
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
            call_llm_fn=pick_b_llm,
            arbiter_model="claude",
            arbiter_api_key="test-key",
        )

        # Every atom in the output should be referenced by some excerpt,
        # or be a heading/prose_tail/exclusion
        atom_ids = {a["atom_id"] for a in consensus["atoms"]}
        referenced = set()
        for exc in consensus["excerpts"]:
            for entry in (exc.get("core_atoms") or []):
                aid = entry["atom_id"] if isinstance(entry, dict) else entry
                referenced.add(aid)
            for entry in (exc.get("context_atoms") or []):
                aid = entry["atom_id"] if isinstance(entry, dict) else entry
                referenced.add(aid)
        excluded = {e.get("atom_id", "") for e in consensus["exclusions"]}
        heading_or_tail = set()
        for a in consensus["atoms"]:
            if a.get("atom_type") == "heading" or a.get("is_prose_tail"):
                heading_or_tail.add(a["atom_id"])
        allowed = referenced | excluded | heading_or_tail
        orphan_atoms = atom_ids - allowed
        assert orphan_atoms == set(), f"Unreferenced atoms in output: {orphan_atoms}"

    def test_full_agreement_atoms_filtered(self):
        """Even in full agreement, only referenced atoms should remain."""
        ra = _make_model_a_result()
        rb = _make_model_b_result_same_taxonomy()
        issues = {"errors": [], "warnings": [], "info": []}
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        # Should have atoms referenced by the 2 excerpts + heading in exclusions
        assert len(consensus["atoms"]) >= 2  # at least the 2 core atoms


# ========================================================================
# G01: _extract_taxonomy_context parses both v0 and v1 YAML
# ========================================================================

class TestExtractTaxonomyContextV1:
    """G01: The arbiter taxonomy context parser must find node IDs in both
    v0 (dict-key) and v1 (- id: value) YAML formats."""

    def test_v1_format_finds_node(self):
        yaml_text = (
            "  - id: ta3rif_alimlaa_lugha\n"
            "    title: تعريف الإملاء لغة\n"
            "    leaf: true\n"
            "  - id: other_node\n"
            "    title: Other\n"
            "    leaf: true\n"
        )
        result = _extract_taxonomy_context(
            yaml_text, "ta3rif_alimlaa_lugha", "other_node"
        )
        assert "ta3rif_alimlaa_lugha" in result
        assert "other_node" in result
        assert "not found" not in result

    def test_v0_format_finds_node(self):
        yaml_text = (
            "  ta3rif_alimlaa_lugha:\n"
            "    _leaf: true\n"
            "  other_node:\n"
            "    _leaf: true\n"
        )
        result = _extract_taxonomy_context(
            yaml_text, "ta3rif_alimlaa_lugha", "other_node"
        )
        assert "ta3rif_alimlaa_lugha" in result
        assert "not found" not in result

    def test_fallback_when_not_found(self):
        yaml_text = "  - id: something_else\n    leaf: true\n"
        result = _extract_taxonomy_context(
            yaml_text, "nonexistent_a", "nonexistent_b"
        )
        assert "not found" in result

    def test_deduplicates_overlapping_context(self):
        """Two nodes close together should not produce duplicate lines."""
        lines = []
        for i in range(20):
            lines.append(f"  - id: node_{i:03d}")
            lines.append(f"    title: Node {i}")
            lines.append(f"    leaf: true")
        yaml_text = "\n".join(lines)
        # node_002 and node_003 are adjacent — context windows overlap
        result = _extract_taxonomy_context(yaml_text, "node_002", "node_003")
        # Count occurrences of "node_002" — should appear only once
        assert result.count("- id: node_002") == 1


# ========================================================================
# G03: Atom ID disambiguation keeps 3-segment format
# ========================================================================

class TestAtomIdDisambiguationFormat:
    """G03: Disambiguated atom IDs must use _tag suffix, not :tag,
    to maintain the 3-segment book:section:seq format."""

    def test_3_segment_id_stays_3_segments(self):
        atoms_a = [_make_atom("qimlaa:matn:000001", "prose_sentence", "Version A")]
        atoms_b = [_make_atom("qimlaa:matn:000001", "prose_sentence", "Version B")]
        exc_b = _make_excerpt("eb:001", ["qimlaa:matn:000001"])
        ra = _make_result(atoms_a, [])
        rb = _make_result(atoms_b, [exc_b])
        consensus_excerpts = [
            {"excerpt": exc_b, "source_model": "gpt4o"},
        ]
        merged = _merge_atoms_for_consensus(
            ra, rb, consensus_excerpts, "claude", "gpt4o", "claude",
        )
        ids = {a["atom_id"] for a in merged}
        assert "qimlaa:matn:000001" in ids  # winning model's version
        assert "qimlaa:matn:000001_gpt4o" in ids  # losing model's version
        # Must still have exactly 3 colon-separated segments
        for aid in ids:
            assert len(aid.split(":")) == 3, f"ID {aid} should have 3 segments"

    def test_2_segment_id_gets_underscore_tag(self):
        atoms_a = [_make_atom("shared:001", "prose_sentence", "A")]
        atoms_b = [_make_atom("shared:001", "prose_sentence", "B")]
        exc_b = _make_excerpt("eb:001", ["shared:001"])
        ra = _make_result(atoms_a, [])
        rb = _make_result(atoms_b, [exc_b])
        consensus_excerpts = [
            {"excerpt": exc_b, "source_model": "gpt4o"},
        ]
        merged = _merge_atoms_for_consensus(
            ra, rb, consensus_excerpts, "claude", "gpt4o", "claude",
        )
        ids = {a["atom_id"] for a in merged}
        assert "shared:001_gpt4o" in ids


# ========================================================================
# G06: One-unmapped-one-real auto-picks real placement
# ========================================================================

class TestOneUnmappedOneReal:
    """G06: When one model places at _unmapped and the other at a real leaf,
    auto-pick the real placement without calling the arbiter."""

    def test_model_a_unmapped_model_b_real(self):
        ra = _make_result(
            [_make_atom("qa:m:001", "prose_sentence", "Some Arabic text")],
            [_make_excerpt("ea:001", ["qa:m:001"], taxonomy_node_id="_unmapped")],
        )
        rb = _make_result(
            [_make_atom("qb:m:001", "prose_sentence", "Some Arabic text")],
            [_make_excerpt("eb:001", ["qb:m:001"], taxonomy_node_id="real_leaf_node")],
        )
        issues = {"errors": [], "warnings": [], "info": []}
        arbiter_called = []

        def mock_arbiter(sys, usr, mdl, key):
            arbiter_called.append(True)
            return {"parsed": {"correct_placement": "real_leaf_node"},
                    "input_tokens": 0, "output_tokens": 0}

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
            call_llm_fn=mock_arbiter, arbiter_model="arb", arbiter_api_key="k",
        )
        # Arbiter should NOT have been called for this case
        assert len(arbiter_called) == 0
        # The real placement should be chosen
        exc = consensus["excerpts"][0]
        assert exc.get("taxonomy_node_id") == "real_leaf_node"
        # Metadata should show one_unmapped
        meta = consensus["consensus_meta"]
        assert meta["one_unmapped_count"] == 1
        assert meta["placement_disagreement_count"] == 0

    def test_model_a_real_model_b_unmapped(self):
        ra = _make_result(
            [_make_atom("qa:m:001", "prose_sentence", "Same text here")],
            [_make_excerpt("ea:001", ["qa:m:001"], taxonomy_node_id="real_node")],
        )
        rb = _make_result(
            [_make_atom("qb:m:001", "prose_sentence", "Same text here")],
            [_make_excerpt("eb:001", ["qb:m:001"], taxonomy_node_id="__unmapped")],
        )
        issues = {"errors": [], "warnings": [], "info": []}
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        exc = consensus["excerpts"][0]
        assert exc.get("taxonomy_node_id") == "real_node"


# ========================================================================
# G07: Arbiter fallback uses preferred model, not Model A
# ========================================================================

class TestArbiterFallbackUsesPreferred:
    """G07: When arbiter fails or returns garbage, fallback should use
    the winning/preferred model's placement, not hardcoded Model A."""

    def test_fallback_uses_model_b_when_preferred(self):
        match = {
            "excerpt_a": _make_excerpt("ea:001", ["qa:m:001"],
                                       taxonomy_node_id="node_a_place"),
            "excerpt_b": _make_excerpt("eb:001", ["qb:m:001"],
                                       taxonomy_node_id="node_b_place"),
            "taxonomy_a": "node_a_place",
            "taxonomy_b": "node_b_place",
            "text_a": "Some text",
            "text_overlap": 0.8,
        }

        def mock_failing_arbiter(sys, usr, mdl, key):
            raise RuntimeError("API down")

        result = resolve_placement_disagreement(
            match, "claude", "gpt4o", "",
            mock_failing_arbiter, "arb", "key",
            preferred_placement="node_b_place",
        )
        # Should fall back to preferred (model B), not model A
        assert result["correct_placement"] == "node_b_place"
        assert "preferred" in result["reasoning"].lower()

    def test_invalid_placement_falls_back_to_preferred(self):
        match = {
            "excerpt_a": _make_excerpt("ea:001", ["qa:m:001"],
                                       taxonomy_node_id="node_a"),
            "excerpt_b": _make_excerpt("eb:001", ["qb:m:001"],
                                       taxonomy_node_id="node_b"),
            "taxonomy_a": "node_a",
            "taxonomy_b": "node_b",
            "text_a": "Some text",
            "text_overlap": 0.8,
        }

        def mock_arbiter(sys, usr, mdl, key):
            return {
                "parsed": {"correct_placement": "totally_wrong_node",
                           "reasoning": "test", "confidence": "high"},
                "input_tokens": 10, "output_tokens": 10,
            }

        result = resolve_placement_disagreement(
            match, "claude", "gpt4o", "",
            mock_arbiter, "arb", "key",
            preferred_placement="node_b",
        )
        assert result["correct_placement"] == "node_b"


# ========================================================================
# G08+G09: Exclusions merged from both models
# ========================================================================

class TestExclusionMerge:
    """G08+G09: Consensus should merge exclusions from both models,
    not just use the winning model's."""

    def test_losing_model_exclusion_added(self):
        """If losing model excludes a heading that winning model missed,
        the exclusion should appear in consensus output."""
        heading_atom_a = _make_atom("qa:h:001", "heading", "باب الأول")
        main_atom_a = _make_atom("qa:m:001", "prose_sentence", "Main content A")
        heading_atom_b = _make_atom("qb:h:001", "heading", "باب الأول")
        main_atom_b = _make_atom("qb:m:001", "prose_sentence", "Main content A")

        ra = _make_result(
            [heading_atom_a, main_atom_a],
            [_make_excerpt("ea:001", ["qa:m:001"], taxonomy_node_id="leaf_1")],
        )
        # Winning model (A) has no exclusions
        ra["exclusions"] = []

        rb = _make_result(
            [heading_atom_b, main_atom_b],
            [_make_excerpt("eb:001", ["qb:m:001"], taxonomy_node_id="leaf_1")],
        )
        # Losing model (B) correctly excludes the heading
        rb["exclusions"] = [
            {"atom_id": "qb:h:001", "exclusion_reason": "heading_structural"}
        ]

        issues = {"errors": [], "warnings": [], "info": []}
        # Model A wins (default: fewer issues, tie goes to A)
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )

        excl_reasons = [e.get("exclusion_reason") for e in consensus["exclusions"]]
        assert "heading_structural" in excl_reasons
        # Should be flagged as coming from losing model
        flagged = [e for e in consensus["exclusions"]
                   if e.get("_consensus_flag")]
        assert len(flagged) >= 1


# ========================================================================
# H02: Exclusion merge checks atom_type to avoid cross-type collisions
# ========================================================================

class TestExclusionMergeAtomTypeCheck:
    """H02: When merging exclusions from the losing model, the match must
    check atom_type too, not just normalized text. Short Arabic headings
    like 'باب' could collide with prose atoms containing the same word."""

    def test_exclusion_does_not_target_core_atom(self):
        """An exclusion from the losing model must NOT point at an atom
        that is actively used in a consensus excerpt's core_atoms."""
        # Both models have an atom with the same text "باب"
        heading_a = _make_atom("qa:h:001", "heading", "باب")
        prose_a = _make_atom("qa:m:001", "prose_sentence", "باب")
        heading_b = _make_atom("qb:h:001", "heading", "باب")
        prose_b = _make_atom("qb:m:001", "prose_sentence", "باب")

        ra = _make_result(
            [heading_a, prose_a],
            [_make_excerpt("ea:001", ["qa:m:001"], taxonomy_node_id="leaf_1")],
        )
        ra["exclusions"] = []  # Winning model forgot to exclude heading

        rb = _make_result(
            [heading_b, prose_b],
            [_make_excerpt("eb:001", ["qb:m:001"], taxonomy_node_id="leaf_1")],
        )
        rb["exclusions"] = [
            {"atom_id": "qb:h:001", "exclusion_reason": "heading_structural"}
        ]

        issues = {"errors": [], "warnings": [], "info": []}
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )

        # The exclusion should NOT point at qa:m:001 (the core prose atom)
        for excl in consensus["exclusions"]:
            excl_id = excl.get("atom_id", "")
            for exc in consensus["excerpts"]:
                core_ids = [
                    (e["atom_id"] if isinstance(e, dict) else e)
                    for e in exc.get("core_atoms", [])
                ]
                assert excl_id not in core_ids, \
                    f"Exclusion {excl_id} conflicts with core atom in {exc.get('excerpt_id')}"


# ========================================================================
# H03: "Neither" verdict sets taxonomy_node_id to _unmapped
# ========================================================================

class TestNeitherVerdictSetsUnmapped:
    """H03: When arbiter says 'neither' placement is correct,
    the excerpt's taxonomy_node_id must be overridden to _unmapped."""

    def test_neither_sets_unmapped(self):
        ra = _make_result(
            [_make_atom("qa:m:001", "prose_sentence", "نص عربي طويل يكفي")],
            [_make_excerpt("ea:001", ["qa:m:001"], taxonomy_node_id="leaf_a")],
        )
        rb = _make_result(
            [_make_atom("qb:m:001", "prose_sentence", "نص عربي طويل يكفي")],
            [_make_excerpt("eb:001", ["qb:m:001"], taxonomy_node_id="leaf_b")],
        )
        issues = {"errors": [], "warnings": [], "info": []}

        def mock_arbiter(sys, usr, mdl, key):
            return {
                "parsed": {"correct_placement": "neither",
                           "reasoning": "both wrong", "confidence": "high"},
                "input_tokens": 10, "output_tokens": 10,
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
            call_llm_fn=mock_arbiter, arbiter_model="arb", arbiter_api_key="k",
        )
        exc = consensus["excerpts"][0]
        assert exc["taxonomy_node_id"] == "_unmapped"
        assert exc["taxonomy_path"] == "_unmapped"


# ========================================================================
# H04: Trailing-comma repair produces valid JSON
# ========================================================================

class TestTrailingCommaRepair:
    """H04: Truncation at comma boundaries must be repaired to valid JSON."""

    def test_trailing_comma_nested(self):
        from tools.extract_passages import repair_truncated_json
        text = '{"atoms": [{"id": "a"}, {"id": "b"}, '
        repaired = repair_truncated_json(text)
        import json
        parsed = json.loads(repaired)
        assert len(parsed["atoms"]) == 2

    def test_trailing_comma_in_array(self):
        from tools.extract_passages import repair_truncated_json
        text = '{"atoms": [{"id": "a"}, '
        repaired = repair_truncated_json(text)
        import json
        parsed = json.loads(repaired)
        assert len(parsed["atoms"]) == 1

    def test_trailing_comma_after_value(self):
        from tools.extract_passages import repair_truncated_json
        text = '{"a": 1, "b": 2, '
        repaired = repair_truncated_json(text)
        import json
        parsed = json.loads(repaired)
        assert parsed["a"] == 1
        assert parsed["b"] == 2


# ========================================================================
# H05: Arbiter uncertain → confidence "low"
# ========================================================================

class TestArbiterUncertainIsLow:
    """H05: When arbiter is unavailable or uncertain, confidence must be
    'low' not 'medium', so these items surface in human review."""

    def test_uncertain_arbiter_gives_low_confidence(self):
        ra = _make_result(
            [_make_atom("qa:m:001", "prose_sentence", "Arabic text here long")],
            [_make_excerpt("ea:001", ["qa:m:001"], taxonomy_node_id="leaf_x")],
        )
        rb = _make_result(
            [_make_atom("qb:m:001", "prose_sentence", "Arabic text here long")],
            [_make_excerpt("eb:001", ["qb:m:001"], taxonomy_node_id="leaf_y")],
        )
        issues = {"errors": [], "warnings": [], "info": []}

        def mock_uncertain_arbiter(sys, usr, mdl, key):
            return {
                "parsed": {"correct_placement": "leaf_x",
                           "reasoning": "unsure", "confidence": "uncertain"},
                "input_tokens": 10, "output_tokens": 10,
            }

        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
            call_llm_fn=mock_uncertain_arbiter,
            arbiter_model="arb", arbiter_api_key="k",
        )
        meta = consensus["consensus_meta"]
        pe = [p for p in meta["per_excerpt"]
              if p["agreement"] == "placement_disagreement"]
        assert len(pe) == 1
        assert pe[0]["confidence"] == "low"


# ========================================================================
# H06: Enrichment of winning model's empty fields from losing model
# ========================================================================

class TestFieldEnrichmentOnFullAgreement:
    """H06: When both models agree on taxonomy but the winning model has
    empty metadata fields, enrich from the losing model."""

    def test_empty_case_types_enriched(self):
        ra = _make_result(
            [_make_atom("qa:m:001", "prose_sentence", "Test text content")],
            [_make_excerpt("ea:001", ["qa:m:001"], taxonomy_node_id="leaf_1",
                           case_types=[])],
        )
        rb = _make_result(
            [_make_atom("qb:m:001", "prose_sentence", "Test text content")],
            [_make_excerpt("eb:001", ["qb:m:001"], taxonomy_node_id="leaf_1",
                           case_types=["A1_pure_definition", "B2_rule_statement"])],
        )
        issues = {"errors": [], "warnings": [], "info": []}
        # Model A wins (tie goes to A)
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        exc = consensus["excerpts"][0]
        assert exc["case_types"] == ["A1_pure_definition", "B2_rule_statement"]
        # Check enrichment flag
        meta = consensus["consensus_meta"]
        pe = meta["per_excerpt"][0]
        assert any("Enriched" in f for f in pe["flags"])

    def test_nonempty_fields_not_overwritten(self):
        """Winning model's non-empty fields should NOT be overwritten."""
        ra = _make_result(
            [_make_atom("qa:m:001", "prose_sentence", "Test text content")],
            [_make_excerpt("ea:001", ["qa:m:001"], taxonomy_node_id="leaf_1",
                           case_types=["A1_pure_definition"],
                           boundary_reasoning="Good reasoning here")],
        )
        rb = _make_result(
            [_make_atom("qb:m:001", "prose_sentence", "Test text content")],
            [_make_excerpt("eb:001", ["qb:m:001"], taxonomy_node_id="leaf_1",
                           case_types=["B2_rule_statement"],
                           boundary_reasoning="Different reasoning")],
        )
        issues = {"errors": [], "warnings": [], "info": []}
        consensus = build_consensus(
            "P004", ra, rb, "claude", "gpt4o", issues, issues,
        )
        exc = consensus["excerpts"][0]
        # Winning model's values should be preserved
        assert exc["case_types"] == ["A1_pure_definition"]
        assert exc["boundary_reasoning"] == "Good reasoning here"
