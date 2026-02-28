"""Tests for tools/evolve_taxonomy.py — Taxonomy Evolution Engine (Phase A)."""

import json
import pytest

from tools.evolve_taxonomy import (
    EvolutionProposal,
    EvolutionSignal,
    deduplicate_signals,
    extract_taxonomy_section,
    generate_change_records,
    generate_proposal_json,
    generate_review_md,
    propose_evolution_for_signal,
    resolve_excerpt_full_text,
    run_evolution,
    scan_cluster_signals,
    scan_unmapped_signals,
    scan_user_signals,
    validate_proposed_node_id,
)
from tools.assemble_excerpts import (
    TaxonomyNodeInfo,
    build_atoms_index,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_atom(atom_id: str, text: str, atype: str = "prose_sentence") -> dict:
    return {"atom_id": atom_id, "type": atype, "text": text}


def _make_excerpt(
    excerpt_id: str,
    node_id: str,
    core_atoms: list[str],
    title: str = "",
    context_atoms: list[str] | None = None,
    boundary_reasoning: str = "",
) -> dict:
    return {
        "excerpt_id": excerpt_id,
        "excerpt_title": title or f"Title for {excerpt_id}",
        "taxonomy_node_id": node_id,
        "taxonomy_path": f"path > to > {node_id}",
        "core_atoms": core_atoms,
        "context_atoms": context_atoms or [],
        "boundary_reasoning": boundary_reasoning or "Test reasoning",
    }


def _make_passage(
    pid: str,
    atoms: list[dict],
    excerpts: list[dict],
    footnote_excerpts: list[dict] | None = None,
) -> dict:
    return {
        "passage_id": pid,
        "filename": f"{pid}_extraction.json",
        "atoms": atoms,
        "excerpts": excerpts,
        "footnote_excerpts": footnote_excerpts or [],
    }


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


SAMPLE_V1_YAML = """\
taxonomy:
  id: imlaa_v1_0
  title: علم الإملاء
  language: ar
  nodes:
  - id: alhamza
    title: الهمزة
    children:
    - id: ta3rif_alhamza
      title: تعريف الهمزة
      leaf: true
    - id: hamzat_alwasl
      title: همزة الوصل
      leaf: true
    - id: hamzat_alqat3
      title: همزة القطع
      leaf: true
"""

SAMPLE_V0_YAML = """\
imlaa:
  alhamza:
    ta3rif_alhamza:
      _leaf: true
    hamzat_alwasl:
      _leaf: true
    hamzat_alqat3:
      _leaf: true
"""


# ---------------------------------------------------------------------------
# Tests: Signal Detection
# ---------------------------------------------------------------------------

class TestSignalDetection:
    """Tests for scan_unmapped_signals, scan_cluster_signals, scan_user_signals."""

    def test_detects_unmapped_excerpts(self):
        atoms = [_make_atom("a1", "نص عربي للاختبار")]
        excerpts = [_make_excerpt("q:exc:001", "_unmapped", ["a1"])]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}

        signals = scan_unmapped_signals([passage], atoms_indexes, "imlaa")

        assert len(signals) == 1
        assert signals[0].signal_type == "unmapped"
        assert signals[0].node_id == "_unmapped"
        assert signals[0].excerpt_ids == ["q:exc:001"]
        assert "نص عربي للاختبار" in signals[0].excerpt_texts[0]

    def test_detects_empty_node_id_as_unmapped(self):
        atoms = [_make_atom("a1", "text")]
        excerpts = [_make_excerpt("q:exc:001", "", ["a1"])]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}

        signals = scan_unmapped_signals([passage], atoms_indexes, "imlaa")
        assert len(signals) == 1
        assert signals[0].signal_type == "unmapped"

    def test_no_unmapped_signals_from_placed_excerpts(self):
        atoms = [_make_atom("a1", "text")]
        excerpts = [_make_excerpt("q:exc:001", "ta3rif_alhamza", ["a1"])]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}

        signals = scan_unmapped_signals([passage], atoms_indexes, "imlaa")
        assert len(signals) == 0

    def test_detects_same_book_clusters(self):
        atoms = [
            _make_atom("a1", "نص أول"),
            _make_atom("a2", "نص ثاني"),
        ]
        excerpts = [
            _make_excerpt("q:exc:001", "ta3rif_alhamza", ["a1"]),
            _make_excerpt("q:exc:002", "ta3rif_alhamza", ["a2"]),
        ]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}
        taxonomy_map = _make_taxonomy_map()

        signals = scan_cluster_signals(
            [passage], atoms_indexes, taxonomy_map, "imlaa",
        )

        assert len(signals) == 1
        assert signals[0].signal_type == "same_book_cluster"
        assert signals[0].node_id == "ta3rif_alhamza"
        assert len(signals[0].excerpt_ids) == 2

    def test_no_cluster_signal_for_single_excerpt(self):
        atoms = [_make_atom("a1", "text")]
        excerpts = [_make_excerpt("q:exc:001", "ta3rif_alhamza", ["a1"])]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}
        taxonomy_map = _make_taxonomy_map()

        signals = scan_cluster_signals(
            [passage], atoms_indexes, taxonomy_map, "imlaa",
        )
        assert len(signals) == 0

    def test_cluster_with_three_excerpts(self):
        atoms = [
            _make_atom("a1", "نص 1"),
            _make_atom("a2", "نص 2"),
            _make_atom("a3", "نص 3"),
        ]
        excerpts = [
            _make_excerpt("q:exc:001", "hamzat_alwasl", ["a1"]),
            _make_excerpt("q:exc:002", "hamzat_alwasl", ["a2"]),
            _make_excerpt("q:exc:003", "hamzat_alwasl", ["a3"]),
        ]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}
        taxonomy_map = _make_taxonomy_map()

        signals = scan_cluster_signals(
            [passage], atoms_indexes, taxonomy_map, "imlaa",
        )
        assert len(signals) == 1
        assert len(signals[0].excerpt_ids) == 3

    def test_user_specified_node(self):
        atoms = [_make_atom("a1", "نص عربي")]
        excerpts = [_make_excerpt("q:exc:001", "ta3rif_alhamza", ["a1"])]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}
        taxonomy_map = _make_taxonomy_map()

        signals = scan_user_signals(
            ["ta3rif_alhamza"], [passage], atoms_indexes, taxonomy_map, "imlaa",
        )

        assert len(signals) == 1
        assert signals[0].signal_type == "user_specified"
        assert signals[0].node_id == "ta3rif_alhamza"
        assert signals[0].excerpt_ids == ["q:exc:001"]

    def test_user_specified_node_no_excerpts(self):
        """User specifies a node with no excerpts — signal still generated."""
        atoms = [_make_atom("a1", "text")]
        excerpts = [_make_excerpt("q:exc:001", "hamzat_alwasl", ["a1"])]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}
        taxonomy_map = _make_taxonomy_map()

        signals = scan_user_signals(
            ["ta3rif_alhamza"], [passage], atoms_indexes, taxonomy_map, "imlaa",
        )

        assert len(signals) == 1
        assert signals[0].excerpt_ids == []

    def test_no_cluster_for_different_books(self):
        """Excerpts from DIFFERENT books at same node = expected, NOT a cluster signal."""
        atoms = [
            _make_atom("a1", "نص الكتاب الأول"),
            _make_atom("a2", "نص الكتاب الثاني"),
        ]
        exc1 = _make_excerpt("q:exc:001", "ta3rif_alhamza", ["a1"])
        exc1["book_id"] = "book_alpha"
        exc2 = _make_excerpt("q:exc:002", "ta3rif_alhamza", ["a2"])
        exc2["book_id"] = "book_beta"
        passage = _make_passage("P001", atoms, [exc1, exc2])
        atoms_indexes = {"P001": build_atoms_index(atoms)}
        taxonomy_map = _make_taxonomy_map()

        signals = scan_cluster_signals(
            [passage], atoms_indexes, taxonomy_map, "imlaa",
        )
        assert len(signals) == 0

    def test_cluster_only_for_same_book(self):
        """Three excerpts at same node: 2 from book A, 1 from book B.
        Only book A should produce a cluster signal."""
        atoms = [
            _make_atom("a1", "نص 1"),
            _make_atom("a2", "نص 2"),
            _make_atom("a3", "نص 3"),
        ]
        exc1 = _make_excerpt("q:exc:001", "ta3rif_alhamza", ["a1"])
        exc1["book_id"] = "book_alpha"
        exc2 = _make_excerpt("q:exc:002", "ta3rif_alhamza", ["a2"])
        exc2["book_id"] = "book_alpha"
        exc3 = _make_excerpt("q:exc:003", "ta3rif_alhamza", ["a3"])
        exc3["book_id"] = "book_beta"
        passage = _make_passage("P001", atoms, [exc1, exc2, exc3])
        atoms_indexes = {"P001": build_atoms_index(atoms)}
        taxonomy_map = _make_taxonomy_map()

        signals = scan_cluster_signals(
            [passage], atoms_indexes, taxonomy_map, "imlaa",
        )
        assert len(signals) == 1
        assert set(signals[0].excerpt_ids) == {"q:exc:001", "q:exc:002"}

    def test_signal_deduplication(self):
        sig1 = EvolutionSignal(
            signal_type="same_book_cluster",
            node_id="ta3rif_alhamza",
            science="imlaa",
            excerpt_ids=["q:exc:001"],
            excerpt_texts=["text1"],
            excerpt_metadata=[{"excerpt_id": "q:exc:001"}],
            context="1 excerpt",
        )
        sig2 = EvolutionSignal(
            signal_type="same_book_cluster",
            node_id="ta3rif_alhamza",
            science="imlaa",
            excerpt_ids=["q:exc:002"],
            excerpt_texts=["text2"],
            excerpt_metadata=[{"excerpt_id": "q:exc:002"}],
            context="1 excerpt",
        )

        result = deduplicate_signals([sig1, sig2])
        assert len(result) == 1
        assert len(result[0].excerpt_ids) == 2
        assert "q:exc:001" in result[0].excerpt_ids
        assert "q:exc:002" in result[0].excerpt_ids

    def test_dedup_preserves_different_types(self):
        sig1 = EvolutionSignal(
            signal_type="unmapped", node_id="_unmapped", science="imlaa",
            excerpt_ids=["e1"], excerpt_texts=["t1"],
            excerpt_metadata=[{}], context="",
        )
        sig2 = EvolutionSignal(
            signal_type="same_book_cluster", node_id="ta3rif_alhamza",
            science="imlaa", excerpt_ids=["e2"], excerpt_texts=["t2"],
            excerpt_metadata=[{}], context="",
        )

        result = deduplicate_signals([sig1, sig2])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Tests: Excerpt Text Resolution
