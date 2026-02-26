# AUDIT — passage3 (v0.3.13)

- Scaffolded baseline folder.

## Patch: QA-review labeling + explicit test-node propagation

- Added `C3_qa_review` to the `case_types` of the **أسئلة على الفصاحة** set excerpt and all its item excerpts (taxonomy node `as2ila_alfasaha`) to distinguish review questions from generic exercises.
- For `tatbiq_fasahat_alkalam` items that have a linked footnote-layer answer excerpt with an explicit defect `primary_test_node` (i.e., not the generic `tatbiq_fasahat_alkalam`), propagated:
  - `primary_test_node` and `tests_nodes` from the answer → the item.
  - Added a short `TEST-NODE:` note in `boundary_reasoning` stating the answer excerpt used.

---

## v0.3.9 — CP6 audit hardening + taxonomy registry identity

**Date:** 2026-02-22
**Schema:** gold_standard_schema_v0.3.1.json (unchanged)

Changes (packaging/audit; no atom/excerpt boundary changes):
- CP6 now produces `checkpoint_outputs/cp6_tool_fingerprint.json` (tool + key-file sha256 anchor).
- `validation_report.txt` is regenerated from the actual CP6 validator stdout to prevent stale reports.
- `baseline_manifest.json` is refreshed at CP6 to reflect the exact baseline file inventory.
- Validation commands now include `--taxonomy-registry` to enforce taxonomy snapshot identity against `ABD/taxonomy/taxonomy_registry.yaml`.

Rationale: remove audit drift and make the baseline package unambiguous for a future AI software builder.

---

## 2026-02-24 — Snapshot tool de-confusion (docs-only)

Changes (docs/comments only; no atom/excerpt boundary changes):
- Added explicit **SNAPSHOT (NON-CANONICAL)** banners to passage-local tool snapshots:
  - `validate_gold.py`
  - `tools/render_excerpts_md.py`

Rationale: prevent future builders from accidentally treating baseline-local snapshots as the canonical
validator/renderer, which live under `ABD/tools/`.

---

## 2026-02-24 — v0.3.13 strict-lints activation + taxonomy snapshot clarification

Changes (docs/metadata only; no atom/excerpt boundary changes):
- Baseline version bumped to **v0.3.13** to enable validator strict-lints (ref-style + checklist-version drift) per `ABD/tools/validate_gold.py`.
- Clarified taxonomy snapshot cohabitation:
  - This baseline is authored against **`balagha_v0_4.yaml`** (see `passage3_metadata.json: taxonomy_version`).
  - `balagha_v0_3.yaml` is retained as a historical snapshot for traceability only.
- Note: backup files such as `*.bak_*` may contain older prose/checklist references; they are retained for authoring archaeology and are **not** consumed by the validator.

Rationale: make Passage 3 safe as spec-by-example for a future AI software builder under the current canonical governance stack.

---

## 2026-02-24 — Baseline-root hygiene: moved backup artifacts to `_SCRATCH/`

Changes (packaging hygiene only; no atom/excerpt boundary changes):
- Moved transient patch backup files out of the baseline root into:
  - `_SCRATCH/backups/`
- Added `_SCRATCH/README.md` to clearly mark the folder as **NON-CANONICAL** and ignored by the pipeline/validator.

Rationale: reduce “future regret” risk where a builder misreads backup files as authoritative baseline artifacts.

- 2026-02-24: v0.3.14 packaging hygiene: moved passage-local governance/protocol full snapshots into _SCRATCH/snapshots and replaced root files with minimal stubs pointing to repo-level canon (ambiguity reduction for future builders).
