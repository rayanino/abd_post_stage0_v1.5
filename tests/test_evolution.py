"""Tests for tools/evolve_taxonomy.py — Taxonomy Evolution Engine (Phase A + B)."""

import json
from pathlib import Path

import pytest

from tools.evolve_taxonomy import (
    EvolutionProposal,
    EvolutionSignal,
    _compare_evolution_proposals,
    deduplicate_signals,
    extract_taxonomy_section,
    generate_change_records,
    generate_proposal_json,
    generate_review_md,
    propose_evolution_for_signal,
    propose_with_consensus,
    resolve_excerpt_full_text,
    run_evolution,
    scan_category_leaf_signals,
    scan_cluster_signals,
    scan_multi_topic_signals,
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

    def test_dedup_preserves_unmapped_as_separate(self):
        """Each unmapped signal should remain separate (each may be about a different topic)."""
        sig1 = EvolutionSignal(
            signal_type="unmapped", node_id="_unmapped", science="imlaa",
            excerpt_ids=["e1"], excerpt_texts=["topic A text"],
            excerpt_metadata=[{}], context="unmapped 1",
        )
        sig2 = EvolutionSignal(
            signal_type="unmapped", node_id="_unmapped", science="imlaa",
            excerpt_ids=["e2"], excerpt_texts=["topic B text"],
            excerpt_metadata=[{}], context="unmapped 2",
        )

        result = deduplicate_signals([sig1, sig2])
        # Must NOT merge — each unmapped excerpt needs its own LLM evaluation
        assert len(result) == 2
        ids = [r.excerpt_ids[0] for r in result]
        assert "e1" in ids
        assert "e2" in ids


class TestBookIdDerivation:
    """Verify that scan_cluster_signals derives book_id from atom_id prefix."""

    def test_cluster_detects_same_book_via_atom_id_prefix(self):
        """Excerpts with atom_ids sharing a book prefix should be grouped together."""
        atoms = [
            _make_atom("qimlaa:matn:001", "نص أول"),
            _make_atom("qimlaa:matn:002", "نص ثاني"),
        ]
        # Use atom_id dicts in core_atoms (matching extraction output format)
        excerpts = [
            {
                "excerpt_id": "qimlaa:exc:001",
                "excerpt_title": "Test 1",
                "taxonomy_node_id": "ta3rif_alhamza",
                "taxonomy_path": "path > to > ta3rif_alhamza",
                "core_atoms": [{"atom_id": "qimlaa:matn:001", "role": "author_prose"}],
                "context_atoms": [],
                "boundary_reasoning": "test",
            },
            {
                "excerpt_id": "qimlaa:exc:002",
                "excerpt_title": "Test 2",
                "taxonomy_node_id": "ta3rif_alhamza",
                "taxonomy_path": "path > to > ta3rif_alhamza",
                "core_atoms": [{"atom_id": "qimlaa:matn:002", "role": "author_prose"}],
                "context_atoms": [],
                "boundary_reasoning": "test",
            },
        ]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}
        taxonomy_map = _make_taxonomy_map()

        signals = scan_cluster_signals(
            [passage], atoms_indexes, taxonomy_map, "imlaa",
        )
        assert len(signals) == 1
        assert signals[0].signal_type == "same_book_cluster"

    def test_different_books_no_cluster_signal(self):
        """Excerpts from different books (different atom_id prefix) should NOT cluster."""
        atoms = [
            _make_atom("qimlaa:matn:001", "نص من كتاب أ"),
            _make_atom("shadha:matn:001", "نص من كتاب ب"),
        ]
        excerpts = [
            {
                "excerpt_id": "qimlaa:exc:001",
                "excerpt_title": "From book A",
                "taxonomy_node_id": "ta3rif_alhamza",
                "taxonomy_path": "path",
                "core_atoms": [{"atom_id": "qimlaa:matn:001", "role": "author_prose"}],
                "context_atoms": [],
                "boundary_reasoning": "test",
            },
            {
                "excerpt_id": "shadha:exc:001",
                "excerpt_title": "From book B",
                "taxonomy_node_id": "ta3rif_alhamza",
                "taxonomy_path": "path",
                "core_atoms": [{"atom_id": "shadha:matn:001", "role": "author_prose"}],
                "context_atoms": [],
                "boundary_reasoning": "test",
            },
        ]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}
        taxonomy_map = _make_taxonomy_map()

        signals = scan_cluster_signals(
            [passage], atoms_indexes, taxonomy_map, "imlaa",
        )
        # Different books at the same node is normal — should NOT trigger signal
        assert len(signals) == 0


class TestVersionIncrement:
    """Verify generate_change_records uses _increment_version consistently."""

    def test_change_records_version_matches_increment(self):
        from tools.evolve_taxonomy import _increment_version
        proposal = EvolutionProposal(
            signal=EvolutionSignal(
                signal_type="same_book_cluster",
                node_id="ta3rif_alhamza",
                science="imlaa",
                excerpt_ids=["e1"],
                excerpt_texts=["text"],
                excerpt_metadata=[{}],
                context="test",
            ),
            proposal_id="EP-001",
            change_type="leaf_granulated",
            new_nodes=[{"node_id": "sub1", "title": "Sub 1"}],
            parent_node_id="ta3rif_alhamza",
            redistribution={"e1": "sub1"},
            reasoning="Split for finer granularity",
            model="test-model",
            confidence="high",
            cost={"input_tokens": 0, "output_tokens": 0, "total_cost": 0},
        )
        records = generate_change_records(
            [proposal], "imlaa_v1_0", "qimlaa",
        )
        # Version in change records should match _increment_version output
        expected = _increment_version("imlaa_v1_0")
        assert records[0]["taxonomy_version_after"] == expected


# ---------------------------------------------------------------------------
# Tests: Category Leaf Signals (RC3)
# ---------------------------------------------------------------------------