# ---------------------------------------------------------------------------

class TestExcerptTextResolution:

    def test_resolves_core_atoms(self):
        atoms_index = {
            "a1": {"atom_id": "a1", "text": "الجزء الأول"},
            "a2": {"atom_id": "a2", "text": "الجزء الثاني"},
        }
        excerpt = _make_excerpt("e1", "node", ["a1", "a2"])
        text = resolve_excerpt_full_text(excerpt, atoms_index)
        assert "الجزء الأول" in text
        assert "الجزء الثاني" in text

    def test_resolves_context_and_core(self):
        atoms_index = {
            "a1": {"atom_id": "a1", "text": "سياق"},
            "a2": {"atom_id": "a2", "text": "محتوى أساسي"},
        }
        excerpt = _make_excerpt("e1", "node", ["a2"], context_atoms=["a1"])
        text = resolve_excerpt_full_text(excerpt, atoms_index)
        assert "سياق" in text
        assert "محتوى أساسي" in text
        # Context should come before core
        assert text.index("سياق") < text.index("محتوى أساسي")

    def test_missing_atoms_skipped(self):
        atoms_index = {"a1": {"atom_id": "a1", "text": "موجود"}}
        excerpt = _make_excerpt("e1", "node", ["a1", "a_missing"])
        text = resolve_excerpt_full_text(excerpt, atoms_index)
        assert "موجود" in text


