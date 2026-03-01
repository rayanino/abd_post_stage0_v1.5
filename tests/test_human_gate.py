"""Tests for tools/human_gate.py — Human Gate Infrastructure."""

import json
from pathlib import Path

import pytest

from tools.human_gate import (
    VALID_CORRECTION_TYPES,
    VALID_REVIEW_STATES,
    build_replay_context,
    create_correction_record,
    detect_patterns,
    find_correction_by_id,
    find_corrections_for_excerpt,
    get_checkpoint_summary,
    initialize_checkpoint_from_extraction,
    load_checkpoint,
    load_corrections,
    replay_correction,
    save_checkpoint,
    save_correction,
    save_pattern_report,
    update_checkpoint,
)


# ==========================================================================
# Correction cycle persistence tests
# ==========================================================================


class TestCreateCorrectionRecord:
    """Tests for create_correction_record."""

    def test_basic_placement_correction(self):
        record = create_correction_record(
            excerpt_id="E001",
            correction_type="placement",
            original_output={"taxonomy_node_id": "old_node"},
            human_correction={"new_taxonomy_node_id": "new_node"},
            reason="Wrong node",
            passage_id="P004",
            book_id="qimlaa",
            science="imlaa",
            model="claude-sonnet-4-5-20250929",
        )
        assert record["excerpt_id"] == "E001"
        assert record["correction_type"] == "placement"
        assert record["original_output"]["taxonomy_node_id"] == "old_node"
        assert record["human_correction"]["new_taxonomy_node_id"] == "new_node"
        assert record["reason"] == "Wrong node"
        assert record["passage_id"] == "P004"
        assert record["book_id"] == "qimlaa"
        assert record["science"] == "imlaa"
        assert record["model"] == "claude-sonnet-4-5-20250929"
        assert record["correction_id"].startswith("CORR-")
        assert "timestamp" in record

    def test_custom_correction_id(self):
        record = create_correction_record(
            excerpt_id="E001",
            correction_type="rejection",
            original_output={},
            human_correction={},
            correction_id="CORR-CUSTOM-001",
        )
        assert record["correction_id"] == "CORR-CUSTOM-001"

    def test_invalid_correction_type_raises(self):
        with pytest.raises(ValueError, match="Invalid correction_type"):
            create_correction_record(
                excerpt_id="E001",
                correction_type="invalid_type",
                original_output={},
                human_correction={},
            )

    def test_all_valid_correction_types(self):
        for ctype in VALID_CORRECTION_TYPES:
            record = create_correction_record(
                excerpt_id="E001",
                correction_type=ctype,
                original_output={},
                human_correction={},
            )
            assert record["correction_type"] == ctype

    def test_boundary_correction(self):
        record = create_correction_record(
            excerpt_id="E005",
            correction_type="boundary",
            original_output={
                "core_atoms": ["A001", "A002"],
                "context_atoms": [],
            },
            human_correction={
                "core_atoms": ["A001", "A002", "A003"],
                "context_atoms": ["A000"],
            },
            reason="Missing atom A003 is essential",
        )
        assert record["correction_type"] == "boundary"
        assert record["human_correction"]["core_atoms"] == ["A001", "A002", "A003"]


