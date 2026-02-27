# ABD — Session Context (persistent, copy-paste for new sessions)

This document is the **one-stop context** for resuming work on the Arabic Book Digester (ABD) project in a fresh ChatGPT / AI-agent session.

It is written for two downstream consumers:
1) **AI software builder** (Claude Code / Devin / etc.) who will implement ABD.
2) **Synthesis LLM** (future, external) that will ingest ABD outputs (excerpts + metadata) and generate encyclopedic texts per taxonomy leaf.

---

## 1) Mission (what ABD must do)
ABD is an *intelligent Arabic book digester* for four Arabic-language sciences:
- الإملاء
- الصرف
- النحو
- البلاغة

Given a book (typically **Shamela HTML export**) belonging to one of these sciences, ABD must:
1) **Extract clean text** for a page range (Checkpoint 1 artifacts).
2) **Atomize** the source into a stable, auditable sequence of *atoms* (minimal units for excerpting, with offsets into canonical text).
3) **Excerpt** the book into *excerpts*, where each excerpt explains **exactly one maximally-granular subtopic** (a leaf-level subject).
4) **Place** each excerpt into **exactly one** leaf node in a **science taxonomy tree**.
5) **Evolve** the taxonomy (review-gated) via explicit `taxonomy_change` proposals when the book introduces a topic not represented in the current tree.

ABD is not the synthesizer: the future synthesis LLM consumes ABD outputs; ABD’s job is **maximally precise extraction + placement + traceability**.

---

## 2) Current gold focus
Gold-standard examples are currently being built using the البلاغة book:
- **جواهر البلاغة في المعاني والبيان والبديع** — أحمد الهاشمي

Active gold baselines (AUTHORITATIVE):
- Do **not** hard-code versions here.
- Always read the active set from:
  - `2_atoms_and_excerpts/1_jawahir_al_balagha/ACTIVE_GOLD.md`
  - (and any other `*/ACTIVE_GOLD.md` under `2_atoms_and_excerpts/` if additional books/sciences are added)

Gold baselines live in `gold_baselines/` (the ACTIVE_GOLD.md file indexes them).

Next planned baseline:
- Do **not** infer “what’s next” from this file.
- Use the current session instruction (or a dedicated `passage*_starting_prompt.md` in `2_atoms_and_excerpts/`) to determine the next target slice.

Long-term: produce at least one gold book per science (إملاء/صرف/نحو/بلاغة), each yielding multiple gold passages.

---

## 3) Core entities and their contracts

### 3.1 Checkpoint-1 clean input (required)
For every passage baseline, the pipeline MUST produce:
- `passageX_clean_matn_input.txt`
- `passageX_clean_fn_input.txt` (may be empty, but must exist)
- `passageX_source_slice.json` (provenance of the slice in the source HTML)
  - This file is a **source locator** object (see `spec/source_locator_contract_v0.1.md`).
- Execution capture artifacts are specified in `spec/checkpoint_outputs_contract_v0.2.md`.

These represent the **clean extracted text** (post-normalization, pre-atomization) and the **provenance** of the slice.

### 3.2 Atom
An **atom** is a smallest auditable unit used to build excerpts.
- Has stable `atom_id` (globally sequential per book + layer).
- Belongs to exactly one `source_layer` (e.g., `matn`, `footnote`).
- Has canonical offsets (`char_offset_start/end`) into the canonical text file.

### 3.3 Excerpt
An **excerpt** is a group of atoms that (together) teach **one** subtopic.
- Exactly one `taxonomy_node_id` (must be a leaf).
- Exactly one `source_layer`.
- `core_atoms`: atoms that carry the teaching/evidence; evidence is always core.
- `context_atoms`: optional, minimal external orientation only (no evidence).
- No heading atoms in excerpts (headings are metadata-only via `heading_path`).

### 3.4 Taxonomy
A **science taxonomy** is a tree of topics for that science.
- Excerpts must map to a leaf node.
- General/intro branch-level content must map to that branch’s `__overview` leaf.
- Tree changes must be proposed via `taxonomy_change` records (human-approved).

---

## 4) Binding precedence (source-of-truth order)
When documents conflict, follow this order:
1) `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` (BINDING) ✅
2) `schemas/gold_standard_schema_v0.3.3.json` (data contract) ✅
3) `project_glossary.md` ✅
4) `2_atoms_and_excerpts/checklists_v0.4.md` ✅
5) `2_atoms_and_excerpts/extraction_protocol_v2.4.md` ✅
6) Gold baselines (Passage packages) ✅
7) Historical narrative drafts / `precision/` (older versions) / `_ARCHIVE/` — **non-binding**

---

## 5) Non-negotiable rules (must be implemented + enforced)