# ---------------------------------------------------------------------------
# Tests: Taxonomy Context Extraction
# ---------------------------------------------------------------------------

class TestTaxonomyContextExtraction:

    def test_extracts_v1_context(self):
        context = extract_taxonomy_section(
            SAMPLE_V1_YAML, ["ta3rif_alhamza"], context_lines=3,
        )
        assert "ta3rif_alhamza" in context
        assert "تعريف الهمزة" in context

    def test_extracts_v0_context(self):
        context = extract_taxonomy_section(
            SAMPLE_V0_YAML, ["ta3rif_alhamza"], context_lines=3,
        )
        assert "ta3rif_alhamza" in context

    def test_missing_node_returns_fallback(self):
        context = extract_taxonomy_section(
            SAMPLE_V1_YAML, ["nonexistent_node"],
        )
        assert "not found" in context

    def test_multiple_nodes(self):
        context = extract_taxonomy_section(
            SAMPLE_V1_YAML, ["ta3rif_alhamza", "hamzat_alwasl"],
        )
        assert "ta3rif_alhamza" in context
        assert "hamzat_alwasl" in context


# ---------------------------------------------------------------------------
# Tests: Node ID Validation
# ---------------------------------------------------------------------------

class TestNodeIdValidation:

    def test_valid_id_accepted(self):
        taxonomy_map = _make_taxonomy_map()
        errors = validate_proposed_node_id("hamza_new_case_1", taxonomy_map)
        assert errors == []

    def test_arabic_characters_rejected(self):
        taxonomy_map = _make_taxonomy_map()
        errors = validate_proposed_node_id("الهمزة", taxonomy_map)
        assert len(errors) > 0
        assert "invalid characters" in errors[0]

    def test_spaces_rejected(self):
        taxonomy_map = _make_taxonomy_map()
        errors = validate_proposed_node_id("hamza new", taxonomy_map)
        assert len(errors) > 0

    def test_uppercase_rejected(self):
        taxonomy_map = _make_taxonomy_map()
        errors = validate_proposed_node_id("Hamza_Case", taxonomy_map)
        assert len(errors) > 0

    def test_duplicate_id_rejected(self):
        taxonomy_map = _make_taxonomy_map()
        errors = validate_proposed_node_id("ta3rif_alhamza", taxonomy_map)
        assert any("already exists" in e for e in errors)

    def test_too_long_id_rejected(self):
        taxonomy_map = _make_taxonomy_map()
        long_id = "a" * 61
        errors = validate_proposed_node_id(long_id, taxonomy_map)
        assert any("too long" in e for e in errors)

    def test_empty_id_rejected(self):
        taxonomy_map = _make_taxonomy_map()
        errors = validate_proposed_node_id("", taxonomy_map)
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Tests: Proposal Generation (with mock LLM)
# ---------------------------------------------------------------------------