class TestCategoryLeafSignals:
    """Tests for scan_category_leaf_signals — detecting leaf nodes with category names."""

    def _make_taxonomy_with_category_leaf(self, node_id, label):
        """Create a taxonomy map with one branch and one leaf (the test leaf)."""
        return {
            "root": TaxonomyNodeInfo(
                node_id="root", title="جذر",
                path_ids=["root"], path_titles=["جذر"],
                is_leaf=False, folder_path="root",
            ),
            node_id: TaxonomyNodeInfo(
                node_id=node_id, title=label,
                path_ids=["root", node_id], path_titles=["جذر", label],
                is_leaf=True, folder_path=f"root/{node_id}",
            ),
        }

    def test_detects_arabic_category_keyword_sifat(self):
        tax = self._make_taxonomy_with_category_leaf(
            "sifat_dhatiyyah", "الصفات الذاتية"
        )
        signals = scan_category_leaf_signals(tax, "aqidah")
        assert len(signals) == 1
        assert signals[0].signal_type == "category_leaf"
        assert signals[0].node_id == "sifat_dhatiyyah"
        assert "صفات" in signals[0].context

    def test_detects_arabic_category_keyword_maratib(self):
        tax = self._make_taxonomy_with_category_leaf(
            "maratib_al_qadr", "مراتب القدر"
        )
        signals = scan_category_leaf_signals(tax, "aqidah")
        assert len(signals) == 1
        assert signals[0].signal_type == "category_leaf"
        assert "مراتب" in signals[0].context

    def test_detects_latin_id_keyword(self):
        # Node has a plain label but the ID contains 'maratib'
        tax = self._make_taxonomy_with_category_leaf(
            "maratib_al_qadr", "القدر"  # label doesn't have keywords
        )
        signals = scan_category_leaf_signals(tax, "aqidah")
        assert len(signals) == 1
        assert signals[0].node_id == "maratib_al_qadr"

    def test_no_signal_for_normal_leaf(self):
        tax = self._make_taxonomy_with_category_leaf(
            "ta3rif_alhamza", "تعريف الهمزة"
        )
        signals = scan_category_leaf_signals(tax, "imlaa")
        assert len(signals) == 0

    def test_no_signal_for_branch_node(self):
        """Branch nodes (non-leaf) should not trigger signals even with category names."""
        tax = {
            "sifat_dhatiyyah": TaxonomyNodeInfo(
                node_id="sifat_dhatiyyah", title="الصفات الذاتية",
                path_ids=["root", "sifat_dhatiyyah"],
                path_titles=["جذر", "الصفات الذاتية"],
                is_leaf=False, folder_path="root/sifat_dhatiyyah",
            ),
        }
        signals = scan_category_leaf_signals(tax, "aqidah")
        assert len(signals) == 0

    def test_detects_multiple_category_leaves(self):
        tax = {
            "root": TaxonomyNodeInfo(
                node_id="root", title="جذر",
                path_ids=["root"], path_titles=["جذر"],
                is_leaf=False, folder_path="root",
            ),
            "sifat_dhatiyyah": TaxonomyNodeInfo(
                node_id="sifat_dhatiyyah", title="الصفات الذاتية",
                path_ids=["root", "sifat_dhatiyyah"],
                path_titles=["جذر", "الصفات الذاتية"],
                is_leaf=True, folder_path="root/sifat_dhatiyyah",
            ),
            "maratib_al_qadr": TaxonomyNodeInfo(
                node_id="maratib_al_qadr", title="مراتب القدر",
                path_ids=["root", "maratib_al_qadr"],
                path_titles=["جذر", "مراتب القدر"],
                is_leaf=True, folder_path="root/maratib_al_qadr",
            ),
        }
        signals = scan_category_leaf_signals(tax, "aqidah")
        assert len(signals) == 2
        node_ids = {s.node_id for s in signals}
        assert node_ids == {"sifat_dhatiyyah", "maratib_al_qadr"}

    def test_category_signals_have_no_excerpts(self):
        """Category signals are name-based, not excerpt-based."""
        tax = self._make_taxonomy_with_category_leaf(
            "ahkam_al_salah", "أحكام الصلاة"
        )
        signals = scan_category_leaf_signals(tax, "fiqh")
        assert len(signals) == 1
        assert signals[0].excerpt_ids == []
        assert signals[0].excerpt_texts == []


# ---------------------------------------------------------------------------
# Tests: Multi-Topic Excerpt Signals (RC4)
# ---------------------------------------------------------------------------

