# READ FIRST — ABD

If you are a new AI software builder (or resuming in a fresh session), start here.

1) Read `00_SESSION_CONTEXT.md`.
2) Read the binding file: `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md`.
3) Open the active gold baselines:
   - `2_atoms_and_excerpts/1_jawahir_al_balagha/ACTIVE_GOLD.md`

## Canonical reference files
- Binding: `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md`
- Schema: `schemas/gold_standard_schema_v0.3.3.json`
- Glossary: `project_glossary.md`
- Checklists: `2_atoms_and_excerpts/checklists_v0.4.md`
- Protocol: `2_atoms_and_excerpts/extraction_protocol_v2.4.md`

## Deprecated precision files
`precision/` contains older versions of binding decisions (v0.3.10, v0.3.15), checklists (v0.3), extraction protocol (v2), and glossary. These are retained for historical baseline reproducibility only. The canonical versions live in `2_atoms_and_excerpts/`.

## Canonical vs derived
- Canonical outputs are JSONL + metadata + taxonomy YAML.
- Markdown (`excerpts_rendered/`) is derived and must be regeneratable.

## Provenance contract (Checkpoint 1)
- Source slice provenance is formalized as a **source locator** object.
- See: `spec/source_locator_contract_v0.1.md` and `schemas/source_locator_schema_v0.1.json`.

## Operational tools
- Canonical latest tools live in `tools/`.
- Some (historical) baselines ship tool snapshots for reproducibility; active baselines may rely on canonical tools in `ABD/tools/`.

## Runtime setup (required)
ABD tooling requires **Python 3.11+** and the pinned deps in `requirements.txt`.
See: `spec/runtime_contract_v0.1.md`.

Typical setup (recommended venv):

```bash
python -m venv .venv
# Windows (PowerShell): .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python tools/check_env.py
```

## Run validations

```bash
python tools/run_all_validations.py
```

## Continuous Integration (CI)
If you host this repo on GitHub, CI is defined in:
- `.github/workflows/abd_validate.yml`

It runs the same pinned-environment setup plus `tools/check_env.py` and
`tools/run_all_validations.py` on push / pull request.

**Important:** GitHub only detects workflows at repository root. Recommended: make the
contents of the `ABD/` folder your repo root (so `.github/` is at the root).

## Checkpoint state
- Each baseline has a `checkpoint_state.json` state-machine file.
- Use `tools/pipeline_gold.py` to advance checkpoints; it updates the state file deterministically.

## Checkpoint output logs
- Each baseline has `checkpoint_outputs/` capturing stdout/stderr for CP1 and CP6.
- See: `spec/checkpoint_outputs_contract_v0.3.md`.

## Refresh baseline manifests (only when artifacts change)
If you add required artifacts (e.g., new log files), refresh the manifest:
```bash
python tools/build_baseline_manifest.py --baseline-dir <baseline_folder>
```
Then re-run CP6 (or update checkpoint_state integrity fields) so `checkpoint_state.json` matches the manifest sha.
