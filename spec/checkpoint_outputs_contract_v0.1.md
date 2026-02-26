# Checkpoint Outputs Contract v0.1

This specification defines the **standardized capture** of stdout/stderr for key pipeline steps.

Goal:
- Make the 6-checkpoint pipeline **reproducible and auditable**.
- Ensure human approval gates and AI builders can review *exactly what ran*, *what it printed*, and *what errors occurred*.

## 1) Directory
Each baseline directory MUST contain:
- `checkpoint_outputs/`

This directory is **non-canonical content** (it is a captured execution artifact), but it is a **required gold baseline artifact**.

## 2) Required files
When Checkpoint 1 is completed (CP1), the following files MUST exist:
- `checkpoint_outputs/cp1_extract_clean_input.stdout.txt`
- `checkpoint_outputs/cp1_extract_clean_input.stderr.txt`

When Checkpoint 6 is completed (CP6), the following files MUST exist:
- `checkpoint_outputs/cp6_validate.stdout.txt`
- `checkpoint_outputs/cp6_validate.stderr.txt`
- `checkpoint_outputs/cp6_render_md.stdout.txt`
- `checkpoint_outputs/cp6_render_md.stderr.txt`

## 3) State machine linkage
`checkpoint_state.json` MUST list these files under the corresponding checkpoint's `artifacts` array.

## 4) Canonical vs derived
These files capture execution output only and **must not** be treated as canonical content.
They exist purely for:
- auditing,
- debugging,
- reproducibility,
- evidence for human approval.