### 5.1 Headings are metadata-only
- Heading atoms never appear in `core_atoms` or `context_atoms`.
- Headings are excluded with `heading_structural` and referenced via `heading_path`.

### 5.2 One excerpt → one leaf
Every excerpt maps to **exactly one** taxonomy leaf.

### 5.3 Semantic granularity
Excerpts follow semantic topics, not author packaging.
Example: `تعريف ... لغة` and `تعريف ... اصطلاحا` are normally **two** excerpts.

### 5.4 Topic scope guard (dependency-aware)
Within one excerpt at node X, material about another topic Y is handled strictly:
- incidental mention/bridge is allowed,
- supportive dependency mini-background is allowed only as **context** (synthesis-safe framing),
- sovereign teaching of Y triggers a boundary (split), unless text is genuinely inseparable → B3_interwoven.

### 5.5 Split discussions
If the same topic resumes later:
- create multiple excerpts at the same leaf
- connect via `relations`: `split_continues_in` / `split_continued_from`

**Authority:** split continuity lives in `relations`. `split_discussion` is allowed only as a redundant mirror and must match relations exactly.

### 5.6 Controlled core-duplication (Option A)
**Default:** a non-heading atom may be core in at most one excerpt.

**Allowed exceptions (intentional only):**
1) **Interwoven multi-topic content** (`interwoven_group_id` + `B3_interwoven` + `interwoven_sibling`).
2) **Shared evidence** (`shared_shahid`) for role=`evidence` only.

### 5.7 Taxonomy strictness
- Leaf is a leaf **only** if `leaf: true` is explicitly present.

---

### 5.8 Relation target integrity
- In strict mode, all non-null `target_excerpt_id` must exist.
- In single-passage validation mode, cross-passage targets are allowed as warnings using `--allow-external-relations`.

## 6) Runtime environment (tools + validation)

- **Python 3.11+** is required.
- Runtime deps are pinned in `requirements.txt`.
- See: `spec/runtime_contract_v0.1.md`.
- Verify setup:

```bash
python tools/check_env.py
```

CI (GitHub Actions): `.github/workflows/abd_validate.yml` runs `tools/check_env.py` + `tools/run_all_validations.py` on push/PR.

---

## 7) Registries (scale)
As the project grows, identity must be centralized:
- `books/books_registry.yaml` is authoritative for `book_id` metadata and input file locations.
- `taxonomy/taxonomy_registry.yaml` is authoritative for taxonomy versions and canonical file paths.

Baselines may ship local snapshots for reproducibility, but registries are the canonical indexes.

---

## 8) Tools (canonical vs baseline snapshots)
- `ABD/tools/` contains the **canonical latest** tools.
- Each baseline package includes a **snapshot** of the tools used to validate it.
- Baseline snapshots must not be edited after release; changes require a new baseline version.

---

## 9) Gold baseline workflow (6 checkpoints)
Gold baseline creation is governed by `2_atoms_and_excerpts/extraction_protocol_v2.4.md` and is operationalized by `tools/pipeline_gold.py`.

Checkpoints:
1) Page extraction → write clean inputs (`*_clean_*_input.txt`) + `*_source_slice.json`
2) Canonicalization + atomization (with offset audits)
3) Boundary/placement plan (decision scaffolding)
4) Final excerpts + exclusions (schema compliant)
5) Taxonomy change proposals (if needed)
6) Validation + packaging (manifest fingerprint + derived MD)

**State machine:** each baseline includes `checkpoint_state.json` (validated). The pipeline runner updates it to mark completed checkpoints.

---

## 10) Validation
Each baseline folder includes `validate_gold.py`.

Typical patterns:
- Active gold passages: validate in strict mode (no `--skip-traceability`) with a decisions file.
- If cross-passage relation targets exist: add `--allow-external-relations`.

`tools/run_all_validations.py` runs validation across all active gold baselines.

---

## 11) Locked decisions (do not reopen without explicit project change)

### 11.1 Gold baseline uniformity
Gold baselines are spec-by-example. Therefore:
- All active gold baselines MUST pass validation without `--skip-traceability`.
- Any older/legacy baseline must be archived under `_ARCHIVE/` and excluded from active gold.

### 11.2 Canonical JSONL vs derived Markdown
- Canonical persisted output is **JSONL + metadata + taxonomy YAML**.
- Markdown excerpt views are **derived** and must be deterministically regeneratable from JSONL.
- Human approval can happen on Markdown views, but approvals must write back to JSONL (or generate a structured patch).

### 11.3 Archive guard
Anything under `_ARCHIVE/` is non-authoritative.
Tools should refuse to run on `_ARCHIVE/` unless `--allow-archive` is explicitly supplied.