class TestProposalGeneration:

    def _make_signal_unmapped(self) -> EvolutionSignal:
        return EvolutionSignal(
            signal_type="unmapped",
            node_id="_unmapped",
            science="imlaa",
            excerpt_ids=["q:exc:001"],
            excerpt_texts=["نص عربي يحتاج تصنيف"],
            excerpt_metadata=[{
                "excerpt_id": "q:exc:001",
                "excerpt_title": "حالة خاصة",
                "taxonomy_node_id": "_unmapped",
                "boundary_reasoning": "No fitting leaf",
            }],
            context="Unmapped excerpt",
        )

    def _make_signal_cluster(self) -> EvolutionSignal:
        return EvolutionSignal(
            signal_type="same_book_cluster",
            node_id="ta3rif_alhamza",
            science="imlaa",
            excerpt_ids=["q:exc:001", "q:exc:002"],
            excerpt_texts=["نص أول", "نص ثاني"],
            excerpt_metadata=[
                {"excerpt_id": "q:exc:001", "excerpt_title": "الموضع الأول"},
                {"excerpt_id": "q:exc:002", "excerpt_title": "الموضع الثاني"},
            ],
            context="2 excerpts at ta3rif_alhamza",
        )

    def test_unmapped_proposal_new_node(self):
        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {
                "parsed": {
                    "action": "new_node",
                    "existing_leaf_id": None,
                    "new_node": {
                        "node_id": "hamza_special_case",
                        "title_ar": "حالة خاصة للهمزة",
                        "parent_node_id": "alhamza",
                        "leaf": True,
                    },
                    "reasoning": "This excerpt covers a special hamza case",
                    "confidence": "likely",
                },
                "input_tokens": 500,
                "output_tokens": 100,
                "stop_reason": "end_turn",
            }

        signal = self._make_signal_unmapped()
        taxonomy_map = _make_taxonomy_map()

        proposal = propose_evolution_for_signal(
            signal=signal,
            taxonomy_yaml_raw=SAMPLE_V1_YAML,
            taxonomy_map=taxonomy_map,
            model="test-model",
            api_key="test-key",
            call_llm_fn=mock_llm,
            proposal_seq=1,
        )

        assert proposal is not None
        assert proposal.change_type == "node_added"
        assert proposal.parent_node_id == "alhamza"
        assert len(proposal.new_nodes) == 1
        assert proposal.new_nodes[0]["node_id"] == "hamza_special_case"
        assert proposal.confidence == "likely"
        assert proposal.proposal_id == "EP-001"

    def test_cluster_proposal_split(self):
        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {
                "parsed": {
                    "action": "split",
                    "new_nodes": [
                        {"node_id": "ta3rif_alhamza_lugha", "title_ar": "تعريف الهمزة لغة", "leaf": True},
                        {"node_id": "ta3rif_alhamza_istilah", "title_ar": "تعريف الهمزة اصطلاحاً", "leaf": True},
                    ],
                    "redistribution": {
                        "q:exc:001": "ta3rif_alhamza_lugha",
                        "q:exc:002": "ta3rif_alhamza_istilah",
                    },
                    "reasoning": "The excerpts cover different aspects of hamza definition",
                    "confidence": "certain",
                },
                "input_tokens": 800,
                "output_tokens": 200,
                "stop_reason": "end_turn",
            }

        signal = self._make_signal_cluster()
        taxonomy_map = _make_taxonomy_map()

        proposal = propose_evolution_for_signal(
            signal=signal,
            taxonomy_yaml_raw=SAMPLE_V1_YAML,
            taxonomy_map=taxonomy_map,
            model="test-model",
            api_key="test-key",
            call_llm_fn=mock_llm,
            proposal_seq=1,
        )

        assert proposal is not None
        assert proposal.change_type == "leaf_granulated"
        assert proposal.parent_node_id == "ta3rif_alhamza"
        assert len(proposal.new_nodes) == 2
        assert len(proposal.redistribution) == 2

    def test_keep_returns_none(self):
        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {
                "parsed": {
                    "action": "keep",
                    "new_nodes": [],
                    "redistribution": {},
                    "reasoning": "Excerpts cover the same topic",
                    "confidence": "certain",
                },
                "input_tokens": 400,
                "output_tokens": 50,
                "stop_reason": "end_turn",
            }

        signal = self._make_signal_cluster()
        taxonomy_map = _make_taxonomy_map()

        proposal = propose_evolution_for_signal(
            signal=signal,
            taxonomy_yaml_raw=SAMPLE_V1_YAML,
            taxonomy_map=taxonomy_map,
            model="test-model",
            api_key="test-key",
            call_llm_fn=mock_llm,
        )

        assert proposal is None

    def test_existing_leaf_returns_none(self):
        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {
                "parsed": {
                    "action": "existing_leaf",
                    "existing_leaf_id": "hamzat_alwasl",
                    "new_node": None,
                    "reasoning": "This excerpt belongs at hamzat_alwasl",
                    "confidence": "certain",
                },
                "input_tokens": 400,
                "output_tokens": 80,
                "stop_reason": "end_turn",
            }

        signal = self._make_signal_unmapped()
        taxonomy_map = _make_taxonomy_map()

        proposal = propose_evolution_for_signal(
            signal=signal,
            taxonomy_yaml_raw=SAMPLE_V1_YAML,
            taxonomy_map=taxonomy_map,
            model="test-model",
            api_key="test-key",
            call_llm_fn=mock_llm,
        )

        assert proposal is None

    def test_llm_error_returns_none(self):
        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            raise ConnectionError("API timeout")

        signal = self._make_signal_unmapped()
        taxonomy_map = _make_taxonomy_map()

        proposal = propose_evolution_for_signal(
            signal=signal,
            taxonomy_yaml_raw=SAMPLE_V1_YAML,
            taxonomy_map=taxonomy_map,
            model="test-model",
            api_key="test-key",
            call_llm_fn=mock_llm,
        )

        assert proposal is None

    def test_cost_tracking(self):
        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {
                "parsed": {
                    "action": "new_node",
                    "new_node": {
                        "node_id": "test_node",
                        "title_ar": "test",
                        "parent_node_id": "alhamza",
                        "leaf": True,
                    },
                    "reasoning": "test",
                    "confidence": "certain",
                },
                "input_tokens": 1000,
                "output_tokens": 200,
                "stop_reason": "end_turn",
            }

        signal = self._make_signal_unmapped()
        taxonomy_map = _make_taxonomy_map()

        proposal = propose_evolution_for_signal(
            signal=signal,
            taxonomy_yaml_raw=SAMPLE_V1_YAML,
            taxonomy_map=taxonomy_map,
            model="claude-sonnet-4-5-20250929",
            api_key="test-key",
            call_llm_fn=mock_llm,
        )

        assert proposal is not None
        assert proposal.cost["input_tokens"] == 1000
        assert proposal.cost["output_tokens"] == 200
        assert proposal.cost["total_cost"] > 0

    def test_all_nodes_invalid_returns_none(self):
        """If LLM proposes only invalid node IDs, proposal is rejected entirely."""
        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {
                "parsed": {
                    "action": "split",
                    "new_nodes": [
                        {"node_id": "UPPERCASE_BAD", "title_ar": "خطأ ١", "leaf": True},
                        {"node_id": "has spaces", "title_ar": "خطأ ٢", "leaf": True},
                    ],
                    "redistribution": {
                        "q:exc:001": "UPPERCASE_BAD",
                        "q:exc:002": "has spaces",
                    },
                    "reasoning": "Invalid IDs proposed",
                    "confidence": "certain",
                },
                "input_tokens": 500,
                "output_tokens": 100,
                "stop_reason": "end_turn",
            }

        signal = self._make_signal_cluster()
        taxonomy_map = _make_taxonomy_map()

        proposal = propose_evolution_for_signal(
            signal=signal,
            taxonomy_yaml_raw=SAMPLE_V1_YAML,
            taxonomy_map=taxonomy_map,
            model="test-model",
            api_key="test-key",
            call_llm_fn=mock_llm,
        )

        assert proposal is None

    def test_some_nodes_invalid_partial_proposal(self):
        """If LLM proposes mix of valid and invalid node IDs,
        invalid ones are excluded but proposal proceeds."""
        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {
                "parsed": {
                    "action": "split",
                    "new_nodes": [
                        {"node_id": "valid_node_id", "title_ar": "صحيح", "leaf": True},
                        {"node_id": "INVALID_ID", "title_ar": "خطأ", "leaf": True},
                    ],
                    "redistribution": {
                        "q:exc:001": "valid_node_id",
                        "q:exc:002": "INVALID_ID",
                    },
                    "reasoning": "Mixed validity",
                    "confidence": "certain",
                },
                "input_tokens": 500,
                "output_tokens": 100,
                "stop_reason": "end_turn",
            }

        signal = self._make_signal_cluster()
        taxonomy_map = _make_taxonomy_map()

        proposal = propose_evolution_for_signal(
            signal=signal,
            taxonomy_yaml_raw=SAMPLE_V1_YAML,
            taxonomy_map=taxonomy_map,
            model="test-model",
            api_key="test-key",
            call_llm_fn=mock_llm,
        )

        assert proposal is not None
        assert len(proposal.new_nodes) == 1
        assert proposal.new_nodes[0]["node_id"] == "valid_node_id"
        assert proposal.confidence == "uncertain"  # downgraded due to rejected nodes