class TestSaveAndLoadCorrections:
    """Tests for save_correction and load_corrections."""

    def test_save_and_load(self, tmp_path):
        corr_file = str(tmp_path / "corrections.jsonl")

        rec1 = create_correction_record(
            excerpt_id="E001",
            correction_type="placement",
            original_output={"node": "a"},
            human_correction={"node": "b"},
            correction_id="CORR-001",
        )
        rec2 = create_correction_record(
            excerpt_id="E002",
            correction_type="rejection",
            original_output={},
            human_correction={},
            correction_id="CORR-002",
        )

        save_correction(rec1, corr_file)
        save_correction(rec2, corr_file)

        loaded = load_corrections(corr_file)
        assert len(loaded) == 2
        assert loaded[0]["correction_id"] == "CORR-001"
        assert loaded[1]["correction_id"] == "CORR-002"

    def test_load_nonexistent_returns_empty(self, tmp_path):
        loaded = load_corrections(str(tmp_path / "nonexistent.jsonl"))
        assert loaded == []

    def test_load_skips_malformed_lines(self, tmp_path):
        corr_file = tmp_path / "corrections.jsonl"
        corr_file.write_text(
            '{"correction_id": "CORR-001", "excerpt_id": "E001"}\n'
            'this is not json\n'
            '{"correction_id": "CORR-002", "excerpt_id": "E002"}\n',
            encoding="utf-8",
        )
        loaded = load_corrections(str(corr_file))
        assert len(loaded) == 2

    def test_creates_parent_directories(self, tmp_path):
        deep_path = str(tmp_path / "a" / "b" / "c" / "corrections.jsonl")
        rec = create_correction_record(
            excerpt_id="E001",
            correction_type="placement",
            original_output={},
            human_correction={},
        )
        save_correction(rec, deep_path)
        assert Path(deep_path).exists()


class TestFindCorrections:
    """Tests for find_correction_by_id and find_corrections_for_excerpt."""

    def test_find_by_id(self):
        corrections = [
            {"correction_id": "CORR-001", "excerpt_id": "E001"},
            {"correction_id": "CORR-002", "excerpt_id": "E002"},
        ]
        assert find_correction_by_id(corrections, "CORR-001")["excerpt_id"] == "E001"
        assert find_correction_by_id(corrections, "CORR-002")["excerpt_id"] == "E002"
        assert find_correction_by_id(corrections, "CORR-999") is None

    def test_find_for_excerpt(self):
        corrections = [
            {"correction_id": "CORR-001", "excerpt_id": "E001"},
            {"correction_id": "CORR-002", "excerpt_id": "E001"},
            {"correction_id": "CORR-003", "excerpt_id": "E002"},
        ]
        e001_corrs = find_corrections_for_excerpt(corrections, "E001")
        assert len(e001_corrs) == 2
        assert find_corrections_for_excerpt(corrections, "E999") == []


# ==========================================================================
# Correction replay tests
# ==========================================================================


class TestBuildReplayContext:
    """Tests for build_replay_context."""

    def test_placement_context(self):
        correction = {
            "excerpt_id": "E001",
            "correction_type": "placement",
            "original_output": {"taxonomy_node_id": "old_node"},
            "human_correction": {"new_taxonomy_node_id": "new_node"},
            "reason": "Wrong placement",
        }
        ctx = build_replay_context(correction)
        assert "HUMAN CORRECTION" in ctx
        assert "placement" in ctx
        assert "old_node" in ctx
        assert "new_node" in ctx
        assert "Wrong placement" in ctx

    def test_boundary_context(self):
        correction = {
            "excerpt_id": "E002",
            "correction_type": "boundary",
            "human_correction": {
                "core_atoms": ["A001", "A002", "A003"],
                "context_atoms": ["A000"],
            },
            "reason": "",
        }
        ctx = build_replay_context(correction)
        assert "boundary" in ctx
        assert "A001" in ctx

    def test_rejection_context(self):
        correction = {
            "excerpt_id": "E003",
            "correction_type": "rejection",
            "human_correction": {"rejection_reason": "Not relevant"},
            "reason": "Off-topic",
        }
        ctx = build_replay_context(correction)
        assert "REJECTED" in ctx
        assert "Not relevant" in ctx

    def test_attribution_context(self):
        correction = {
            "excerpt_id": "E004",
            "correction_type": "attribution",
            "human_correction": {"madhab": "حنفي", "school": "بصرة"},
            "reason": "",
        }
        ctx = build_replay_context(correction)
        assert "حنفي" in ctx
        assert "بصرة" in ctx

    def test_merge_context(self):
        correction = {
            "excerpt_id": "E005",
            "correction_type": "merge",
            "human_correction": {"merge_with_excerpt_id": "E006"},
            "reason": "",
        }
        ctx = build_replay_context(correction)
        assert "E006" in ctx

    def test_split_context(self):
        correction = {
            "excerpt_id": "E007",
            "correction_type": "split",
            "human_correction": {
                "split_excerpts": [
                    {"excerpt_id": "E007a"},
                    {"excerpt_id": "E007b"},
                ],
            },
            "reason": "",
        }
        ctx = build_replay_context(correction)
        assert "2 excerpts" in ctx


