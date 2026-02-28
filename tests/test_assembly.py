#!/usr/bin/env python3
"""
Tests for Stage 7 Assembly + Folder Distribution (tools/assemble_excerpts.py)

Run: python -m pytest tests/test_assembly.py -q
"""

import json
import sys
from pathlib import Path

import pytest

# Ensure tools/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from assemble_excerpts import (
    SCHEMA_VERSION,
    TaxonomyNodeInfo,
    assemble_footnote_excerpt,
    assemble_matn_excerpt,
    build_atoms_index,
    derive_filename,
    detect_taxonomy_format,
    distribute_excerpts,
    generate_report_md,
    generate_summary,
    load_extraction_files,
    parse_taxonomy_yaml,
    resolve_atom_texts,
    validate_assembled_excerpt,
    _extract_atom_id,
    _extract_atom_role,
)


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

SAMPLE_V1_YAML = """\
taxonomy:
  id: imlaa_v1_0
  title: علم الإملاء
  language: ar
  policy:
    leaf_atomic: true
  nodes:
  - id: alhamza
    title: الهمزة
    children:
    - id: ta3rif_alhamza
      title: تعريف الهمزة
      leaf: true
    - id: hamza_wasat_alkalima
      title: الهمزة المتوسطة
      children:
      - id: qawa3id_hamza_wasat__overview
        title: القواعد العامة
        leaf: true
      - id: hamza_wasat_3ala_alif
        title: الهمزة المتوسطة على ألف
        leaf: true
      - id: hamza_wasat_3ala_waw
        title: الهمزة المتوسطة على واو
        leaf: true
  - id: alalif
    title: الألف
    children:
    - id: alalif_layyina
      title: الألف اللينة
      leaf: true
"""

SAMPLE_V0_YAML = """\
imlaa:
  al_hamza:
    ta3rif_al_hamza:
      _leaf: true
    al_hamza_wasat_al_kalima:
      al_hamza_wasat__overview:
        _leaf: true
      al_hala_1_tursam_alifan:
        _leaf: true
      al_hala_2_tursam_wawan:
        _leaf: true
  al_alif:
    al_alif_al_layyina:
      _leaf: true
"""


def _make_atom(atom_id: str, text: str, role: str = "author_prose",
               atype: str = "prose_sentence") -> dict:
    return {
        "atom_id": atom_id,
        "type": atype,
        "role": role,
        "text": text,
    }


def _make_excerpt(
    excerpt_id: str,
    core_atoms: list,
    taxonomy_node_id: str = "ta3rif_alhamza",
    taxonomy_path: str = "إملاء > الهمزة > تعريف الهمزة",
    context_atoms: list | None = None,
    excerpt_title: str = "Test excerpt",
    excerpt_kind: str = "teaching",
    content_type: str = "prose",
    heading_path: list | None = None,
    boundary_reasoning: str = "Test reasoning",
) -> dict:
    return {
        "excerpt_id": excerpt_id,
        "excerpt_title": excerpt_title,
        "source_layer": "matn",
        "excerpt_kind": excerpt_kind,
        "taxonomy_node_id": taxonomy_node_id,
        "taxonomy_path": taxonomy_path,
        "heading_path": heading_path or [],
        "core_atoms": core_atoms,
        "context_atoms": context_atoms or [],
        "boundary_reasoning": boundary_reasoning,
        "content_type": content_type,
    }


def _make_footnote_excerpt(
    excerpt_id: str,
    text: str,
    linked_matn: str,
    taxonomy_node_id: str = "ta3rif_alhamza",
    taxonomy_path: str = "إملاء > الهمزة > تعريف الهمزة",
    note: str = "Footnote note",
) -> dict:
    return {
        "excerpt_id": excerpt_id,
        "excerpt_title": "Test footnote",
        "source_layer": "footnote",
        "excerpt_kind": "teaching",
        "taxonomy_node_id": taxonomy_node_id,
        "taxonomy_path": taxonomy_path,
        "linked_matn_excerpt": linked_matn,
        "text": text,
        "note": note,
    }


def _make_book_meta() -> dict:
    return {
        "book_id": "qimlaa",
        "title": "قواعد الإملاء",
        "author": "عبد السلام محمد هارون (ت 1408هـ)",
        "publisher": "مكتبة الأنجلو المصرية",
        "primary_science": "imlaa",
        "scholarly_context": {
            "author_death_hijri": 1408,
            "author_birth_hijri": None,
            "fiqh_madhab": None,
            "grammatical_school": None,
            "geographic_origin": None,
        },
    }


# ---------------------------------------------------------------------------
# Taxonomy Parsing Tests
# ---------------------------------------------------------------------------