# ---------------------------------------------------------------------------
# Tests: Change Record Generation
# ---------------------------------------------------------------------------

class TestChangeRecordGeneration:

    def _make_proposal(
        self, change_type="node_added", parent="alhamza",
    ) -> EvolutionProposal:
        signal = EvolutionSignal(
            signal_type="unmapped", node_id="_unmapped", science="imlaa",
            excerpt_ids=["q:exc:001"], excerpt_texts=["text"],
            excerpt_metadata=[{}], context="test",
        )
        return EvolutionProposal(
            signal=signal,
            proposal_id="EP-001",
            change_type=change_type,
            parent_node_id=parent,
            new_nodes=[{
                "node_id": "new_leaf_node",
                "title_ar": "عقدة جديدة",
                "leaf": True,
            }],
            redistribution={"q:exc:001": "new_leaf_node"},
            reasoning="Test reasoning",
            confidence="likely",
            model="test-model",
            cost={"input_tokens": 100, "output_tokens": 50, "total_cost": 0.01},
        )

    def test_node_added_format(self):
        proposal = self._make_proposal(change_type="node_added")
        records = generate_change_records([proposal], "imlaa_v1_0", "qimlaa")

        assert len(records) == 1
        rec = records[0]
        assert rec["record_type"] == "taxonomy_change"
        assert rec["change_type"] == "node_added"
        assert rec["node_id"] == "new_leaf_node"
        assert rec["parent_node_id"] == "alhamza"
        assert rec["book_id"] == "qimlaa"
        assert rec["taxonomy_version_before"] == "imlaa_v1_0"
        assert rec["taxonomy_version_after"] == "imlaa_v1_1"
        assert "TC-001" in rec["change_id"]

    def test_leaf_granulated_format(self):
        signal = EvolutionSignal(
            signal_type="same_book_cluster", node_id="ta3rif_alhamza",
            science="imlaa", excerpt_ids=["e1", "e2"],
            excerpt_texts=["t1", "t2"], excerpt_metadata=[{}, {}],
            context="test",
        )
        proposal = EvolutionProposal(
            signal=signal,
            proposal_id="EP-001",
            change_type="leaf_granulated",
            parent_node_id="ta3rif_alhamza",
            new_nodes=[
                {"node_id": "sub_a", "title_ar": "فرع أ"},
                {"node_id": "sub_b", "title_ar": "فرع ب"},
            ],
            redistribution={"e1": "sub_a", "e2": "sub_b"},
            reasoning="Different subtopics",
            confidence="certain",
            model="test-model",
            cost={"input_tokens": 100, "output_tokens": 50, "total_cost": 0.01},
        )

        records = generate_change_records([proposal], "imlaa_v1_0", "qimlaa")

        assert len(records) == 1
        rec = records[0]
        assert rec["change_type"] == "leaf_granulated"
        assert rec["node_id"] == "ta3rif_alhamza"
        assert len(rec["new_children"]) == 2
        assert rec["migration"] == {"e1": "sub_a", "e2": "sub_b"}

    def test_change_ids_sequential(self):
        p1 = self._make_proposal()
        p2 = self._make_proposal()
        records = generate_change_records([p1, p2], "imlaa_v1_0", "qimlaa")

        ids = [r["change_id"] for r in records]
        assert "TC-001" in ids
        assert "TC-002" in ids

    def test_version_bump(self):
        records = generate_change_records(
            [self._make_proposal()], "balagha_v0_4", "jawahir",
        )
        assert records[0]["taxonomy_version_before"] == "balagha_v0_4"
        assert records[0]["taxonomy_version_after"] == "balagha_v0_5"