class TestReplayCorrection:
    """Tests for replay_correction using mock extraction function."""

    def test_replay_with_mock(self, tmp_path):
        correction = {
            "correction_id": "CORR-001",
            "excerpt_id": "E001",
            "passage_id": "P004",
            "correction_type": "placement",
            "human_correction": {"new_taxonomy_node_id": "new_node"},
            "reason": "Wrong node",
        }

        called_with = {}

        def mock_extract(passage_id, correction_context, model):
            called_with["passage_id"] = passage_id
            called_with["context"] = correction_context
            called_with["model"] = model
            return {"status": "success"}

        result = replay_correction(
            correction=correction,
            passages_file="dummy_passages.jsonl",
            pages_file="dummy_pages.jsonl",
            taxonomy_path="dummy_taxonomy.yaml",
            book_id="qimlaa",
            science="imlaa",
            output_dir=str(tmp_path / "replay"),
            call_extract_fn=mock_extract,
        )

        assert result["status"] == "completed"
        assert result["passage_id"] == "P004"
        assert called_with["passage_id"] == "P004"
        assert "HUMAN CORRECTION" in called_with["context"]

        # Check replay metadata was written
        meta_path = Path(result["replay_metadata_path"])
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["correction_id"] == "CORR-001"

    def test_replay_no_passage_id(self, tmp_path):
        correction = {
            "correction_id": "CORR-002",
            "excerpt_id": "E001",
            "correction_type": "placement",
            "human_correction": {},
        }
        result = replay_correction(
            correction=correction,
            passages_file="",
            pages_file="",
            taxonomy_path="",
            book_id="",
            science="",
            output_dir=str(tmp_path / "replay"),
        )
        assert result["status"] == "error"
        assert "no passage_id" in result["error"]


# ==========================================================================
# Pattern detection tests
# ==========================================================================