class TestTaxonomyParserV1:
    def test_finds_all_leaves(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(SAMPLE_V1_YAML, encoding="utf-8")
        result = parse_taxonomy_yaml(str(yaml_file), "imlaa")
        leaves = {nid for nid, info in result.items() if info.is_leaf}
        assert leaves == {
            "ta3rif_alhamza",
            "qawa3id_hamza_wasat__overview",
            "hamza_wasat_3ala_alif",
            "hamza_wasat_3ala_waw",
            "alalif_layyina",
        }

    def test_leaf_count(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(SAMPLE_V1_YAML, encoding="utf-8")
        result = parse_taxonomy_yaml(str(yaml_file), "imlaa")
        leaves = [n for n in result.values() if n.is_leaf]
        assert len(leaves) == 5

    def test_branch_nodes_included(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(SAMPLE_V1_YAML, encoding="utf-8")
        result = parse_taxonomy_yaml(str(yaml_file), "imlaa")
        assert "alhamza" in result
        assert "hamza_wasat_alkalima" in result
        assert not result["alhamza"].is_leaf
        assert not result["hamza_wasat_alkalima"].is_leaf

    def test_correct_folder_paths(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(SAMPLE_V1_YAML, encoding="utf-8")
        result = parse_taxonomy_yaml(str(yaml_file), "imlaa")
        assert result["ta3rif_alhamza"].folder_path == "imlaa/alhamza/ta3rif_alhamza"
        assert result["hamza_wasat_3ala_alif"].folder_path == (
            "imlaa/alhamza/hamza_wasat_alkalima/hamza_wasat_3ala_alif"
        )
        assert result["alalif_layyina"].folder_path == "imlaa/alalif/alalif_layyina"

    def test_path_ids_and_titles(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(SAMPLE_V1_YAML, encoding="utf-8")
        result = parse_taxonomy_yaml(str(yaml_file), "imlaa")
        node = result["hamza_wasat_3ala_alif"]
        assert node.path_ids == [
            "imlaa", "alhamza", "hamza_wasat_alkalima", "hamza_wasat_3ala_alif"
        ]
        assert node.path_titles == [
            "علم الإملاء", "الهمزة", "الهمزة المتوسطة", "الهمزة المتوسطة على ألف"
        ]

    def test_overview_node_is_leaf(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(SAMPLE_V1_YAML, encoding="utf-8")
        result = parse_taxonomy_yaml(str(yaml_file), "imlaa")
        assert "qawa3id_hamza_wasat__overview" in result
        assert result["qawa3id_hamza_wasat__overview"].is_leaf


class TestTaxonomyParserV0:
    def test_finds_all_leaves(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(SAMPLE_V0_YAML, encoding="utf-8")
        result = parse_taxonomy_yaml(str(yaml_file), "imlaa")
        leaves = {nid for nid, info in result.items() if info.is_leaf}
        assert leaves == {
            "ta3rif_al_hamza",
            "al_hamza_wasat__overview",
            "al_hala_1_tursam_alifan",
            "al_hala_2_tursam_wawan",
            "al_alif_al_layyina",
        }

    def test_correct_folder_paths(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(SAMPLE_V0_YAML, encoding="utf-8")
        result = parse_taxonomy_yaml(str(yaml_file), "imlaa")
        assert result["ta3rif_al_hamza"].folder_path == (
            "imlaa/al_hamza/ta3rif_al_hamza"
        )
        assert result["al_hala_1_tursam_alifan"].folder_path == (
            "imlaa/al_hamza/al_hamza_wasat_al_kalima/al_hala_1_tursam_alifan"
        )

    def test_branch_nodes_included(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(SAMPLE_V0_YAML, encoding="utf-8")
        result = parse_taxonomy_yaml(str(yaml_file), "imlaa")
        assert "al_hamza" in result
        assert "al_hamza_wasat_al_kalima" in result
        assert not result["al_hamza"].is_leaf


class TestTaxonomyFormatDetection:
    def test_detects_v1(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(SAMPLE_V1_YAML, encoding="utf-8")
        assert detect_taxonomy_format(str(yaml_file)) == "v1"

    def test_detects_v0(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(SAMPLE_V0_YAML, encoding="utf-8")
        assert detect_taxonomy_format(str(yaml_file)) == "v0"


class TestTaxonomyEdgeCases:
    def test_empty_yaml(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("", encoding="utf-8")
        result = parse_taxonomy_yaml(str(yaml_file), "imlaa")
        assert result == {}

    def test_yaml_with_only_metadata(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("taxonomy:\n  id: test\n  title: Test\n  nodes: []\n",
                             encoding="utf-8")
        result = parse_taxonomy_yaml(str(yaml_file), "imlaa")
        assert result == {}


# ---------------------------------------------------------------------------
# Atom Resolution Tests
# ---------------------------------------------------------------------------

class TestAtomResolution:
    def test_extract_atom_id_string(self):
        assert _extract_atom_id("qimlaa:matn:000001") == "qimlaa:matn:000001"

    def test_extract_atom_id_dict(self):
        assert _extract_atom_id({"atom_id": "qimlaa:matn:000001", "role": "author_prose"}) == "qimlaa:matn:000001"

    def test_extract_atom_id_other(self):
        assert _extract_atom_id(42) == ""

    def test_extract_atom_role_from_dict(self):
        assert _extract_atom_role({"atom_id": "x", "role": "evidence"}) == "evidence"

    def test_extract_atom_role_from_string(self):
        assert _extract_atom_role("x") == ""

    def test_build_atoms_index(self):
        atoms = [
            _make_atom("a:m:001", "text one"),
            _make_atom("a:m:002", "text two"),
        ]
        idx = build_atoms_index(atoms)
        assert len(idx) == 2
        assert idx["a:m:001"]["text"] == "text one"
        assert idx["a:m:002"]["text"] == "text two"

    def test_resolve_atom_texts_success(self):
        idx = build_atoms_index([
            _make_atom("a:m:001", "الأولى"),
            _make_atom("a:m:002", "الثانية"),
        ])
        text, resolved, missing = resolve_atom_texts(["a:m:001", "a:m:002"], idx)
        assert text == "الأولى\n\nالثانية"
        assert len(resolved) == 2
        assert resolved[0]["text"] == "الأولى"
        assert missing == []

    def test_resolve_atom_texts_with_objects(self):
        idx = build_atoms_index([_make_atom("a:m:001", "text")])
        text, resolved, missing = resolve_atom_texts(
            [{"atom_id": "a:m:001", "role": "evidence"}], idx
        )
        assert text == "text"
        assert resolved[0]["role"] == "evidence"

    def test_resolve_atom_texts_missing(self):
        idx = build_atoms_index([_make_atom("a:m:001", "text")])
        text, resolved, missing = resolve_atom_texts(
            ["a:m:001", "a:m:999"], idx
        )
        assert text == "text"
        assert missing == ["a:m:999"]


# ---------------------------------------------------------------------------
# Excerpt Assembly Tests
# ---------------------------------------------------------------------------

class TestAssembleMatnExcerpt:
    def _make_taxonomy_map(self):
        return {
            "ta3rif_alhamza": TaxonomyNodeInfo(
                node_id="ta3rif_alhamza",
                title="تعريف الهمزة",
                path_ids=["imlaa", "alhamza", "ta3rif_alhamza"],
                path_titles=["علم الإملاء", "الهمزة", "تعريف الهمزة"],
                is_leaf=True,
                folder_path="imlaa/alhamza/ta3rif_alhamza",
            ),
        }

    def test_basic_assembly(self):
        atoms = [_make_atom("q:m:001", "تعريف الهمزة هو حرف مخصوص")]
        idx = build_atoms_index(atoms)
        excerpt = _make_excerpt("q:exc:001", core_atoms=["q:m:001"])
        meta = _make_book_meta()
        tax_map = self._make_taxonomy_map()

        assembled, errs = assemble_matn_excerpt(
            excerpt, idx, [], meta, tax_map, "imlaa", "P001", "P001_extraction.json"
        )
        assert assembled is not None
        assert errs == []
        assert assembled["schema_version"] == SCHEMA_VERSION
        assert assembled["excerpt_id"] == "q:exc:001"
        assert assembled["book_title"] == "قواعد الإملاء"
        assert assembled["author"] == "عبد السلام محمد هارون (ت 1408هـ)"
        assert assembled["core_text"] == "تعريف الهمزة هو حرف مخصوص"
        assert assembled["full_text"] == "تعريف الهمزة هو حرف مخصوص"
        assert assembled["context_text"] == ""
        assert assembled["taxonomy_node_title"] == "تعريف الهمزة"
        assert assembled["science"] == "imlaa"
        assert assembled["scholarly_context"]["author_death_hijri"] == 1408

    def test_with_context_atoms(self):
        atoms = [
            _make_atom("q:m:001", "مقدمة السياق"),
            _make_atom("q:m:002", "المحتوى الأساسي"),
        ]
        idx = build_atoms_index(atoms)
        excerpt = _make_excerpt(
            "q:exc:001",
            core_atoms=["q:m:002"],
            context_atoms=["q:m:001"],
        )
        meta = _make_book_meta()
        tax_map = self._make_taxonomy_map()

        assembled, errs = assemble_matn_excerpt(
            excerpt, idx, [], meta, tax_map, "imlaa", "P001", "P001_extraction.json"
        )
        assert assembled is not None
        assert assembled["context_text"] == "مقدمة السياق"
        assert assembled["core_text"] == "المحتوى الأساسي"
        assert assembled["full_text"] == "مقدمة السياق\n\nالمحتوى الأساسي"

    def test_with_linked_footnotes(self):
        atoms = [_make_atom("q:m:001", "النص الأساسي")]
        idx = build_atoms_index(atoms)
        excerpt = _make_excerpt("q:exc:001", core_atoms=["q:m:001"])
        fn_excerpts = [
            _make_footnote_excerpt(
                "q:exc:fn:001", "نص الحاشية", "q:exc:001",
                note="تعليق على النص"
            ),
        ]
        meta = _make_book_meta()
        tax_map = self._make_taxonomy_map()

        assembled, errs = assemble_matn_excerpt(
            excerpt, idx, fn_excerpts, meta, tax_map, "imlaa", "P001", "P001_extraction.json"
        )
        assert assembled is not None
        assert len(assembled["footnotes"]) == 1
        assert assembled["footnotes"][0]["text"] == "نص الحاشية"
        assert assembled["footnotes"][0]["note"] == "تعليق على النص"

    def test_unlinked_footnote_not_included(self):
        atoms = [_make_atom("q:m:001", "text")]
        idx = build_atoms_index(atoms)
        excerpt = _make_excerpt("q:exc:001", core_atoms=["q:m:001"])
        fn_excerpts = [
            _make_footnote_excerpt("q:exc:fn:001", "footnote text", "q:exc:999"),
        ]
        meta = _make_book_meta()
        tax_map = self._make_taxonomy_map()

        assembled, errs = assemble_matn_excerpt(
            excerpt, idx, fn_excerpts, meta, tax_map, "imlaa", "P001", "P001_extraction.json"
        )
        assert assembled is not None
        assert assembled["footnotes"] == []

    def test_missing_atom_error(self):
        idx = build_atoms_index([])  # empty
        excerpt = _make_excerpt("q:exc:001", core_atoms=["q:m:001"])
        meta = _make_book_meta()
        tax_map = self._make_taxonomy_map()

        assembled, errs = assemble_matn_excerpt(
            excerpt, idx, [], meta, tax_map, "imlaa", "P001", "P001_extraction.json"
        )
        assert assembled is None
        assert any("missing core atoms" in e for e in errs)

    def test_core_atoms_object_format(self):
        atoms = [_make_atom("q:m:001", "text content")]
        idx = build_atoms_index(atoms)
        excerpt = _make_excerpt(
            "q:exc:001",
            core_atoms=[{"atom_id": "q:m:001", "role": "evidence"}],
        )
        meta = _make_book_meta()
        tax_map = self._make_taxonomy_map()

        assembled, errs = assemble_matn_excerpt(
            excerpt, idx, [], meta, tax_map, "imlaa", "P001", "P001_extraction.json"
        )
        assert assembled is not None
        assert assembled["core_text"] == "text content"
        assert assembled["core_atoms"][0]["role"] == "evidence"

    def test_unknown_taxonomy_node(self):
        atoms = [_make_atom("q:m:001", "text")]
        idx = build_atoms_index(atoms)
        excerpt = _make_excerpt(
            "q:exc:001",
            core_atoms=["q:m:001"],
            taxonomy_node_id="nonexistent_node",
        )
        meta = _make_book_meta()
        tax_map = self._make_taxonomy_map()

        assembled, errs = assemble_matn_excerpt(
            excerpt, idx, [], meta, tax_map, "imlaa", "P001", "P001_extraction.json"
        )
        assert assembled is not None
        assert assembled["taxonomy_node_title"] == ""  # Not found

    def test_provenance_fields(self):
        atoms = [_make_atom("q:m:001", "text")]
        idx = build_atoms_index(atoms)
        excerpt = _make_excerpt("q:exc:001", core_atoms=["q:m:001"])
        meta = _make_book_meta()
        tax_map = self._make_taxonomy_map()

        assembled, errs = assemble_matn_excerpt(
            excerpt, idx, [], meta, tax_map, "imlaa", "P004", "P004_extraction.json"
        )
        prov = assembled["provenance"]
        assert prov["extraction_passage_id"] == "P004"
        assert prov["extraction_file"] == "P004_extraction.json"
        assert prov["source_atoms"]["core"] == ["q:m:001"]
        assert prov["source_atoms"]["context"] == []
        assert "assembled_utc" in prov

    def test_multiple_core_atoms_concatenated(self):
        atoms = [
            _make_atom("q:m:001", "الجملة الأولى"),
            _make_atom("q:m:002", "الجملة الثانية"),
            _make_atom("q:m:003", "الجملة الثالثة"),
        ]
        idx = build_atoms_index(atoms)
        excerpt = _make_excerpt(
            "q:exc:001",
            core_atoms=["q:m:001", "q:m:002", "q:m:003"],
        )
        meta = _make_book_meta()
        tax_map = self._make_taxonomy_map()

        assembled, errs = assemble_matn_excerpt(
            excerpt, idx, [], meta, tax_map, "imlaa", "P001", "P001_extraction.json"
        )
        assert assembled["core_text"] == "الجملة الأولى\n\nالجملة الثانية\n\nالجملة الثالثة"


class TestAssembleFootnoteExcerpt:
    def test_basic_footnote_assembly(self):
        fn = _make_footnote_excerpt(
            "q:exc:fn:001", "محتوى الحاشية", "q:exc:001"
        )
        meta = _make_book_meta()
        tax_map = {
            "ta3rif_alhamza": TaxonomyNodeInfo(
                node_id="ta3rif_alhamza",
                title="تعريف الهمزة",
                path_ids=["imlaa", "alhamza", "ta3rif_alhamza"],
                path_titles=["علم الإملاء", "الهمزة", "تعريف الهمزة"],
                is_leaf=True,
                folder_path="imlaa/alhamza/ta3rif_alhamza",
            ),
        }

        assembled = assemble_footnote_excerpt(
            fn, meta, tax_map, "imlaa", "P001", "P001_extraction.json"
        )
        assert assembled["excerpt_id"] == "q:exc:fn:001"
        assert assembled["source_layer"] == "footnote"
        assert assembled["core_text"] == "محتوى الحاشية"
        assert assembled["full_text"] == "محتوى الحاشية"
        assert assembled["linked_matn_excerpt"] == "q:exc:001"
        assert assembled["book_title"] == "قواعد الإملاء"
        assert assembled["context_text"] == ""


# ---------------------------------------------------------------------------
# Filename Derivation Tests
# ---------------------------------------------------------------------------

class TestDeriveFilename:
    def test_matn_excerpt(self):
        assert derive_filename("qimlaa:exc:000001") == "qimlaa_exc_000001.json"

    def test_footnote_excerpt(self):
        assert derive_filename("qimlaa:exc:fn:000001") == "qimlaa_exc_fn_000001.json"

    def test_different_book_id(self):
        assert derive_filename("shadha:exc:000042") == "shadha_exc_000042.json"


# ---------------------------------------------------------------------------
# Distribution Tests
# ---------------------------------------------------------------------------

class TestDistributeExcerpts:
    def _make_simple_taxonomy_map(self):
        return {
            "ta3rif_alhamza": TaxonomyNodeInfo(
                node_id="ta3rif_alhamza",
                title="تعريف الهمزة",
                path_ids=["imlaa", "alhamza", "ta3rif_alhamza"],
                path_titles=["علم الإملاء", "الهمزة", "تعريف الهمزة"],
                is_leaf=True,
                folder_path="imlaa/alhamza/ta3rif_alhamza",
            ),
            "hamza_wasat_3ala_alif": TaxonomyNodeInfo(
                node_id="hamza_wasat_3ala_alif",
                title="الهمزة المتوسطة على ألف",
                path_ids=["imlaa", "alhamza", "hamza_wasat_alkalima",
                           "hamza_wasat_3ala_alif"],
                path_titles=["علم الإملاء", "الهمزة", "الهمزة المتوسطة",
                              "الهمزة المتوسطة على ألف"],
                is_leaf=True,
                folder_path="imlaa/alhamza/hamza_wasat_alkalima/hamza_wasat_3ala_alif",
            ),
        }

    def test_creates_correct_folders(self, tmp_path):
        tax_map = self._make_simple_taxonomy_map()
        excerpts = [
            {"excerpt_id": "q:exc:001", "taxonomy_node_id": "ta3rif_alhamza",
             "book_id": "q", "core_text": "t"},
            {"excerpt_id": "q:exc:002", "taxonomy_node_id": "hamza_wasat_3ala_alif",
             "book_id": "q", "core_text": "t"},
        ]
        result = distribute_excerpts(excerpts, tax_map, str(tmp_path), "imlaa")
        assert result["files_written"] == 2
        assert result["unique_nodes_populated"] == 2
        assert (tmp_path / "imlaa/alhamza/ta3rif_alhamza/q_exc_001.json").exists()
        assert (
            tmp_path / "imlaa/alhamza/hamza_wasat_alkalima/hamza_wasat_3ala_alif"
            / "q_exc_002.json"
        ).exists()

    def test_unmapped_placement(self, tmp_path):
        tax_map = self._make_simple_taxonomy_map()
        excerpts = [
            {"excerpt_id": "q:exc:001", "taxonomy_node_id": "unknown_node",
             "book_id": "q", "core_text": "t"},
        ]
        result = distribute_excerpts(excerpts, tax_map, str(tmp_path), "imlaa")
        assert result["files_written"] == 1
        assert len(result["warnings"]) == 1
        assert "not found" in result["warnings"][0]
        assert (tmp_path / "imlaa/_unmapped/q_exc_001.json").exists()

    def test_dry_run_no_files(self, tmp_path):
        tax_map = self._make_simple_taxonomy_map()
        excerpts = [
            {"excerpt_id": "q:exc:001", "taxonomy_node_id": "ta3rif_alhamza",
             "book_id": "q", "core_text": "t"},
        ]
        result = distribute_excerpts(
            excerpts, tax_map, str(tmp_path), "imlaa", dry_run=True
        )
        assert result["files_written"] == 1  # counted but not written
        # No actual files should exist
        assert not (tmp_path / "imlaa").exists()

    def test_same_book_duplicates_logged(self, tmp_path):
        tax_map = self._make_simple_taxonomy_map()
        excerpts = [
            {"excerpt_id": "q:exc:001", "taxonomy_node_id": "ta3rif_alhamza",
             "book_id": "q", "core_text": "t1"},
            {"excerpt_id": "q:exc:002", "taxonomy_node_id": "ta3rif_alhamza",
             "book_id": "q", "core_text": "t2"},
        ]
        result = distribute_excerpts(excerpts, tax_map, str(tmp_path), "imlaa")
        assert result["files_written"] == 2
        dupes = result["same_book_at_same_node"]
        assert len(dupes) == 1
        assert dupes[0]["node_id"] == "ta3rif_alhamza"
        assert dupes[0]["count"] == 2

    def test_full_tree_creates_empty_folders(self, tmp_path):
        tax_map = self._make_simple_taxonomy_map()
        excerpts = [
            {"excerpt_id": "q:exc:001", "taxonomy_node_id": "ta3rif_alhamza",
             "book_id": "q", "core_text": "t"},
        ]
        distribute_excerpts(
            excerpts, tax_map, str(tmp_path), "imlaa", full_tree=True
        )
        # Both leaf folders should exist even though only one has content
        assert (tmp_path / "imlaa/alhamza/ta3rif_alhamza").is_dir()
        assert (
            tmp_path / "imlaa/alhamza/hamza_wasat_alkalima/hamza_wasat_3ala_alif"
        ).is_dir()

    def test_json_output_format(self, tmp_path):
        tax_map = self._make_simple_taxonomy_map()
        excerpts = [
            {"excerpt_id": "q:exc:001", "taxonomy_node_id": "ta3rif_alhamza",
             "book_id": "q", "core_text": "تعريف الهمزة"},
        ]
        distribute_excerpts(excerpts, tax_map, str(tmp_path), "imlaa")
        fpath = tmp_path / "imlaa/alhamza/ta3rif_alhamza/q_exc_001.json"
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        assert data["excerpt_id"] == "q:exc:001"
        assert data["core_text"] == "تعريف الهمزة"


# ---------------------------------------------------------------------------
# Validation Tests
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_excerpt(self):
        exc = {
            "excerpt_id": "q:exc:001",
            "core_text": "Some text",
            "book_title": "Test Book",
            "taxonomy_node_id": "test_node",
            "taxonomy_path": "Test > Path",
        }
        assert validate_assembled_excerpt(exc) == []

    def test_missing_core_text(self):
        exc = {
            "excerpt_id": "q:exc:001",
            "core_text": "",
            "book_title": "Test Book",
            "taxonomy_node_id": "test_node",
            "taxonomy_path": "Test > Path",
        }
        issues = validate_assembled_excerpt(exc)
        assert any("empty core_text" in i for i in issues)

    def test_missing_excerpt_id(self):
        exc = {
            "core_text": "text",
            "book_title": "Book",
            "taxonomy_node_id": "node",
            "taxonomy_path": "path",
        }
        issues = validate_assembled_excerpt(exc)
        assert any("missing excerpt_id" in i for i in issues)


# ---------------------------------------------------------------------------
# Extraction File Loading Tests
# ---------------------------------------------------------------------------

class TestLoadExtractionFiles:
    def test_loads_matching_files(self, tmp_path):
        data = {
            "atoms": [_make_atom("a:m:001", "text")],
            "excerpts": [_make_excerpt("a:e:001", ["a:m:001"])],
            "footnote_excerpts": [],
        }
        fpath = tmp_path / "P004_extraction.json"
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        result = load_extraction_files(str(tmp_path))
        assert len(result) == 1
        assert result[0]["passage_id"] == "P004"
        assert len(result[0]["atoms"]) == 1

    def test_filters_by_passage_id(self, tmp_path):
        for pid in ["P004", "P005", "P010"]:
            data = {"atoms": [], "excerpts": [], "footnote_excerpts": []}
            fpath = tmp_path / f"{pid}_extraction.json"
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f)

        result = load_extraction_files(str(tmp_path), passage_ids=["P004", "P010"])
        assert len(result) == 2
        pids = [r["passage_id"] for r in result]
        assert "P004" in pids
        assert "P010" in pids
        assert "P005" not in pids

    def test_empty_dir(self, tmp_path):
        result = load_extraction_files(str(tmp_path))
        assert result == []


# ---------------------------------------------------------------------------
# Report Generation Tests
# ---------------------------------------------------------------------------

class TestReportGeneration:
    def test_summary_has_required_fields(self):
        meta = _make_book_meta()
        dist_result = {
            "files_written": 5,
            "unique_nodes_populated": 3,
            "warnings": [],
            "same_book_at_same_node": [],
        }
        summary = generate_summary(
            meta, "imlaa", "imlaa_v1_0", "input/", "output/",
            3, 2, dist_result, []
        )
        assert summary["book_id"] == "qimlaa"
        assert summary["science"] == "imlaa"
        assert summary["total_matn_excerpts_assembled"] == 3
        assert summary["total_footnote_excerpts_assembled"] == 2
        assert summary["total_files_written"] == 5
        assert "assembled_utc" in summary

    def test_report_md_contains_book_info(self):
        summary = {
            "book_id": "qimlaa",
            "book_title": "قواعد الإملاء",
            "science": "imlaa",
            "taxonomy_version": "imlaa_v1_0",
            "assembled_utc": "2026-02-28T12:00:00",
            "total_matn_excerpts_assembled": 2,
            "total_footnote_excerpts_assembled": 1,
            "total_files_written": 3,
            "unique_nodes_populated": 2,
            "errors": [],
            "warnings": [],
            "same_book_at_same_node": [],
        }
        excerpts = [
            {
                "excerpt_id": "q:exc:001",
                "excerpt_title": "Test Title",
                "taxonomy_node_id": "ta3rif_alhamza",
                "source_layer": "matn",
            },
        ]
        tax_map = {
            "ta3rif_alhamza": TaxonomyNodeInfo(
                node_id="ta3rif_alhamza",
                title="تعريف الهمزة",
                path_ids=["imlaa", "alhamza", "ta3rif_alhamza"],
                path_titles=["علم الإملاء", "الهمزة", "تعريف الهمزة"],
                is_leaf=True,
                folder_path="imlaa/alhamza/ta3rif_alhamza",
            ),
        }
        report = generate_report_md(summary, excerpts, tax_map)
        assert "قواعد الإملاء" in report
        assert "ta3rif_alhamza" in report
        assert "Test Title" in report


# ---------------------------------------------------------------------------
# Integration Test
# ---------------------------------------------------------------------------

class TestIntegration:
    """Full pipeline integration with P004-like inline data."""

    def _make_p004_data(self):
        atoms = [
            _make_atom("qimlaa:matn:000001", "ونَحْوُ: امْرِئٍ", "examples_continuation",
                        "prose_tail"),
            _make_atom("qimlaa:matn:000002", "الْهَمْزَةُ وَسَطَ الْكَلِمَةِ", "structural",
                        "heading"),
            _make_atom("qimlaa:matn:000003",
                        "لِلْهَمْزَةِ فِي وَسَطِ الْكَلِمَةِ خَمْسُ حَالَاتٍ:",
                        "author_prose"),
            _make_atom("qimlaa:matn:000004",
                        "الْحَالَةُ الْأُولَى: تُرْسَمُ أَلِفًا فِي مَوْضِعَيْنِ:",
                        "structural", "heading"),
            _make_atom("qimlaa:matn:000005",
                        "1 - أَنْ تُسَكَّنَ أَوْ تُفْتَحَ وَلَوْ مُشَدَّدَةً بَعْدَ مَفْتُوحٍ",
                        "author_prose", "bonded_cluster"),
        ]

        excerpts = [
            _make_excerpt(
                "qimlaa:exc:000001",
                core_atoms=["qimlaa:matn:000003"],
                taxonomy_node_id="al_hamza_wasat_al_kalima__overview",
                taxonomy_path="إملاء > الهمزة > الهمزة وسط الكلمة > نظرة عامة",
                excerpt_title="حالات الهمزة وسط الكلمة — تقسيم عام (ص ٩)",
                heading_path=["الْبَابُ الْأَوَّلُ", "الْهَمْزَةُ وَسَطَ الْكَلِمَةِ"],
            ),
            _make_excerpt(
                "qimlaa:exc:000002",
                core_atoms=["qimlaa:matn:000005"],
                taxonomy_node_id="al_hala_1_tursam_alifan",
                taxonomy_path="إملاء > الهمزة > الهمزة وسط الكلمة > الحالة الأولى",
                excerpt_title="الحالة الأولى: ترسم ألفاً — الموضع الأول (ص ٩)",
                heading_path=["الْبَابُ الْأَوَّلُ", "الْهَمْزَةُ وَسَطَ الْكَلِمَةِ",
                               "الْحَالَةُ الْأُولَى"],
            ),
        ]

        footnote_excerpts = [
            _make_footnote_excerpt(
                "qimlaa:exc:fn:000001",
                "وأجازوا اجتماع الألفين هنا لئلا يلتبس",
                "qimlaa:exc:000002",
                taxonomy_node_id="al_hala_1_tursam_alifan",
                taxonomy_path="إملاء > الهمزة > الهمزة وسط الكلمة > الحالة الأولى",
            ),
        ]

        return {"atoms": atoms, "excerpts": excerpts,
                "footnote_excerpts": footnote_excerpts}

    def test_full_pipeline(self, tmp_path):
        # Write v0 taxonomy (matching the node IDs used in P004 extraction)
        taxonomy_yaml = """\
imlaa:
  al_hamza:
    al_hamza_wasat_al_kalima:
      al_hamza_wasat_al_kalima__overview:
        _leaf: true
      al_hala_1_tursam_alifan:
        _leaf: true
      al_hala_2_tursam_wawan:
        _leaf: true
"""
        yaml_file = tmp_path / "taxonomy.yaml"
        yaml_file.write_text(taxonomy_yaml, encoding="utf-8")

        # Write extraction file
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()
        data = self._make_p004_data()
        with open(ext_dir / "P004_extraction.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        # Write intake metadata
        meta = _make_book_meta()
        meta_file = tmp_path / "intake_metadata.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)

        # Parse taxonomy
        tax_map = parse_taxonomy_yaml(str(yaml_file), "imlaa")

        # Load extraction
        passages = load_extraction_files(str(ext_dir))
        assert len(passages) == 1

        # Assemble
        all_assembled = []
        passage = passages[0]
        idx = build_atoms_index(passage["atoms"])

        for exc in passage["excerpts"]:
            assembled, errs = assemble_matn_excerpt(
                exc, idx, passage["footnote_excerpts"],
                meta, tax_map, "imlaa", "P004", "P004_extraction.json"
            )
            assert assembled is not None
            all_assembled.append(assembled)

        for fn in passage["footnote_excerpts"]:
            assembled = assemble_footnote_excerpt(
                fn, meta, tax_map, "imlaa", "P004", "P004_extraction.json"
            )
            all_assembled.append(assembled)

        assert len(all_assembled) == 3  # 2 matn + 1 footnote

        # Distribute
        out_dir = tmp_path / "output"
        result = distribute_excerpts(all_assembled, tax_map, str(out_dir), "imlaa")

        assert result["files_written"] == 3
        assert result["unique_nodes_populated"] == 2  # overview + hala_1

        # Verify file locations
        assert (
            out_dir / "imlaa/al_hamza/al_hamza_wasat_al_kalima"
            / "al_hamza_wasat_al_kalima__overview"
            / "qimlaa_exc_000001.json"
        ).exists()
        assert (
            out_dir / "imlaa/al_hamza/al_hamza_wasat_al_kalima"
            / "al_hala_1_tursam_alifan"
            / "qimlaa_exc_000002.json"
        ).exists()
        assert (
            out_dir / "imlaa/al_hamza/al_hamza_wasat_al_kalima"
            / "al_hala_1_tursam_alifan"
            / "qimlaa_exc_fn_000001.json"
        ).exists()

        # Verify self-containment of a matn excerpt
        with open(
            out_dir / "imlaa/al_hamza/al_hamza_wasat_al_kalima"
            / "al_hala_1_tursam_alifan"
            / "qimlaa_exc_000002.json",
            encoding="utf-8"
        ) as f:
            exc_data = json.load(f)

        assert exc_data["schema_version"] == SCHEMA_VERSION
        assert exc_data["book_title"] == "قواعد الإملاء"
        assert exc_data["author"] == "عبد السلام محمد هارون (ت 1408هـ)"
        assert exc_data["scholarly_context"]["author_death_hijri"] == 1408
        assert "أَنْ تُسَكَّنَ" in exc_data["core_text"]
        assert len(exc_data["footnotes"]) == 1
        assert "اجتماع الألفين" in exc_data["footnotes"][0]["text"]
        assert exc_data["taxonomy_node_id"] == "al_hala_1_tursam_alifan"
        assert exc_data["taxonomy_path"] == (
            "إملاء > الهمزة > الهمزة وسط الكلمة > الحالة الأولى"
        )


# ---------------------------------------------------------------------------
# Science-Agnostic Engine Tests
# ---------------------------------------------------------------------------

class TestScienceAgnostic:
    """Verify the engine accepts arbitrary science names (Ilm Digest readiness)."""

    def test_assembly_accepts_unknown_science(self, tmp_path):
        """Assembly should work with non-standard science names like 'fiqh'."""
        from tools.assemble_excerpts import parse_taxonomy_yaml, KNOWN_SCIENCES

        # Verify known set is just informational
        assert "fiqh" not in KNOWN_SCIENCES

        # Create a minimal v0 taxonomy for 'fiqh'
        tax_yaml = tmp_path / "fiqh_v1.yaml"
        tax_yaml.write_text(
            "fiqh:\n  kitab_altahara:\n    _leaf: true\n",
            encoding="utf-8"
        )

        # parse_taxonomy_yaml should work with any science
        nodes = parse_taxonomy_yaml(str(tax_yaml), "fiqh")
        assert len(nodes) >= 1  # at least the leaf
        leaves = {nid for nid, n in nodes.items() if n.is_leaf}
        assert "kitab_altahara" in leaves

    def test_evolution_accepts_arbitrary_science(self):
        """Evolution signal creation works with any science string."""
        from tools.evolve_taxonomy import EvolutionSignal

        signal = EvolutionSignal(
            signal_type="same_book_cluster",
            node_id="ahkam_altahara",
            science="fiqh",
            excerpt_ids=["fqh:exc:001"],
            excerpt_texts=["نص فقهي"],
            excerpt_metadata=[{"excerpt_id": "fqh:exc:001"}],
            context="test",
        )
        assert signal.science == "fiqh"

    def test_extract_taxonomy_leaves_with_custom_science(self, tmp_path):
        """extract_taxonomy_leaves should work with any science."""
        from tools.extract_passages import extract_taxonomy_leaves

        tax_yaml = tmp_path / "hadith_v1.yaml"
        tax_yaml.write_text(
            "hadith:\n  mustalah:\n    _leaf: true\n  jarh_wa_tadil:\n    _leaf: true\n",
            encoding="utf-8"
        )
        leaves = extract_taxonomy_leaves(str(tax_yaml), "hadith")
        assert "mustalah" in leaves
        assert "jarh_wa_tadil" in leaves


# ---------------------------------------------------------------------------
# BUG-043: Path normalization in assembly
# ---------------------------------------------------------------------------

class TestAssemblyPathNormalization:
    """BUG-043: Assembly should normalize full taxonomy paths to leaf IDs."""

    def test_distribute_normalizes_dot_path(self, tmp_path):
        """Excerpt with dot-path taxonomy_node_id should be placed correctly."""
        from tools.assemble_excerpts import distribute_excerpts, parse_taxonomy_yaml

        tax_yaml = tmp_path / "aq_v0.yaml"
        tax_yaml.write_text(
            "aqidah:\n  al_iman:\n    ta3rif:\n      _leaf: true\n",
            encoding="utf-8",
        )
        taxonomy_map = parse_taxonomy_yaml(str(tax_yaml), "aqidah")

        excerpt = {
            "excerpt_id": "test:exc:001",
            "book_id": "test",
            "taxonomy_node_id": "aqidah.al_iman.ta3rif",
        }

        result = distribute_excerpts(
            [excerpt], taxonomy_map, "aqidah", tmp_path, dry_run=True
        )
        # Should NOT appear in warnings about _unmapped
        unmapped_warnings = [w for w in result.get("warnings", []) if "_unmapped" in w]
        assert len(unmapped_warnings) == 0
        assert excerpt["taxonomy_node_id"] == "ta3rif"

    def test_distribute_normalizes_colon_path(self, tmp_path):
        """Excerpt with colon-path taxonomy_node_id should be normalized."""
        from tools.assemble_excerpts import distribute_excerpts, parse_taxonomy_yaml

        tax_yaml = tmp_path / "aq_v0.yaml"
        tax_yaml.write_text(
            "aqidah:\n  qadr:\n    maratib:\n      _leaf: true\n",
            encoding="utf-8",
        )
        taxonomy_map = parse_taxonomy_yaml(str(tax_yaml), "aqidah")

        excerpt = {
            "excerpt_id": "test:exc:002",
            "book_id": "test",
            "taxonomy_node_id": "aqidah:qadr:maratib",
        }

        result = distribute_excerpts(
            [excerpt], taxonomy_map, "aqidah", tmp_path, dry_run=True
        )
        unmapped_warnings = [w for w in result.get("warnings", []) if "_unmapped" in w]
        assert len(unmapped_warnings) == 0
        assert excerpt["taxonomy_node_id"] == "maratib"

    def test_plain_leaf_not_modified(self, tmp_path):
        """Excerpt with plain leaf ID should not be modified."""
        from tools.assemble_excerpts import distribute_excerpts, parse_taxonomy_yaml

        tax_yaml = tmp_path / "aq_v0.yaml"
        tax_yaml.write_text(
            "aqidah:\n  al_karamat:\n    _leaf: true\n",
            encoding="utf-8",
        )
        taxonomy_map = parse_taxonomy_yaml(str(tax_yaml), "aqidah")

        excerpt = {
            "excerpt_id": "test:exc:003",
            "book_id": "test",
            "taxonomy_node_id": "al_karamat",
        }

        result = distribute_excerpts(
            [excerpt], taxonomy_map, "aqidah", tmp_path, dry_run=True
        )
        unmapped_warnings = [w for w in result.get("warnings", []) if "_unmapped" in w]
        assert len(unmapped_warnings) == 0
        assert excerpt["taxonomy_node_id"] == "al_karamat"

    def test_assemble_matn_normalizes_node_id(self, tmp_path):
        """assemble_matn_excerpt should normalize full path node IDs."""
        from tools.assemble_excerpts import assemble_matn_excerpt, parse_taxonomy_yaml

        tax_yaml = tmp_path / "aq_v0.yaml"
        tax_yaml.write_text(
            "aqidah:\n  al_iman:\n    ta3rif:\n      _leaf: true\n",
            encoding="utf-8",
        )
        taxonomy_map = parse_taxonomy_yaml(str(tax_yaml), "aqidah")

        excerpt = {
            "excerpt_id": "test:exc:001",
            "taxonomy_node_id": "aqidah.al_iman.ta3rif",
            "taxonomy_path": "",
            "core_atoms": [{"atom_id": "t:matn:001", "role": "author_prose"}],
            "context_atoms": [],
            "boundary_reasoning": "test",
            "excerpt_title": "test",
            "excerpt_kind": "teaching",
            "source_layer": "matn",
            "case_types": ["A1_pure_definition"],
        }
        atoms_index = {"t:matn:001": {"text": "نص تجريبي"}}
        book_meta = {"book_id": "test", "title": "كتاب", "author": "مؤلف",
                     "publisher": "", "scholarly_context": {}}

        assembled, errors = assemble_matn_excerpt(
            excerpt, atoms_index, [], book_meta, taxonomy_map, "aqidah",
            "P001", "P001_extraction.json"
        )
        assert assembled["taxonomy_node_id"] == "ta3rif"