# ---------------------------------------------------------------------------
# Tests: Review Markdown
# ---------------------------------------------------------------------------

class TestReviewMarkdown:

    def test_contains_signal_summary(self):
        signal = EvolutionSignal(
            signal_type="unmapped", node_id="_unmapped", science="imlaa",
            excerpt_ids=["e1"], excerpt_texts=["نص"],
            excerpt_metadata=[{"excerpt_title": "عنوان"}], context="test",
        )
        taxonomy_map = _make_taxonomy_map()
        md = generate_review_md([signal], [], "imlaa", "imlaa_v1_0", taxonomy_map, "model")

        assert "Signals detected:" in md
        assert "1" in md
        assert "Proposals generated:" in md

    def test_contains_arabic_text(self):
        signal = EvolutionSignal(
            signal_type="unmapped", node_id="_unmapped", science="imlaa",
            excerpt_ids=["e1"], excerpt_texts=["نص عربي مهم"],
            excerpt_metadata=[{"excerpt_title": "عنوان الاقتباس"}], context="test",
        )
        taxonomy_map = _make_taxonomy_map()
        md = generate_review_md([signal], [], "imlaa", "imlaa_v1_0", taxonomy_map, "model")

        assert "نص عربي مهم" in md

    def test_contains_proposal_details(self):
        signal = EvolutionSignal(
            signal_type="unmapped", node_id="_unmapped", science="imlaa",
            excerpt_ids=["e1"], excerpt_texts=["text"],
            excerpt_metadata=[{}], context="test",
        )
        proposal = EvolutionProposal(
            signal=signal, proposal_id="EP-001",
            change_type="node_added", parent_node_id="alhamza",
            new_nodes=[{"node_id": "new_node", "title_ar": "عقدة جديدة"}],
            redistribution={"e1": "new_node"}, reasoning="Because reasons",
            confidence="likely", model="test", cost={"total_cost": 0.01,
            "input_tokens": 100, "output_tokens": 50},
        )
        taxonomy_map = _make_taxonomy_map()
        md = generate_review_md(
            [signal], [proposal], "imlaa", "imlaa_v1_0", taxonomy_map, "test",
        )

        assert "EP-001" in md
        assert "NODE_ADDED" in md
        assert "new_node" in md
        assert "عقدة جديدة" in md
        assert "Because reasons" in md


# ---------------------------------------------------------------------------
# Tests: Proposal JSON
# ---------------------------------------------------------------------------

