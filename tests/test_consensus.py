"""
Tests for Multi-Model Consensus Engine (tools/consensus.py)

Run: python -m pytest tests/test_consensus.py -q
"""

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
    build_consensus,
    generate_consensus_review_section,
    _extract_taxonomy_context,
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
        # Disagreement excerpt should have medium confidence
        meta = consensus["consensus_meta"]
        disagreement_excerpts = [
            pe for pe in meta["per_excerpt"]
            if pe["agreement"] == "placement_disagreement"
        ]
        assert len(disagreement_excerpts) == 1
        assert disagreement_excerpts[0]["confidence"] == "medium"


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