class TestDetectPatterns:
    """Tests for detect_patterns."""

    def test_empty_corrections(self):
        report = detect_patterns([])
        assert report["total_corrections"] == 0
        assert report["patterns"] == []

    def test_single_correction_no_patterns(self):
        corrections = [
            {
                "correction_type": "placement",
                "original_output": {"taxonomy_node_id": "n1"},
                "model": "claude",
                "science": "imlaa",
                "passage_id": "P001",
            },
        ]
        report = detect_patterns(corrections, min_count=2)
        assert report["total_corrections"] == 1
        # No patterns because min_count=2
        assert len(report["patterns"]) == 0

    def test_recurring_placement_pattern(self):
        corrections = [
            {
                "correction_type": "placement",
                "original_output": {"taxonomy_node_id": "problematic_node"},
                "model": "claude",
                "science": "imlaa",
                "passage_id": "P001",
            },
            {
                "correction_type": "placement",
                "original_output": {"taxonomy_node_id": "problematic_node"},
                "model": "claude",
                "science": "imlaa",
                "passage_id": "P002",
            },
            {
                "correction_type": "placement",
                "original_output": {"taxonomy_node_id": "problematic_node"},
                "model": "gpt-4o",
                "science": "imlaa",
                "passage_id": "P003",
            },
        ]
        report = detect_patterns(corrections, min_count=2)
        assert report["total_corrections"] == 3

        # Should detect recurring misplacement pattern
        node_patterns = [
            p for p in report["patterns"]
            if p["pattern_type"] == "recurring_misplacement"
        ]
        assert len(node_patterns) >= 1
        assert node_patterns[0]["key"] == "problematic_node"
        assert node_patterns[0]["count"] == 3

        # Should detect correction type frequency
        type_patterns = [
            p for p in report["patterns"]
            if p["pattern_type"] == "correction_type_frequency"
        ]
        assert len(type_patterns) >= 1

    def test_model_error_pattern(self):
        corrections = [
            {"correction_type": "placement", "original_output": {}, "model": "gpt-4o",
             "science": "imlaa", "passage_id": "P001"},
            {"correction_type": "boundary", "original_output": {}, "model": "gpt-4o",
             "science": "imlaa", "passage_id": "P002"},
            {"correction_type": "placement", "original_output": {}, "model": "claude",
             "science": "imlaa", "passage_id": "P003"},
        ]
        report = detect_patterns(corrections, min_count=2)

        model_patterns = [
            p for p in report["patterns"]
            if p["pattern_type"] == "model_error_rate"
        ]
        assert len(model_patterns) >= 1
        assert model_patterns[0]["key"] == "gpt-4o"
        assert model_patterns[0]["count"] == 2

    def test_passage_difficulty_pattern(self):
        corrections = [
            {"correction_type": "placement", "original_output": {},
             "model": "claude", "science": "imlaa", "passage_id": "P005"},
            {"correction_type": "boundary", "original_output": {},
             "model": "claude", "science": "imlaa", "passage_id": "P005"},
            {"correction_type": "rejection", "original_output": {},
             "model": "claude", "science": "imlaa", "passage_id": "P005"},
        ]
        report = detect_patterns(corrections, min_count=2)

        passage_patterns = [
            p for p in report["patterns"]
            if p["pattern_type"] == "passage_difficulty"
        ]
        assert len(passage_patterns) >= 1
        assert passage_patterns[0]["key"] == "P005"
        assert passage_patterns[0]["count"] == 3

    def test_by_model_and_science_counts(self):
        corrections = [
            {"correction_type": "placement", "original_output": {},
             "model": "claude", "science": "imlaa", "passage_id": "P001"},
            {"correction_type": "placement", "original_output": {},
             "model": "gpt-4o", "science": "nahw", "passage_id": "P002"},
        ]
        report = detect_patterns(corrections)
        assert report["by_model"]["claude"] == 1
        assert report["by_model"]["gpt-4o"] == 1
        assert report["by_science"]["imlaa"] == 1
        assert report["by_science"]["nahw"] == 1


class TestSavePatternReport:
    """Tests for save_pattern_report."""

    def test_saves_json_and_markdown(self, tmp_path):
        report = detect_patterns([
            {"correction_type": "placement", "original_output": {},
             "model": "claude", "science": "imlaa", "passage_id": "P001"},
            {"correction_type": "placement", "original_output": {},
             "model": "claude", "science": "imlaa", "passage_id": "P002"},
        ])
        json_path = save_pattern_report(report, str(tmp_path / "output"))

        assert Path(json_path).exists()
        assert (tmp_path / "output" / "correction_patterns.md").exists()

        # JSON is valid
        with open(json_path, encoding="utf-8") as f:
            loaded = json.loads(f.read())
        assert loaded["total_corrections"] == 2

        # Markdown contains key info
        md = (tmp_path / "output" / "correction_patterns.md").read_text(encoding="utf-8")
        assert "Correction Pattern Report" in md
        assert "placement" in md


# ==========================================================================
# Gate checkpoint tests
# ==========================================================================