class TestProposalJSON:

    def test_schema_version_present(self):
        result = generate_proposal_json([], [], "imlaa", "v1_0", "path.yaml", "model")
        assert result["schema_version"] == "evolution_proposal_v0.1"

    def test_summary_counts(self):
        signal = EvolutionSignal(
            signal_type="unmapped", node_id="_unmapped", science="imlaa",
            excerpt_ids=["e1"], excerpt_texts=["t"],
            excerpt_metadata=[{}], context="",
        )
        proposal = EvolutionProposal(
            signal=signal, proposal_id="EP-001",
            change_type="node_added", parent_node_id="p",
            new_nodes=[{"node_id": "n"}], redistribution={},
            reasoning="r", confidence="likely",
            model="m", cost={"input_tokens": 100, "output_tokens": 50, "total_cost": 0.01},
        )

        result = generate_proposal_json(
            [signal, signal], [proposal], "imlaa", "v1_0", "path", "model",
        )

        assert result["summary"]["total_signals"] == 2
        assert result["summary"]["total_proposals"] == 1
        assert result["summary"]["no_change_needed"] == 1


# ---------------------------------------------------------------------------
# Tests: Dry Run
# ---------------------------------------------------------------------------

class TestDryRun:

    def test_dry_run_no_llm_calls(self, tmp_path):
        """Dry run should not call LLM."""
        # Write extraction file
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()
        extraction = {
            "atoms": [{"atom_id": "a1", "type": "prose_sentence", "text": "نص"}],
            "excerpts": [{
                "excerpt_id": "q:exc:001",
                "taxonomy_node_id": "_unmapped",
                "taxonomy_path": "",
                "core_atoms": ["a1"],
                "context_atoms": [],
            }],
            "footnote_excerpts": [],
        }
        (ext_dir / "P001_extraction.json").write_text(
            json.dumps(extraction, ensure_ascii=False), encoding="utf-8",
        )

        # Write taxonomy
        tax_path = tmp_path / "tax.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        out_dir = tmp_path / "output"

        llm_called = False

        def fail_llm(*args, **kwargs):
            nonlocal llm_called
            llm_called = True
            raise RuntimeError("LLM should not be called in dry run")

        result = run_evolution(
            extraction_dir=str(ext_dir),
            taxonomy_path=str(tax_path),
            science="imlaa",
            output_dir=str(out_dir),
            dry_run=True,
            call_llm_fn=fail_llm,
        )

        assert not llm_called
        assert result.get("dry_run") is True
        assert result["signals"] == 1

        # Check that dry run report was written
        report = out_dir / "evolution_signals_dry_run.json"
        assert report.exists()
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["mode"] == "dry_run"
        assert len(data["signals"]) == 1

    def test_dry_run_writes_signals_only(self, tmp_path):
        """Dry run should not produce proposals or change records."""
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()
        extraction = {
            "atoms": [{"atom_id": "a1", "type": "prose_sentence", "text": "text"}],
            "excerpts": [{
                "excerpt_id": "q:exc:001",
                "taxonomy_node_id": "_unmapped",
                "taxonomy_path": "",
                "core_atoms": ["a1"],
                "context_atoms": [],
            }],
            "footnote_excerpts": [],
        }
        (ext_dir / "P001_extraction.json").write_text(
            json.dumps(extraction, ensure_ascii=False), encoding="utf-8",
        )

        tax_path = tmp_path / "tax.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        out_dir = tmp_path / "output"

        run_evolution(
            extraction_dir=str(ext_dir),
            taxonomy_path=str(tax_path),
            science="imlaa",
            output_dir=str(out_dir),
            dry_run=True,
        )

        # Should NOT produce these files
        assert not (out_dir / "evolution_proposal.json").exists()
        assert not (out_dir / "taxonomy_changes.jsonl").exists()
        assert not (out_dir / "evolution_review.md").exists()


# ---------------------------------------------------------------------------
# Tests: Integration
# ---------------------------------------------------------------------------

