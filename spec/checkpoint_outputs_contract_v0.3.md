# Checkpoint Outputs Contract v0.3

This specification defines **standardized execution-capture artifacts** for the 6-checkpoint gold pipeline,
including a deterministic `index.txt` for fast human approval.

Goals:
- Make the gold pipeline **reproducible and auditable** (including tool fingerprints).
- Ensure human approval gates and AI builders can review *exactly what ran* and *what artifacts exist*.
- Prevent nondeterminism traps (hash cycles, write races, timestamps).

## 1) Directory
Each baseline directory MUST contain:
- `checkpoint_outputs/`

This directory contains **non-canonical captured outputs** and **derived review aids**.
It MUST NOT be treated as canonical source content.

## 2) Required capture logs

### CP1 (after checkpoint 1 is completed)
The following files MUST exist:
- `checkpoint_outputs/cp1_extract_clean_input.stdout.txt`
- `checkpoint_outputs/cp1_extract_clean_input.stderr.txt`

### CP6 (after checkpoint 6 is completed)
The following files MUST exist:
- `checkpoint_outputs/cp6_validate.stdout.txt`
- `checkpoint_outputs/cp6_validate.stderr.txt`
- `checkpoint_outputs/cp6_render_md.stdout.txt`
- `checkpoint_outputs/cp6_render_md.stderr.txt`
- `checkpoint_outputs/cp6_tool_fingerprint.json`  *(machine-readable tool + baseline fingerprint)*

## 3) Deterministic index (required when CP1+ completed)

When `checkpoint_last_completed >= 1`, the following file MUST exist:
- `checkpoint_outputs/index.txt`

### 3.1 Purpose
`checkpoint_outputs/index.txt` is a **derived-only** review index optimized for:
- fast human approval,
- clear checkpoint status,
- artifact presence checks,
- a stable fingerprint that detects meaningful baseline changes.

It is generated deterministically from:
- `checkpoint_state.json` (commands, artifact lists, statuses),
- the baseline file inventory.

### 3.2 Non-negotiable determinism rules
`index.txt` MUST be:
- **deterministic** (no timestamps),
- **relative-path only** (no machine absolute paths),
- **exact-match validated** by the validator.

It MUST be regenerated via:
- `python tools/generate_checkpoint_index.py --baseline-dir <baseline_dir>`

Manual edits are forbidden.

### 3.3 No hash cycles / no write races
The fingerprint inside `index.txt` MUST NOT embed hashes of:
- `baseline_manifest.json`
- `checkpoint_state.json`
- `checkpoint_outputs/index.txt` itself

In addition, the fingerprint MUST NOT hash CP6 log files, because they are written while CP6 executes:
- `checkpoint_outputs/cp6_*.stdout.txt`
- `checkpoint_outputs/cp6_*.stderr.txt`

To prevent additional CP6 write races, the fingerprint MUST also exclude:
- `validation_report.txt`
- `excerpts_rendered/**`

These exclusions are part of the canonical algorithm defined in:
- `tools/checkpoint_index_lib.py`

## 4) State machine linkage
`checkpoint_state.json` MUST list the required checkpoint_outputs artifacts under the corresponding checkpoint's `artifacts` array.

Specifically:
- CP1 artifacts must list:
  - `checkpoint_outputs/cp1_extract_clean_input.stdout.txt`
  - `checkpoint_outputs/cp1_extract_clean_input.stderr.txt`
  - `checkpoint_outputs/index.txt`
- CP6 artifacts must list (when CP6 is completed):
  - the four CP6 log files above
  - `checkpoint_outputs/cp6_tool_fingerprint.json`
  - `checkpoint_outputs/index.txt`

## 5) Canonical vs derived
All `checkpoint_outputs/` artifacts are non-canonical:
- they exist for auditing, debugging, and approval evidence,
- they can be regenerated (except as evidence of a specific run),
- they must never be used as “teaching content” for excerpt synthesis.