class TestMultiTopicSignals:
    """Tests for scan_multi_topic_signals — detecting solo large excerpts."""

    def test_detects_large_solo_excerpt(self):
        atoms = [
            _make_atom("a1", "نص ١"),
            _make_atom("a2", "نص ٢"),
            _make_atom("a3", "نص ٣"),
            _make_atom("a4", "نص ٤"),
            _make_atom("a5", "نص ٥"),
        ]
        excerpts = [
            _make_excerpt("q:exc:001", "sifat_fi3liyyah",
                          ["a1", "a2", "a3", "a4", "a5"]),
        ]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}
        taxonomy_map = {
            "sifat_fi3liyyah": TaxonomyNodeInfo(
                node_id="sifat_fi3liyyah", title="الصفات الفعلية",
                path_ids=["aqidah", "sifat_fi3liyyah"],
                path_titles=["عقيدة", "الصفات الفعلية"],
                is_leaf=True, folder_path="aqidah/sifat_fi3liyyah",
            ),
        }

        signals = scan_multi_topic_signals(
            [passage], atoms_indexes, taxonomy_map, "aqidah",
        )

        assert len(signals) == 1
        assert signals[0].signal_type == "multi_topic_excerpt"
        assert signals[0].node_id == "sifat_fi3liyyah"
        assert signals[0].excerpt_ids == ["q:exc:001"]
        assert "5 atoms" in signals[0].context

    def test_no_signal_for_small_excerpt(self):
        """Excerpts with fewer than min_atoms should not trigger."""
        atoms = [
            _make_atom("a1", "نص ١"),
            _make_atom("a2", "نص ٢"),
        ]
        excerpts = [
            _make_excerpt("q:exc:001", "some_leaf", ["a1", "a2"]),
        ]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}
        taxonomy_map = {
            "some_leaf": TaxonomyNodeInfo(
                node_id="some_leaf", title="ورقة",
                path_ids=["root", "some_leaf"],
                path_titles=["جذر", "ورقة"],
                is_leaf=True, folder_path="root/some_leaf",
            ),
        }

        signals = scan_multi_topic_signals(
            [passage], atoms_indexes, taxonomy_map, "aqidah",
        )
        assert len(signals) == 0

    def test_no_signal_when_multiple_excerpts_at_node(self):
        """If node has 2+ excerpts, don't flag — that's a cluster signal's job."""
        atoms = [
            _make_atom("a1", "نص ١"),
            _make_atom("a2", "نص ٢"),
            _make_atom("a3", "نص ٣"),
            _make_atom("a4", "نص ٤"),
            _make_atom("a5", "نص ٥"),
        ]
        excerpts = [
            _make_excerpt("q:exc:001", "some_leaf", ["a1", "a2", "a3"]),
            _make_excerpt("q:exc:002", "some_leaf", ["a4", "a5"]),
        ]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}
        taxonomy_map = {
            "some_leaf": TaxonomyNodeInfo(
                node_id="some_leaf", title="ورقة",
                path_ids=["root", "some_leaf"],
                path_titles=["جذر", "ورقة"],
                is_leaf=True, folder_path="root/some_leaf",
            ),
        }

        signals = scan_multi_topic_signals(
            [passage], atoms_indexes, taxonomy_map, "aqidah",
        )
        assert len(signals) == 0

    def test_ignores_footnote_excerpts(self):
        """Footnote excerpts at a node should not be counted as matn excerpts."""
        atoms = [
            _make_atom("a1", "نص ١"),
            _make_atom("a2", "نص ٢"),
            _make_atom("a3", "نص ٣"),
            _make_atom("a4", "نص ٤"),
        ]
        # One matn excerpt with 4 atoms + a footnote at same node
        matn_exc = _make_excerpt("q:exc:001", "some_leaf", ["a1", "a2", "a3", "a4"])
        fn_exc = _make_excerpt("q:exc:fn:001", "some_leaf", ["a1"])
        fn_exc["source_layer"] = "footnote"
        passage = _make_passage("P001", atoms, [matn_exc, fn_exc])
        atoms_indexes = {"P001": build_atoms_index(atoms)}
        taxonomy_map = {
            "some_leaf": TaxonomyNodeInfo(
                node_id="some_leaf", title="ورقة",
                path_ids=["root", "some_leaf"],
                path_titles=["جذر", "ورقة"],
                is_leaf=True, folder_path="root/some_leaf",
            ),
        }

        signals = scan_multi_topic_signals(
            [passage], atoms_indexes, taxonomy_map, "aqidah",
        )
        # Should still detect — only 1 matn excerpt (the footnote doesn't count)
        assert len(signals) == 1

    def test_custom_min_atoms_threshold(self):
        """Custom min_atoms parameter adjusts sensitivity."""
        atoms = [_make_atom(f"a{i}", f"نص {i}") for i in range(1, 8)]
        excerpts = [
            _make_excerpt("q:exc:001", "some_leaf",
                          [f"a{i}" for i in range(1, 8)]),
        ]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}
        taxonomy_map = {
            "some_leaf": TaxonomyNodeInfo(
                node_id="some_leaf", title="ورقة",
                path_ids=["root", "some_leaf"],
                path_titles=["جذر", "ورقة"],
                is_leaf=True, folder_path="root/some_leaf",
            ),
        }

        # With default min_atoms=4, should trigger
        signals = scan_multi_topic_signals(
            [passage], atoms_indexes, taxonomy_map, "aqidah",
        )
        assert len(signals) == 1

        # With min_atoms=10, should NOT trigger
        signals = scan_multi_topic_signals(
            [passage], atoms_indexes, taxonomy_map, "aqidah",
            min_atoms=10,
        )
        assert len(signals) == 0

    def test_ignores_unmapped_excerpts(self):
        """Excerpts at _unmapped should not trigger multi-topic signal."""
        atoms = [_make_atom(f"a{i}", f"text {i}") for i in range(1, 6)]
        excerpts = [
            _make_excerpt("q:exc:001", "_unmapped",
                          [f"a{i}" for i in range(1, 6)]),
        ]
        passage = _make_passage("P001", atoms, excerpts)
        atoms_indexes = {"P001": build_atoms_index(atoms)}

        signals = scan_multi_topic_signals(
            [passage], atoms_indexes, {}, "aqidah",
        )
        assert len(signals) == 0


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
# Tests: Phase B — Apply, Version Control, Rollback, Redistribution
# ---------------------------------------------------------------------------