class TestIntegration:

    def test_full_pipeline_with_mock_llm(self, tmp_path):
        """Full pipeline: signals → proposals → artifacts."""
        # Write extraction data with an unmapped excerpt and a cluster
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()

        extraction = {
            "atoms": [
                {"atom_id": "a1", "type": "prose_sentence", "text": "نص غير مصنف"},
                {"atom_id": "a2", "type": "prose_sentence", "text": "نص أول عن الهمزة"},
                {"atom_id": "a3", "type": "prose_sentence", "text": "نص ثاني عن الهمزة"},
            ],
            "excerpts": [
                {
                    "excerpt_id": "q:exc:001",
                    "excerpt_title": "اقتباس غير مصنف",
                    "taxonomy_node_id": "_unmapped",
                    "taxonomy_path": "",
                    "core_atoms": ["a1"],
                    "context_atoms": [],
                    "boundary_reasoning": "No fitting leaf",
                },
                {
                    "excerpt_id": "q:exc:002",
                    "excerpt_title": "تعريف الهمزة — 1",
                    "taxonomy_node_id": "ta3rif_alhamza",
                    "taxonomy_path": "imlaa > alhamza > ta3rif_alhamza",
                    "core_atoms": ["a2"],
                    "context_atoms": [],
                },
                {
                    "excerpt_id": "q:exc:003",
                    "excerpt_title": "تعريف الهمزة — 2",
                    "taxonomy_node_id": "ta3rif_alhamza",
                    "taxonomy_path": "imlaa > alhamza > ta3rif_alhamza",
                    "core_atoms": ["a3"],
                    "context_atoms": [],
                },
            ],
            "footnote_excerpts": [],
        }
        (ext_dir / "P001_extraction.json").write_text(
            json.dumps(extraction, ensure_ascii=False), encoding="utf-8",
        )

        # Write taxonomy
        tax_path = tmp_path / "imlaa_v1_0.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        out_dir = tmp_path / "output"

        call_count = 0

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            nonlocal call_count
            call_count += 1

            if "unmapped" in system.lower() or "_unmapped" in user:
                return {
                    "parsed": {
                        "action": "new_node",
                        "existing_leaf_id": None,
                        "new_node": {
                            "node_id": "hamza_special",
                            "title_ar": "حالة خاصة",
                            "parent_node_id": "alhamza",
                            "leaf": True,
                        },
                        "reasoning": "New case for hamza",
                        "confidence": "likely",
                    },
                    "input_tokens": 500,
                    "output_tokens": 100,
                    "stop_reason": "end_turn",
                }
            else:
                return {
                    "parsed": {
                        "action": "keep",
                        "new_nodes": [],
                        "redistribution": {},
                        "reasoning": "Same topic, no split needed",
                        "confidence": "certain",
                    },
                    "input_tokens": 600,
                    "output_tokens": 80,
                    "stop_reason": "end_turn",
                }

        result = run_evolution(
            extraction_dir=str(ext_dir),
            taxonomy_path=str(tax_path),
            science="imlaa",
            output_dir=str(out_dir),
            model="test-model",
            api_key="test-key",
            book_id="qimlaa",
            call_llm_fn=mock_llm,
        )

        # Verify LLM was called (2 signals: 1 unmapped + 1 cluster)
        assert call_count == 2

        # Verify output artifacts
        assert (out_dir / "evolution_proposal.json").exists()
        assert (out_dir / "taxonomy_changes.jsonl").exists()
        assert (out_dir / "evolution_review.md").exists()

        # Verify proposal JSON content
        proposal_data = json.loads(
            (out_dir / "evolution_proposal.json").read_text(encoding="utf-8"),
        )
        assert proposal_data["schema_version"] == "evolution_proposal_v0.1"
        assert proposal_data["summary"]["total_signals"] == 2
        assert proposal_data["summary"]["total_proposals"] == 1  # cluster kept as-is
        assert proposal_data["summary"]["no_change_needed"] == 1

        # Verify change records
        changes_text = (out_dir / "taxonomy_changes.jsonl").read_text(encoding="utf-8")
        records = [json.loads(line) for line in changes_text.strip().split("\n")]
        assert len(records) == 1
        assert records[0]["change_type"] == "node_added"
        assert records[0]["node_id"] == "hamza_special"

        # Verify review markdown
        review_text = (out_dir / "evolution_review.md").read_text(encoding="utf-8")
        assert "Taxonomy Evolution Review" in review_text
        assert "hamza_special" in review_text

    def test_no_signals_graceful(self, tmp_path):
        """No extraction data → no signals → graceful exit."""
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()

        # Write clean extraction data (all excerpts properly placed)
        extraction = {
            "atoms": [{"atom_id": "a1", "type": "prose_sentence", "text": "text"}],
            "excerpts": [{
                "excerpt_id": "q:exc:001",
                "taxonomy_node_id": "ta3rif_alhamza",
                "taxonomy_path": "path",
                "core_atoms": ["a1"],
                "context_atoms": [],
            }],
            "footnote_excerpts": [],
        }
        (ext_dir / "P001_extraction.json").write_text(
            json.dumps(extraction, ensure_ascii=False), encoding="utf-8",
        )

        tax_path = tmp_path / "tax.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        out_dir = tmp_path / "output"

        result = run_evolution(
            extraction_dir=str(ext_dir),
            taxonomy_path=str(tax_path),
            science="imlaa",
            output_dir=str(out_dir),
        )

        assert result["signals"] == 0
        assert result["proposals"] == 0

    def test_empty_extraction_dir(self, tmp_path):
        """Empty extraction directory → no signals."""
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()

        tax_path = tmp_path / "tax.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        out_dir = tmp_path / "output"

        result = run_evolution(
            extraction_dir=str(ext_dir),
            taxonomy_path=str(tax_path),
            science="imlaa",
            output_dir=str(out_dir),
        )

        assert result["signals"] == 0


# ---------------------------------------------------------------------------
# Tests: Apply Step (Phase B stub)
# ---------------------------------------------------------------------------

class TestApplyStub:

    def test_apply_raises_not_implemented(self):
        from tools.evolve_taxonomy import apply_evolution
        with pytest.raises(NotImplementedError, match="Phase B"):
            apply_evolution("proposal.json", "tax.yaml", None, "out")
