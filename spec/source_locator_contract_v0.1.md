# ABD — Source Locator Contract (v0.1)

## Purpose

ABD must preserve **reproducible provenance** from extracted clean text, atoms, and excerpts back to the book’s **original source artifact** (typically a Shamela HTML export).

This contract defines a **source locator**: a machine-readable object that identifies *where* a passage’s Checkpoint‑1 clean input slice came from, using stable selectors that can survive downstream transformations.

The source locator is a critical architectural primitive for:

- deterministic re-extraction (given the same source artifact)
- auditability (human review gates)
- future tooling that maps atom/excerpt offsets back to the source

## Scope (v0.1)

v0.1 formalizes provenance for **Checkpoint‑1** only (the clean input slice). It does **not** yet require atom-level DOM mapping.

The CP1 locator is stored as `{passage_id}_source_slice.json` in each baseline.

## Non-negotiable invariants

1) **Deterministic selectors**
   - Selectors must be stable and re-playable (page markers, char offsets, anchors).
   - No non-deterministic fields are required (timestamps are optional and discouraged).

2) **Immutable source identity**
   - The locator MUST include `source_artifact.sha256` for the full source artifact file.

3) **Self-contained baseline execution**
   - The locator MUST include `source_artifact.baseline_relpath` so a validator can locate the source file when run from the baseline directory.

4) **Normalization linkage**
   - The locator MUST specify the normalization contract used to produce the clean input.

5) **Schema validation**
   - `{passage_id}_source_slice.json` MUST validate against `schemas/source_locator_schema_v0.1.json` (baseline-local copy).

## Required structure (high-level)

The locator is a JSON object with:

- `record_type = "source_locator"`
- `locator_version = "0.1"`
- identifiers: `book_id`, `passage_id`
- `source_artifact`: what file is being located
- `selectors`: one or more selector objects
- `normalization_contract`: what contract governed cleaning
- `extraction_tool`: tool name/version used to produce CP1 artifacts
- `outputs`: filenames for clean input artifacts (matn/fn)

## Selectors (v0.1)

The locator supports multiple selectors simultaneously; use as many as are available.

Recommended minimum for Shamela HTML:

- `shamela_page_marker_range` (page start/end using `(ص: N)` markers)
- `html_char_range` (character offsets in the raw HTML file)

If a book lacks page markers, use:

- `html_anchor_range` (start/end anchor ids), OR
- `dom_xpath_range` (start/end XPath), OR
- `html_char_range` alone (least robust)

## How this interacts with later stages

- Atoms/excerpts already carry **canonical text offsets** (`source_anchor`, `source_spans`).
- The CP1 source locator anchors those offsets to the original artifact.
- A future mapping layer may connect canonical offsets → clean input offsets → HTML offsets.

## Reference schema

See: `schemas/source_locator_schema_v0.1.json`