class TestCheckpoints:
    """Tests for gate checkpoint functions."""

    def test_load_nonexistent_checkpoint(self, tmp_path):
        cp = load_checkpoint(str(tmp_path / "nonexistent"))
        assert cp["version"] == "0.1"
        assert cp["excerpts"] == {}

    def test_save_and_load_checkpoint(self, tmp_path):
        ext_dir = str(tmp_path / "extraction")
        Path(ext_dir).mkdir()

        cp = {
            "version": "0.1",
            "excerpts": {
                "E001": {"state": "approved", "timestamp": "2025-01-01T00:00:00Z"},
                "E002": {"state": "pending", "timestamp": "2025-01-01T00:00:00Z"},
            },
        }
        path = save_checkpoint(ext_dir, cp)
        assert Path(path).exists()

        loaded = load_checkpoint(ext_dir)
        assert loaded["excerpts"]["E001"]["state"] == "approved"
        assert loaded["excerpts"]["E002"]["state"] == "pending"

    def test_update_checkpoint_approve(self):
        cp = {
            "version": "0.1",
            "excerpts": {
                "E001": {"state": "pending", "timestamp": "", "reviewer": ""},
                "E002": {"state": "pending", "timestamp": "", "reviewer": ""},
            },
        }
        cp = update_checkpoint(cp, ["E001"], "approved", reviewer="rayane")
        assert cp["excerpts"]["E001"]["state"] == "approved"
        assert cp["excerpts"]["E001"]["reviewer"] == "rayane"
        assert cp["excerpts"]["E002"]["state"] == "pending"

    def test_update_checkpoint_reject(self):
        cp = {"version": "0.1", "excerpts": {
            "E001": {"state": "pending", "timestamp": "", "reviewer": ""},
        }}
        cp = update_checkpoint(cp, ["E001"], "rejected")
        assert cp["excerpts"]["E001"]["state"] == "rejected"

    def test_update_checkpoint_invalid_state(self):
        cp = {"version": "0.1", "excerpts": {}}
        with pytest.raises(ValueError, match="Invalid review state"):
            update_checkpoint(cp, ["E001"], "invalid_state")

    def test_update_multiple_excerpts(self):
        cp = {"version": "0.1", "excerpts": {
            "E001": {"state": "pending", "timestamp": "", "reviewer": ""},
            "E002": {"state": "pending", "timestamp": "", "reviewer": ""},
            "E003": {"state": "pending", "timestamp": "", "reviewer": ""},
        }}
        cp = update_checkpoint(cp, ["E001", "E003"], "approved")
        assert cp["excerpts"]["E001"]["state"] == "approved"
        assert cp["excerpts"]["E002"]["state"] == "pending"
        assert cp["excerpts"]["E003"]["state"] == "approved"

    def test_update_nonexistent_excerpt_creates_entry(self):
        cp = {"version": "0.1", "excerpts": {}}
        cp = update_checkpoint(cp, ["E_NEW"], "corrected")
        assert cp["excerpts"]["E_NEW"]["state"] == "corrected"


class TestCheckpointSummary:
    """Tests for get_checkpoint_summary."""

    def test_empty_checkpoint(self):
        cp = {"version": "0.1", "excerpts": {}}
        summary = get_checkpoint_summary(cp)
        assert summary["total"] == 0
        assert summary["pending_count"] == 0
        assert summary["pending_ids"] == []

    def test_mixed_states(self):
        cp = {"version": "0.1", "excerpts": {
            "E001": {"state": "approved"},
            "E002": {"state": "pending"},
            "E003": {"state": "rejected"},
            "E004": {"state": "pending"},
            "E005": {"state": "corrected"},
        }}
        summary = get_checkpoint_summary(cp)
        assert summary["total"] == 5
        assert summary["by_state"]["approved"] == 1
        assert summary["by_state"]["pending"] == 2
        assert summary["by_state"]["rejected"] == 1
        assert summary["by_state"]["corrected"] == 1
        assert sorted(summary["pending_ids"]) == ["E002", "E004"]
        assert summary["pending_count"] == 2


