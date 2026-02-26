# Tools Compatibility

## Canonical location
- Canonical latest tools live in `ABD/tools/`.
- Some baseline packages carry tool snapshots (for reproducibility/history). Active baselines may rely on canonical tools in `ABD/tools/`. Any snapshots MUST NOT be edited in-place.

## Versioning
- `validate_gold.py` and `render_excerpts_md.py` include an internal version banner.
- A baseline's `passage*_metadata.json` records `validation.validator_version` and the exact command used.

## Supported schema(s)
Current canonical tools support:
- Gold record schema (canonical): `schemas/gold_standard_schema_v0.3.3.json`
- Support schemas (architecture):
  - `schemas/passage_metadata_schema_v0.1.json`
  - `schemas/baseline_manifest_schema_v0.1.json`
  - `schemas/decision_log_schema_v0.1.json`
  - `schemas/source_locator_schema_v0.1.json`
  - `schemas/checkpoint_state_schema_v0.1.json`

## Checkpoint-1 extractor
- `tools/extract_clean_input.py` emits `{passage}_source_slice.json` as a **source locator** object.
- Current tool version: **v0.2** (see tool header).

If schemas advance, tools MUST either:
- remain backward compatible, or
- ship compatibility shims and clearly document breaking changes.

## Baseline manifest builder
- `tools/build_baseline_manifest.py` refreshes `baseline_manifest.json` after new required artifacts are added (e.g., checkpoint_outputs logs).
- Excludes `baseline_manifest.json` and `checkpoint_state.json` from inventory + fingerprint to avoid hash cycles.

## Pipeline runner
- `tools/pipeline_gold.py` maintains `checkpoint_state.json` and captures CP1/CP6 stdout/stderr into `checkpoint_outputs/` (v0.3+).

## Deterministic checkpoint index
- `checkpoint_outputs/index.txt` is required when CP1+ is completed (see `spec/checkpoint_outputs_contract_v0.2.md`).
- Canonical algorithm: `tools/checkpoint_index_lib.py` (no timestamps; excludes cyclic/volatile files).
- CLI generator: `tools/generate_checkpoint_index.py`.
- Enforced by validator: `tools/validate_gold.py` v0.3.8+.

## Supportive dependency review block lint
- When an excerpt's `boundary_reasoning` contains a `SUPPORTIVE_DEPENDENCIES:` YAML block,
  the validator (v0.3.9+) parses and lints:
  - YAML shape (required keys/types)
  - that listed atoms are *only* in `context_atoms` (not `core_atoms`)
  - that context roles are restricted to `preceding_setup` / `cross_science_background`
  - boundedness exception marker requirements.
- This check is conditional: it triggers only when the marker block is present.