class TestApplyProposalToYaml:
    """Tests for apply_proposal_to_yaml — structural changes to taxonomy YAML."""

    def test_leaf_granulated_v1(self, tmp_path):
        """Granulate a v1 leaf into sub-leaves."""
        from tools.evolve_taxonomy import apply_proposal_to_yaml
        import yaml

        tax_path = tmp_path / "imlaa_v1_0.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        proposals = [{
            "change_type": "leaf_granulated",
            "parent_node_id": "ta3rif_alhamza",
            "new_nodes": [
                {"node_id": "ta3rif_alhamza_lugha", "title_ar": "تعريف الهمزة لغة"},
                {"node_id": "ta3rif_alhamza_istilah", "title_ar": "تعريف الهمزة اصطلاحا"},
            ],
        }]

        out_dir = str(tmp_path / "output")
        new_path = apply_proposal_to_yaml(
            str(tax_path), proposals, "imlaa_v1_1", out_dir,
        )

        assert Path(new_path).exists()
        with open(new_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Verify the target node now has children
        nodes = data["taxonomy"]["nodes"]
        alhamza = nodes[0]
        assert alhamza["id"] == "alhamza"

        ta3rif = None
        for child in alhamza["children"]:
            if child["id"] == "ta3rif_alhamza":
                ta3rif = child
                break

        assert ta3rif is not None
        assert "leaf" not in ta3rif  # No longer a leaf
        assert "children" in ta3rif
        assert len(ta3rif["children"]) == 2
        assert ta3rif["children"][0]["id"] == "ta3rif_alhamza_lugha"
        assert ta3rif["children"][1]["leaf"] is True

        # Original file unchanged
        with open(tax_path, encoding="utf-8") as f:
            original = yaml.safe_load(f)
        orig_ta3rif = original["taxonomy"]["nodes"][0]["children"][0]
        assert orig_ta3rif.get("leaf") is True  # Still a leaf in original

    def test_leaf_granulated_v0(self, tmp_path):
        """Granulate a v0 leaf into sub-leaves."""
        from tools.evolve_taxonomy import apply_proposal_to_yaml
        import yaml

        tax_path = tmp_path / "imlaa_v0.yaml"
        tax_path.write_text(SAMPLE_V0_YAML, encoding="utf-8")

        proposals = [{
            "change_type": "leaf_granulated",
            "parent_node_id": "ta3rif_alhamza",
            "new_nodes": [
                {"node_id": "ta3rif_lugha", "title_ar": "تعريف لغة"},
                {"node_id": "ta3rif_istilah", "title_ar": "تعريف اصطلاحا"},
            ],
        }]

        out_dir = str(tmp_path / "output")
        new_path = apply_proposal_to_yaml(
            str(tax_path), proposals, "imlaa_v0_2", out_dir,
        )

        with open(new_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        ta3rif = data["imlaa"]["alhamza"]["ta3rif_alhamza"]
        assert "_leaf" not in ta3rif  # No longer a leaf
        assert "ta3rif_lugha" in ta3rif
        assert ta3rif["ta3rif_lugha"]["_leaf"] is True

    def test_node_added_v1(self, tmp_path):
        """Add a new leaf node under an existing branch in v1."""
        from tools.evolve_taxonomy import apply_proposal_to_yaml
        import yaml

        tax_path = tmp_path / "imlaa_v1_0.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        proposals = [{
            "change_type": "node_added",
            "parent_node_id": "alhamza",
            "new_nodes": [
                {"node_id": "hamza_special_case", "title_ar": "حالة خاصة للهمزة"},
            ],
        }]

        out_dir = str(tmp_path / "output")
        new_path = apply_proposal_to_yaml(
            str(tax_path), proposals, "imlaa_v1_1", out_dir,
        )

        with open(new_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        children = data["taxonomy"]["nodes"][0]["children"]
        child_ids = [c["id"] for c in children]
        assert "hamza_special_case" in child_ids

    def test_multiple_proposals(self, tmp_path):
        """Apply multiple proposals in sequence."""
        from tools.evolve_taxonomy import apply_proposal_to_yaml
        import yaml

        tax_path = tmp_path / "imlaa_v1_0.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        proposals = [
            {
                "change_type": "node_added",
                "parent_node_id": "alhamza",
                "new_nodes": [
                    {"node_id": "new_node_1", "title_ar": "عقدة جديدة 1"},
                ],
            },
            {
                "change_type": "leaf_granulated",
                "parent_node_id": "hamzat_alwasl",
                "new_nodes": [
                    {"node_id": "wasl_sub1", "title_ar": "فرع 1"},
                    {"node_id": "wasl_sub2", "title_ar": "فرع 2"},
                ],
            },
        ]

        out_dir = str(tmp_path / "output")
        new_path = apply_proposal_to_yaml(
            str(tax_path), proposals, "imlaa_v1_1", out_dir,
        )

        with open(new_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        children = data["taxonomy"]["nodes"][0]["children"]
        child_ids = [c["id"] for c in children]
        assert "new_node_1" in child_ids

        wasl = next(c for c in children if c["id"] == "hamzat_alwasl")
        assert "children" in wasl
        assert len(wasl["children"]) == 2

    def test_empty_proposals_noop(self, tmp_path):
        """Empty proposals list leaves taxonomy unchanged."""
        from tools.evolve_taxonomy import apply_proposal_to_yaml
        import yaml

        tax_path = tmp_path / "imlaa_v1_0.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        out_dir = str(tmp_path / "output")
        new_path = apply_proposal_to_yaml(
            str(tax_path), [], "imlaa_v1_1", out_dir,
        )

        with open(new_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Structure should be identical to original
        with open(tax_path, encoding="utf-8") as f:
            original = yaml.safe_load(f)

        assert len(data["taxonomy"]["nodes"]) == len(original["taxonomy"]["nodes"])


class TestIncrementVersion:
    """Tests for _increment_version."""

    def test_standard_version(self):
        from tools.evolve_taxonomy import _increment_version
        assert _increment_version("imlaa_v1_0") == "imlaa_v1_1"

    def test_higher_number(self):
        from tools.evolve_taxonomy import _increment_version
        assert _increment_version("aqidah_v0_2") == "aqidah_v0_3"

    def test_non_standard(self):
        from tools.evolve_taxonomy import _increment_version
        assert _increment_version("custom_version") == "custom_version_1"


class TestUpdateTaxonomyRegistry:
    """Tests for update_taxonomy_registry."""

    def test_adds_new_version(self, tmp_path):
        from tools.evolve_taxonomy import update_taxonomy_registry
        import yaml

        registry_path = tmp_path / "registry.yaml"
        registry_path.write_text(
            "registry_version: '0.1'\n"
            "sciences:\n"
            "- science_id: imlaa\n"
            "  display_name_ar: الإملاء\n"
            "  versions:\n"
            "  - taxonomy_version: imlaa_v1_0\n"
            "    relpath: taxonomy/imlaa/imlaa_v1_0.yaml\n"
            "    status: active\n",
            encoding="utf-8",
        )

        update_taxonomy_registry(
            str(registry_path), "imlaa", "imlaa_v1_1",
            "taxonomy/imlaa/imlaa_v1_1.yaml", "imlaa_v1_0",
        )

        with open(registry_path, encoding="utf-8") as f:
            reg = yaml.safe_load(f)

        versions = reg["sciences"][0]["versions"]
        assert len(versions) == 2
        # Old version marked historical
        assert versions[0]["status"] == "historical"
        # New version is active
        assert versions[1]["taxonomy_version"] == "imlaa_v1_1"
        assert versions[1]["status"] == "active"

    def test_creates_new_science_entry(self, tmp_path):
        from tools.evolve_taxonomy import update_taxonomy_registry
        import yaml

        registry_path = tmp_path / "registry.yaml"
        registry_path.write_text(
            "registry_version: '0.1'\nsciences: []\n",
            encoding="utf-8",
        )

        update_taxonomy_registry(
            str(registry_path), "fiqh", "fiqh_v0_1",
            "taxonomy/fiqh/fiqh_v0_1.yaml", "",
        )

        with open(registry_path, encoding="utf-8") as f:
            reg = yaml.safe_load(f)

        assert len(reg["sciences"]) == 1
        assert reg["sciences"][0]["science_id"] == "fiqh"
        assert reg["sciences"][0]["versions"][0]["taxonomy_version"] == "fiqh_v0_1"


class TestRedistributeExcerpts:
    """Tests for redistribute_excerpts with mock LLM."""

    def test_redistributes_with_mock_llm(self, tmp_path):
        from tools.evolve_taxonomy import redistribute_excerpts
        import yaml

        # Set up taxonomy
        tax_path = tmp_path / "tax.yaml"
        tax_yaml = (
            "taxonomy:\n"
            "  id: test_v1\n"
            "  title: Test\n"
            "  nodes:\n"
            "  - id: parent_node\n"
            "    title: Parent\n"
            "    children:\n"
            "    - id: sub_a\n"
            "      title: Sub A\n"
            "      leaf: true\n"
            "    - id: sub_b\n"
            "      title: Sub B\n"
            "      leaf: true\n"
        )
        tax_path.write_text(tax_yaml, encoding="utf-8")

        # Set up assembled excerpts at old node
        assembly_dir = tmp_path / "assembled"
        old_folder = assembly_dir / "test" / "parent_node"
        old_folder.mkdir(parents=True)

        exc1 = {"excerpt_title": "Excerpt 1", "arabic_text": "نص أول", "excerpt_id": "e1"}
        exc2 = {"excerpt_title": "Excerpt 2", "arabic_text": "نص ثاني", "excerpt_id": "e2"}
        (old_folder / "e1.json").write_text(
            json.dumps(exc1, ensure_ascii=False), encoding="utf-8",
        )
        (old_folder / "e2.json").write_text(
            json.dumps(exc2, ensure_ascii=False), encoding="utf-8",
        )

        call_count = 0

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            nonlocal call_count
            call_count += 1
            # First excerpt → sub_a, second → sub_b
            if "نص أول" in user:
                return {"parsed": {"node_id": "sub_a", "confidence": "certain"}}
            return {"parsed": {"node_id": "sub_b", "confidence": "certain"}}

        result = redistribute_excerpts(
            assembly_dir=str(assembly_dir),
            old_node_id="parent_node",
            new_nodes=[
                {"node_id": "sub_a", "title_ar": "Sub A"},
                {"node_id": "sub_b", "title_ar": "Sub B"},
            ],
            science="test",
            taxonomy_path=str(tax_path),
            call_llm_fn=mock_llm,
        )

        assert call_count == 2
        assert len(result["moves"]) == 2
        assert len(result["flagged"]) == 0

        # Files should have been moved
        assert not (old_folder / "e1.json").exists()
        assert not (old_folder / "e2.json").exists()

    def test_flags_uncertain_placements(self, tmp_path):
        from tools.evolve_taxonomy import redistribute_excerpts

        tax_path = tmp_path / "tax.yaml"
        tax_yaml = (
            "taxonomy:\n"
            "  id: test_v1\n"
            "  title: Test\n"
            "  nodes:\n"
            "  - id: parent_node\n"
            "    title: Parent\n"
            "    children:\n"
            "    - id: sub_a\n"
            "      title: Sub A\n"
            "      leaf: true\n"
        )
        tax_path.write_text(tax_yaml, encoding="utf-8")

        assembly_dir = tmp_path / "assembled"
        old_folder = assembly_dir / "test" / "parent_node"
        old_folder.mkdir(parents=True)

        exc1 = {"excerpt_title": "Unclear", "arabic_text": "نص غير واضح"}
        (old_folder / "e1.json").write_text(
            json.dumps(exc1, ensure_ascii=False), encoding="utf-8",
        )

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {"parsed": {"node_id": "sub_a", "confidence": "uncertain"}}

        result = redistribute_excerpts(
            assembly_dir=str(assembly_dir),
            old_node_id="parent_node",
            new_nodes=[{"node_id": "sub_a", "title_ar": "Sub A"}],
            science="test",
            taxonomy_path=str(tax_path),
            call_llm_fn=mock_llm,
        )

        assert len(result["flagged"]) == 1  # Uncertain → flagged

    def test_empty_folder_noop(self, tmp_path):
        from tools.evolve_taxonomy import redistribute_excerpts

        tax_path = tmp_path / "tax.yaml"
        tax_path.write_text(
            "taxonomy:\n  id: t\n  title: T\n  nodes:\n"
            "  - id: parent_node\n    title: P\n    leaf: true\n",
            encoding="utf-8",
        )

        assembly_dir = tmp_path / "assembled"
        old_folder = assembly_dir / "test" / "parent_node"
        old_folder.mkdir(parents=True)

        result = redistribute_excerpts(
            assembly_dir=str(assembly_dir),
            old_node_id="parent_node",
            new_nodes=[{"node_id": "sub_a"}],
            science="test",
            taxonomy_path=str(tax_path),
        )

        assert result["moves"] == {}
        assert "No excerpt files" in result.get("note", "")


class TestRollbackEvolution:
    """Tests for rollback_evolution."""

    def test_rollback_reverses_file_moves(self, tmp_path):
        from tools.evolve_taxonomy import rollback_evolution

        # Set up: file was moved from old → new
        old_dir = tmp_path / "old_location"
        new_dir = tmp_path / "new_location"
        old_dir.mkdir()
        new_dir.mkdir()

        # File currently at new location
        (new_dir / "excerpt.json").write_text('{"test": true}', encoding="utf-8")

        manifest = {
            "science": "imlaa",
            "previous_version": "imlaa_v1_0",
            "new_version": "imlaa_v1_1",
            "file_moves": [
                {
                    "from": str(old_dir / "excerpt.json"),
                    "to": str(new_dir / "excerpt.json"),
                },
            ],
        }
        manifest_path = tmp_path / "rollback_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8",
        )

        result = rollback_evolution(str(manifest_path))

        assert result["status"] == "success"
        assert result["reversed_moves"] == 1
        assert (old_dir / "excerpt.json").exists()
        assert not (new_dir / "excerpt.json").exists()

    def test_rollback_deletes_new_taxonomy(self, tmp_path):
        from tools.evolve_taxonomy import rollback_evolution

        new_tax = tmp_path / "imlaa_v1_1.yaml"
        new_tax.write_text("test", encoding="utf-8")

        manifest = {
            "science": "imlaa",
            "previous_version": "imlaa_v1_0",
            "new_version": "imlaa_v1_1",
            "new_taxonomy_path": str(new_tax),
            "file_moves": [],
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest), encoding="utf-8",
        )

        result = rollback_evolution(str(manifest_path))

        assert result["status"] == "success"
        assert not new_tax.exists()

    def test_rollback_restores_registry(self, tmp_path):
        from tools.evolve_taxonomy import rollback_evolution
        import yaml

        # Set up registry with new version active
        registry_path = tmp_path / "registry.yaml"
        registry_path.write_text(
            "registry_version: '0.1'\n"
            "sciences:\n"
            "- science_id: imlaa\n"
            "  versions:\n"
            "  - taxonomy_version: imlaa_v1_0\n"
            "    status: historical\n"
            "    relpath: tax/v1_0.yaml\n"
            "  - taxonomy_version: imlaa_v1_1\n"
            "    status: active\n"
            "    relpath: tax/v1_1.yaml\n",
            encoding="utf-8",
        )

        manifest = {
            "science": "imlaa",
            "previous_version": "imlaa_v1_0",
            "new_version": "imlaa_v1_1",
            "registry_path": str(registry_path),
            "file_moves": [],
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = rollback_evolution(str(manifest_path))

        with open(registry_path, encoding="utf-8") as f:
            reg = yaml.safe_load(f)

        versions = reg["sciences"][0]["versions"]
        # New version should be removed
        version_ids = [v["taxonomy_version"] for v in versions]
        assert "imlaa_v1_1" not in version_ids
        # Old version restored to active
        assert versions[0]["status"] == "active"


class TestApplyEvolutionE2E:
    """End-to-end tests for apply_evolution."""

    def test_full_apply_cycle(self, tmp_path):
        """Full cycle: apply proposals → verify new taxonomy → verify manifest."""
        from tools.evolve_taxonomy import apply_evolution

        # Set up taxonomy
        tax_dir = tmp_path / "taxonomy" / "imlaa"
        tax_dir.mkdir(parents=True)
        tax_path = tax_dir / "imlaa_v1_0.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        # Set up registry
        registry_path = tmp_path / "taxonomy" / "taxonomy_registry.yaml"
        registry_path.write_text(
            "registry_version: '0.1'\n"
            "sciences:\n"
            "- science_id: imlaa\n"
            "  display_name_ar: الإملاء\n"
            "  versions:\n"
            "  - taxonomy_version: imlaa_v1_0\n"
            "    relpath: imlaa/imlaa_v1_0.yaml\n"
            "    status: active\n",
            encoding="utf-8",
        )

        # Create proposal JSON
        proposal = {
            "schema_version": "evolution_proposal_v0.1",
            "science": "imlaa",
            "taxonomy_version": "imlaa_v1_0",
            "proposals": [
                {
                    "change_type": "leaf_granulated",
                    "parent_node_id": "ta3rif_alhamza",
                    "new_nodes": [
                        {"node_id": "ta3rif_lugha", "title_ar": "تعريف لغة"},
                        {"node_id": "ta3rif_istilah", "title_ar": "تعريف اصطلاحا"},
                    ],
                    "redistribution": {},
                },
            ],
        }
        proposal_path = tmp_path / "proposal.json"
        proposal_path.write_text(
            json.dumps(proposal, ensure_ascii=False), encoding="utf-8",
        )

        out_dir = tmp_path / "output"

        result = apply_evolution(
            proposal_path=str(proposal_path),
            taxonomy_path=str(tax_path),
            assembly_dir=None,
            output_dir=str(out_dir),
            registry_path=str(registry_path),
        )

        assert result["status"] == "applied"
        assert result["new_version"] == "imlaa_v1_1"
        assert Path(result["new_taxonomy_path"]).exists()
        assert Path(result["manifest_path"]).exists()

        # Verify rollback manifest
        with open(result["manifest_path"], encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["previous_version"] == "imlaa_v1_0"
        assert manifest["new_version"] == "imlaa_v1_1"

    def test_apply_then_rollback(self, tmp_path):
        """Full cycle: apply → rollback → verify restoration."""
        from tools.evolve_taxonomy import apply_evolution, rollback_evolution
        import yaml

        # Set up taxonomy
        tax_dir = tmp_path / "taxonomy" / "imlaa"
        tax_dir.mkdir(parents=True)
        tax_path = tax_dir / "imlaa_v1_0.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        # Set up registry
        registry_path = tmp_path / "taxonomy" / "taxonomy_registry.yaml"
        registry_path.write_text(
            "registry_version: '0.1'\n"
            "sciences:\n"
            "- science_id: imlaa\n"
            "  display_name_ar: الإملاء\n"
            "  versions:\n"
            "  - taxonomy_version: imlaa_v1_0\n"
            "    relpath: imlaa/imlaa_v1_0.yaml\n"
            "    status: active\n",
            encoding="utf-8",
        )

        # Create proposal
        proposal = {
            "science": "imlaa",
            "taxonomy_version": "imlaa_v1_0",
            "proposals": [{
                "change_type": "node_added",
                "parent_node_id": "alhamza",
                "new_nodes": [{"node_id": "new_leaf", "title_ar": "ورقة جديدة"}],
            }],
        }
        proposal_path = tmp_path / "proposal.json"
        proposal_path.write_text(
            json.dumps(proposal, ensure_ascii=False), encoding="utf-8",
        )

        out_dir = tmp_path / "output"

        # Apply
        result = apply_evolution(
            proposal_path=str(proposal_path),
            taxonomy_path=str(tax_path),
            assembly_dir=None,
            output_dir=str(out_dir),
            registry_path=str(registry_path),
        )

        new_tax_path = result["new_taxonomy_path"]
        assert Path(new_tax_path).exists()

        # Rollback
        rollback_result = rollback_evolution(result["manifest_path"])
        assert rollback_result["status"] == "success"

        # New taxonomy file should be deleted
        assert not Path(new_tax_path).exists()

        # Registry should be restored
        with open(registry_path, encoding="utf-8") as f:
            reg = yaml.safe_load(f)
        versions = reg["sciences"][0]["versions"]
        assert len(versions) == 1
        assert versions[0]["taxonomy_version"] == "imlaa_v1_0"
        assert versions[0]["status"] == "active"

    def test_no_proposals_returns_early(self, tmp_path):
        from tools.evolve_taxonomy import apply_evolution

        proposal = {"science": "imlaa", "taxonomy_version": "v1", "proposals": []}
        proposal_path = tmp_path / "empty.json"
        proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

        tax_path = tmp_path / "tax.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        result = apply_evolution(
            str(proposal_path), str(tax_path), None, str(tmp_path / "out"),
        )
        assert result["status"] == "no_proposals"


# ==========================================================================
# Phase B: Multi-model consensus tests
# ==========================================================================


def _make_signal() -> EvolutionSignal:
    """Create a test signal for consensus tests."""
    return EvolutionSignal(
        signal_type="multi_topic_excerpt",
        node_id="ta3rif_alhamza",
        science="imlaa",
        excerpt_ids=["E001", "E002"],
        excerpt_texts=["text1", "text2"],
        excerpt_metadata=[{"id": "E001"}, {"id": "E002"}],
        context="Test signal",
    )


def _make_proposal(
    model: str,
    node_ids: list[str],
    confidence: str = "likely",
    proposal_id: str = "EP-001",
) -> EvolutionProposal:
    """Create a test proposal with given node IDs."""
    return EvolutionProposal(
        signal=_make_signal(),
        proposal_id=proposal_id,
        change_type="leaf_granulated",
        parent_node_id="ta3rif_alhamza",
        new_nodes=[{"node_id": nid, "title_ar": f"عنوان {nid}"} for nid in node_ids],
        redistribution={"E001": node_ids[0]} if node_ids else {},
        reasoning="Test reasoning",
        confidence=confidence,
        model=model,
        cost={"input_tokens": 100, "output_tokens": 50, "total_cost": 0.001},
    )


class TestCompareEvolutionProposals:
    """Tests for _compare_evolution_proposals."""

    def test_all_none_returns_no_change(self):
        result = _compare_evolution_proposals(
            [None, None], ["model_a", "model_b"],
        )
        assert result["status"] == "no_change"
        assert result["chosen_proposal"] is None
        assert "model_a" in result["model_proposals"]
        assert "model_b" in result["model_proposals"]

    def test_full_agreement_same_nodes(self):
        p1 = _make_proposal("model_a", ["sub_a", "sub_b"], confidence="likely")
        p2 = _make_proposal("model_b", ["sub_a", "sub_b"], confidence="certain")
        result = _compare_evolution_proposals(
            [p1, p2], ["model_a", "model_b"],
        )
        assert result["status"] == "agreement"
        assert set(result["agreed_nodes"]) == {"sub_a", "sub_b"}
        # Should choose model_b (higher confidence)
        assert result["chosen_proposal"].model == "model_b"

    def test_partial_agreement(self):
        p1 = _make_proposal("model_a", ["sub_a", "sub_b"])
        p2 = _make_proposal("model_b", ["sub_a", "sub_c"])
        result = _compare_evolution_proposals(
            [p1, p2], ["model_a", "model_b"],
        )
        assert result["status"] == "partial"
        assert "sub_a" in result["agreed_nodes"]
        assert set(result["disagreed_nodes"]) == {"sub_b", "sub_c"}

    def test_total_disagreement(self):
        p1 = _make_proposal("model_a", ["sub_x"])
        p2 = _make_proposal("model_b", ["sub_y"])
        result = _compare_evolution_proposals(
            [p1, p2], ["model_a", "model_b"],
        )
        assert result["status"] == "disagreement"
        assert result["confidence_override"] == "uncertain"

    def test_one_active_one_none(self):
        p1 = _make_proposal("model_a", ["sub_a"])
        result = _compare_evolution_proposals(
            [p1, None], ["model_a", "model_b"],
        )
        assert result["status"] == "disagreement"
        assert result["confidence_override"] == "uncertain"
        assert result["chosen_proposal"].model == "model_a"

    def test_three_models_agreement(self):
        p1 = _make_proposal("m1", ["x", "y"], confidence="likely")
        p2 = _make_proposal("m2", ["x", "y"], confidence="certain")
        p3 = _make_proposal("m3", ["x", "y"], confidence="uncertain")
        result = _compare_evolution_proposals(
            [p1, p2, p3], ["m1", "m2", "m3"],
        )
        assert result["status"] == "agreement"
        # Should choose m2 (highest confidence)
        assert result["chosen_proposal"].model == "m2"


class TestProposeWithConsensus:
    """Tests for propose_with_consensus using mock LLM."""

    def test_consensus_with_mock_llm(self):
        """Two mock models agree on the same proposal."""
        signal = _make_signal()
        taxonomy_map = _make_taxonomy_map()
        taxonomy_yaml = SAMPLE_V1_YAML

        call_count = {"n": 0}

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            call_count["n"] += 1
            return {
                "parsed": {
                    "action": "split",
                    "new_nodes": [
                        {"node_id": "sub_a", "title_ar": "فرع أ", "leaf": True},
                        {"node_id": "sub_b", "title_ar": "فرع ب", "leaf": True},
                    ],
                    "redistribution": {"E001": "sub_a", "E002": "sub_b"},
                    "confidence": "certain",
                },
                "input_tokens": 100,
                "output_tokens": 50,
                "stop_reason": "end_turn",
            }

        proposal, consensus = propose_with_consensus(
            signal=signal,
            taxonomy_yaml_raw=taxonomy_yaml,
            taxonomy_map=taxonomy_map,
            models=["model_a", "model_b"],
            api_key="test-key",
            call_llm_fn=mock_llm,
        )

        assert call_count["n"] == 2  # Called once per model
        assert consensus["status"] == "agreement"
        assert proposal is not None
        assert proposal.change_type == "leaf_granulated"

    def test_consensus_one_model_no_change(self):
        """One model proposes, other says no change — disagreement."""
        signal = _make_signal()
        taxonomy_map = _make_taxonomy_map()
        taxonomy_yaml = SAMPLE_V1_YAML

        responses = iter([
            # Model A: proposes a change
            {
                "parsed": {
                    "action": "split",
                    "new_nodes": [
                        {"node_id": "sub_a", "title_ar": "فرع أ", "leaf": True},
                    ],
                    "redistribution": {"E001": "sub_a"},
                    "confidence": "likely",
                },
                "input_tokens": 100,
                "output_tokens": 50,
                "stop_reason": "end_turn",
            },
            # Model B: no change
            {
                "parsed": {
                    "action": "keep",
                    "reasoning": "Current taxonomy is adequate",
                },
                "input_tokens": 100,
                "output_tokens": 30,
                "stop_reason": "end_turn",
            },
        ])

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return next(responses)

        proposal, consensus = propose_with_consensus(
            signal=signal,
            taxonomy_yaml_raw=taxonomy_yaml,
            taxonomy_map=taxonomy_map,
            models=["model_a", "model_b"],
            api_key="test-key",
            call_llm_fn=mock_llm,
        )

        assert consensus["status"] == "disagreement"
        # Proposal exists but with lowered confidence
        assert proposal is not None
        assert proposal.confidence == "uncertain"
        assert "[consensus: disagreement]" in proposal.reasoning

    def test_consensus_all_no_change(self):
        """Both models say no change needed."""
        signal = _make_signal()
        taxonomy_map = _make_taxonomy_map()
        taxonomy_yaml = SAMPLE_V1_YAML

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            return {
                "parsed": {
                    "action": "keep",
                    "reasoning": "Adequate",
                },
                "input_tokens": 100,
                "output_tokens": 30,
                "stop_reason": "end_turn",
            }

        proposal, consensus = propose_with_consensus(
            signal=signal,
            taxonomy_yaml_raw=taxonomy_yaml,
            taxonomy_map=taxonomy_map,
            models=["model_a", "model_b"],
            api_key="test-key",
            call_llm_fn=mock_llm,
        )

        assert consensus["status"] == "no_change"
        assert proposal is None


class TestRunEvolutionMultiModel:
    """Tests for run_evolution with multi-model consensus."""

    def test_multi_model_mode(self, tmp_path):
        """run_evolution with models=[m1, m2] uses consensus."""
        # Create extraction data
        atoms = [_make_atom(f"A{i:03d}", f"نص {i}") for i in range(1, 4)]
        excerpts = [
            _make_excerpt("E001", "ta3rif_alhamza", ["A001", "A002"]),
            _make_excerpt("E002", "ta3rif_alhamza", ["A003"]),
        ]
        passage = _make_passage("P001", atoms, excerpts)
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()
        ext_path = ext_dir / "P001_extraction.json"
        ext_path.write_text(
            json.dumps(passage, ensure_ascii=False), encoding="utf-8",
        )

        # Write taxonomy
        tax_path = tmp_path / "imlaa_v1_0.yaml"
        tax_path.write_text(SAMPLE_V1_YAML, encoding="utf-8")

        out_dir = tmp_path / "output"

        call_models = []

        def mock_llm(system, user, model, key, openrouter_key=None, openai_key=None):
            call_models.append(model)
            return {
                "parsed": {
                    "action": "split",
                    "new_nodes": [
                        {"node_id": "sub_a", "title_ar": "فرع أ", "leaf": True},
                    ],
                    "redistribution": {"E001": "sub_a", "E002": "sub_a"},
                    "confidence": "certain",
                },
                "input_tokens": 100,
                "output_tokens": 50,
                "stop_reason": "end_turn",
            }

        result = run_evolution(
            extraction_dir=str(ext_dir),
            taxonomy_path=str(tax_path),
            science="imlaa",
            output_dir=str(out_dir),
            models=["model_a", "model_b"],
            call_llm_fn=mock_llm,
        )

        # Both models should have been called for each signal
        assert "model_a" in call_models
        assert "model_b" in call_models

        # Should have written consensus_results.json
        consensus_file = out_dir / "consensus_results.json"
        assert consensus_file.exists()
        consensus_data = json.loads(consensus_file.read_text(encoding="utf-8"))
        assert len(consensus_data) >= 1
        assert consensus_data[0]["status"] == "agreement"