class TestInitializeCheckpoint:
    """Tests for initialize_checkpoint_from_extraction."""

    def test_initializes_from_extraction_files(self, tmp_path):
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()

        # Write extraction file
        passage = {
            "passage_id": "P001",
            "atoms": [],
            "excerpts": [
                {"excerpt_id": "E001", "taxonomy_node_id": "n1"},
                {"excerpt_id": "E002", "taxonomy_node_id": "n2"},
            ],
            "footnote_excerpts": [
                {"excerpt_id": "FE001", "taxonomy_node_id": "n3"},
            ],
        }
        (ext_dir / "P001_extraction.json").write_text(
            json.dumps(passage, ensure_ascii=False), encoding="utf-8",
        )

        cp = initialize_checkpoint_from_extraction(str(ext_dir))
        assert "E001" in cp["excerpts"]
        assert "E002" in cp["excerpts"]
        assert "FE001" in cp["excerpts"]
        assert cp["excerpts"]["E001"]["state"] == "pending"
        assert cp["excerpts"]["E002"]["state"] == "pending"
        assert cp["excerpts"]["FE001"]["state"] == "pending"

        # Should also be saved to disk
        saved = load_checkpoint(str(ext_dir))
        assert "E001" in saved["excerpts"]

    def test_empty_extraction_dir(self, tmp_path):
        ext_dir = tmp_path / "empty_extraction"
        ext_dir.mkdir()
        cp = initialize_checkpoint_from_extraction(str(ext_dir))
        assert cp["excerpts"] == {}

    def test_multiple_extraction_files(self, tmp_path):
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()

        for pid in ["P001", "P002"]:
            passage = {
                "passage_id": pid,
                "atoms": [],
                "excerpts": [
                    {"excerpt_id": f"{pid}-E001", "taxonomy_node_id": "n1"},
                ],
                "footnote_excerpts": [],
            }
            (ext_dir / f"{pid}_extraction.json").write_text(
                json.dumps(passage, ensure_ascii=False), encoding="utf-8",
            )

        cp = initialize_checkpoint_from_extraction(str(ext_dir))
        assert "P001-E001" in cp["excerpts"]
        assert "P002-E001" in cp["excerpts"]


# ==========================================================================
# Integration tests
# ==========================================================================


class TestFullCorrectionWorkflow:
    """End-to-end workflow: record → load → pattern detect → checkpoint."""

    def test_full_workflow(self, tmp_path):
        corr_file = str(tmp_path / "corrections" / "test.jsonl")

        # 1. Record corrections
        for i in range(5):
            rec = create_correction_record(
                excerpt_id=f"E{i:03d}",
                correction_type="placement" if i < 3 else "boundary",
                original_output={"taxonomy_node_id": "bad_node"},
                human_correction={"new_taxonomy_node_id": "good_node"},
                reason=f"Correction reason {i}",
                passage_id=f"P{i:03d}",
                model="claude",
                science="imlaa",
            )
            save_correction(rec, corr_file)

        # 2. Load and verify
        loaded = load_corrections(corr_file)
        assert len(loaded) == 5

        # 3. Find specific corrections
        e001_corrs = find_corrections_for_excerpt(loaded, "E001")
        assert len(e001_corrs) == 1

        # 4. Detect patterns
        report = detect_patterns(loaded, min_count=2)
        assert report["total_corrections"] == 5
        assert len(report["patterns"]) > 0

        # 5. Save pattern report
        report_path = save_pattern_report(report, str(tmp_path / "patterns"))
        assert Path(report_path).exists()

        # 6. Create and manage checkpoint
        ext_dir = tmp_path / "extraction"
        ext_dir.mkdir()
        passage = {
            "passage_id": "P001",
            "atoms": [],
            "excerpts": [
                {"excerpt_id": "E000", "taxonomy_node_id": "n1"},
                {"excerpt_id": "E001", "taxonomy_node_id": "n1"},
                {"excerpt_id": "E002", "taxonomy_node_id": "n2"},
            ],
            "footnote_excerpts": [],
        }
        (ext_dir / "P001_extraction.json").write_text(
            json.dumps(passage, ensure_ascii=False), encoding="utf-8",
        )

        cp = initialize_checkpoint_from_extraction(str(ext_dir))
        summary = get_checkpoint_summary(cp)
        assert summary["total"] == 3
        assert summary["pending_count"] == 3

        # 7. Approve some, reject one
        cp = update_checkpoint(cp, ["E000", "E001"], "approved")
        cp = update_checkpoint(cp, ["E002"], "corrected")
        save_checkpoint(str(ext_dir), cp)

        summary = get_checkpoint_summary(cp)
        assert summary["by_state"]["approved"] == 2
        assert summary["by_state"]["corrected"] == 1
        assert summary["pending_count"] == 0


class TestCorrectionIdMicrosecondPrecision:
    """BUG-FIX: correction IDs should use microsecond precision to avoid collisions."""

    def test_id_has_microseconds(self):
        from tools.human_gate import create_correction_record
        record = create_correction_record(
            excerpt_id="E001",
            correction_type="boundary",
            original_output={"text": "original"},
            human_correction={"text": "fixed"},
            passage_id="P001",
            book_id="test",
            science="imlaa",
            model="test-model",
            reason="Test",
        )
        cid = record["correction_id"]
        # Format: CORR-YYYYMMDDHHMMSSffffff-E001
        # The timestamp part should be 20 chars (14 date + 6 microsecond)
        parts = cid.split("-")
        assert len(parts) >= 3
        ts_part = parts[1]
        assert len(ts_part) == 20, f"Timestamp should include microseconds: {ts_part}"

    def test_timestamp_consistent_with_id(self):
        """timestamp field and correction_id should use the same datetime."""
        from tools.human_gate import create_correction_record
        record = create_correction_record(
            excerpt_id="E001",
            correction_type="boundary",
            original_output={"text": "original"},
            human_correction={"text": "fixed"},
            passage_id="P001",
            book_id="test",
            science="imlaa",
            model="test-model",
            reason="Test",
        )
        # Both should reference the same second
        cid_ts = record["correction_id"].split("-")[1][:14]  # YYYYMMDDHHMMSS
        iso_ts = record["timestamp"][:19].replace("-", "").replace("T", "").replace(":", "")
        assert cid_ts == iso_ts


class TestLoadCheckpointValidation:
    """BUG-FIX: load_checkpoint should validate JSON structure."""

    def test_corrupt_checkpoint_returns_default(self, tmp_path):
        from tools.human_gate import load_checkpoint
        cp_path = tmp_path / "gate_checkpoint.json"
        # Write a corrupt checkpoint (list instead of dict)
        cp_path.write_text("[1, 2, 3]", encoding="utf-8")
        result = load_checkpoint(str(tmp_path))
        assert result == {"version": "0.1", "excerpts": {}}

    def test_missing_excerpts_key_returns_default(self, tmp_path):
        from tools.human_gate import load_checkpoint
        cp_path = tmp_path / "gate_checkpoint.json"
        cp_path.write_text('{"version": "0.1"}', encoding="utf-8")
        result = load_checkpoint(str(tmp_path))
        assert result == {"version": "0.1", "excerpts": {}}

    def test_valid_checkpoint_loads_normally(self, tmp_path):
        from tools.human_gate import load_checkpoint
        cp_path = tmp_path / "gate_checkpoint.json"
        data = {"version": "0.1", "excerpts": {"E001": {"state": "approved"}}}
        cp_path.write_text(json.dumps(data), encoding="utf-8")
        result = load_checkpoint(str(tmp_path))
        assert result == data


class TestReplayCorrectionSignature:
    """BUG-FIX: replay_correction should build argparse.Namespace for run_extraction."""

    def test_replay_uses_injected_fn(self):
        """Testing path (call_extract_fn) still works as before."""
        from tools.human_gate import replay_correction
        import tempfile

        correction = {
            "correction_id": "CORR-TEST",
            "excerpt_id": "E001",
            "passage_id": "P001",
            "book_id": "test",
            "science": "imlaa",
            "model": "test-model",
            "correction_type": "boundary",
            "original_output": {"core_atoms": ["A001"]},
            "human_correction": {"core_atoms": ["A001", "A002"]},
            "reason": "Test reason",
        }

        captured = {}

        def mock_extract(**kwargs):
            captured.update(kwargs)
            return {"status": "ok"}

        with tempfile.TemporaryDirectory() as td:
            result = replay_correction(
                correction=correction,
                passages_file="passages.jsonl",
                pages_file="pages.jsonl",
                taxonomy_path="tax.yaml",
                book_id="test",
                science="imlaa",
                output_dir=td,
                call_extract_fn=mock_extract,
            )

        assert result["status"] == "completed"
        assert "correction_context" in captured
