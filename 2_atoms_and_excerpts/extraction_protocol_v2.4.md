# Arabic Book Digester — Gold Standard Extraction Protocol v2.4

> **This is a MANUAL gold-standard protocol** — the 6-checkpoint human+LLM interactive
> workflow used to create the بلاغة gold baselines (`gold_baselines/jawahir_al_balagha/`).
> It is NOT the operating procedure for the automated extraction tool (`tools/extract_passages.py`).
> For automated extraction, see `3_extraction/RUNBOOK.md`.

> **Provenance note (v2.4):** Promoted from v2 snapshot during repo structure consolidation. The v2 content was the operating procedure used for all three gold baselines; v2.4 updates only version references and file paths (zero semantic changes to the protocol).

**Canonical location:** `ABD/2_atoms_and_excerpts/extraction_protocol_v2.4.md`
This is the operating procedure for extracting gold standard passages. Read it at the start of every new extraction session.

**This document tells you WHAT TO DO (as a historical snapshot). For what things MEAN, read `project_glossary.md`. For what shape the data takes, read the canonical schema (`ABD/schemas/gold_standard_schema_v0.3.3.json`). For a worked example, read the active Passage 1 baseline.**

**Canonical output is JSONL.** Any excerpt `.md` is a deterministic, regeneratable *derived* view for human review.

**Executable contract:** the 6 checkpoints are also encoded as a runner in `ABD/tools/pipeline_gold.py`.
The repo-level canonical protocol remains normative; the runner is the machine-readable mirror.

**State machine artifact:** each baseline package MUST include `checkpoint_state.json` at the baseline root.
The pipeline runner updates it at every checkpoint (and validation enforces its integrity).

---

## 0. Session Startup

### What the user provides:
- The page range for the next passage (e.g., ص ٢٥–٣٢)
- The passage 1 baseline zip (or it's already in project files)
- The source book HTML (or it's already in project files)
- Any special instructions (e.g., "this section has شرح layer")

### What you do first (in order):
1. Read `project_glossary.md` — understand every term
2. Read the schema's `description` fields (skim definitions, read field descriptions for excerpt_record and atom_record thoroughly)
3. Unzip the latest baseline. Read at least 3 Passage 1 excerpts from the report: one teaching excerpt with context atoms, one exercise item, one footnote-layer excerpt
4. Read `passage1_lessons_learned.md` — internalize the error patterns
5. Read the previous passage's `metadata.json` → `continuation` block to get starting sequence numbers
6. Read this protocol fully

### Continuation state:
The previous passage's metadata.json contains:
```
continuation.next_matn_atom_seq       → your first matn atom sequence number
continuation.next_fn_atom_seq         → your first footnote atom sequence number  
continuation.next_excerpt_seq         → your first excerpt sequence number
continuation.next_taxonomy_change_seq → your first TC- number
continuation.current_taxonomy_version → taxonomy version to start from
```

For Passage 2 of جواهر البلاغة, these are: matn=60, fn=37, exc=21, TC=4, taxonomy=balagha_v0_2.

---

## 1. Input Preparation

Extract the Arabic text for the passage from the source HTML. Separate متن from footnotes *if possible*.

This checkpoint MUST emit the following artifacts (required, even if empty):
- `checkpoint_state.json` must exist already (CP0) and will be updated to mark CP1 done.
- `{passage}_clean_matn_input.txt`
- `{passage}_clean_fn_input.txt` *(may be empty, but must exist for uniformity)*
- `{passage}_source_slice.json` *(Checkpoint‑1 provenance as a **source locator**; must validate against `schemas/source_locator_schema_v0.1.json`)*

Preferred tool (when Shamela page markers exist as `(ص: N)`):
```bash
python tools/extract_clean_input.py --html <shamela_export.htm> --page-start <N> --page-end <M> \
  --out-matn {passage}_clean_matn_input.txt \
  --out-fn {passage}_clean_fn_input.txt \
  --out-slice {passage}_source_slice.json
```

### CP1 output capture (required)
The command execution output MUST be captured into:
- `checkpoint_outputs/cp1_extract_clean_input.stdout.txt`
- `checkpoint_outputs/cp1_extract_clean_input.stderr.txt`

These files MUST be listed in `checkpoint_state.json` under CP1 artifacts.

**Allowed transformations:** HTML tag stripping, whitespace normalization, footnote marker preservation (strip from text, record in metadata).

**Forbidden:** Spelling correction, diacritic changes, editorial insertions, reordering content.

Present the extracted text to the user for review before proceeding. The user confirms the slice is complete.

Important: CP1 clean inputs are **pre-atomization** and are **not expected** to match canonical layer texts later.
Canonical texts are built at Checkpoint 2 from atoms (and may exclude headings and non-teaching items).

**Checkpoint 1: User confirms clean text extraction.**

---

## 2. Atomization

Convert the clean text into atoms. This is the foundation — every downstream decision depends on it.

### Rules:
- **Sentence boundaries:** Terminal punctuation (`.` `؟` `?` `!`) and paragraph breaks end atoms. Commas (`,` `،`), semicolons (`;` `؛`), colons (`:`), and dashes do NOT.
- **Bonded clusters:** Merge when separating would make one sentence meaningless. Always provide trigger (T1–T6) and reason. Conservative rule: when unsure, merge.
- **Headings:** Short, no verb, no predication. Type=heading. Will be excluded but used in heading_path.
- **Verse evidence:** Poetry/Quran cited as evidence or example gets its own atom, even without surrounding punctuation.
- **Internal tags:** Quran/hadith/verse fragments embedded within prose get internal_tags on the prose atom, not separate atoms.
- **Footnote refs:** Record marker text (e.g., "(1)"), link to footnote atom IDs. Mark orphans explicitly.
- **Text is verbatim:** Copy exactly from the canonical source. Never correct, normalize, or edit.

### Atom ID assignment:
`{book_id}:{layer}:{6-digit sequence}` — continue from previous passage's last number.

### Output:
- `{passage}_matn_atoms_v02.jsonl` — one atom record per line
- `{passage}_fn_atoms_v02.jsonl` — one atom record per line (if footnotes exist)

Present atom counts and a sample of the first 5 and last 5 atoms to the user.

**Checkpoint 2: User reviews atoms. Check for missed sentence boundaries, incorrect merges, missing bonded clusters, verse atoms mistyped as prose.**

---

## 3. Canonical Text Construction

Build canonical text files by joining atom texts with newline separators:
```python
canonical = '\n'.join(atom['text'] for atom in atoms_in_order)
```

Compute source_anchor offsets: each atom's `char_offset_start` and `char_offset_end` are its position in this canonical text.

Verify the invariant: `atom['text'] == canonical[start:end]` for every atom.

### Output:
- `{passage}_matn_canonical.txt`
- `{passage}_fn_canonical.txt`

---

## 4. Excerpting

This is the critical step. Analyze the atom sequence to identify excerpts.

### For each excerpt, decide:

**A. What is the teaching unit?** Identify the contiguous (or non-contiguous) group of atoms that the author presents as one coherent discussion of one topic.

**B. Which taxonomy node?** Where does this belong in the tree? Check the current taxonomy. If no fitting node exists, prepare a taxonomy_change record (see §6).

**C. Core atoms + roles:** Every atom in the excerpt's discourse flow is core. Assign roles:
- `author_prose` — the author's own words (definitions, explanations, transitions, attribution formulas)
- `evidence` — material cited as proof (verses, hadith, prose quotations from other scholars). **The evidence rule: if someone else wrote it and the author is citing it, it's evidence. Always core, never context.**
- `exercise_content` — exercise items the reader must analyze
- `exercise_answer_content` — scholarly judgments identifying answers to exercises

**D. Context atoms + roles (synthesis-safe framing):** Context exists to make the excerpt understandable without polluting the node's authoritative content.

Assignment rule:
- If an atom teaches/proves something *about the excerpt's taxonomy node*, it is **core**.
- If an atom exists only to make that teaching understandable (setup, classification frame, back-reference, or brief supportive prerequisite mini-background about another topic), it is **context**.

Supportive dependency note: when a brief prerequisite reminder/definition about another topic is needed for comprehension, keep it **as context** (role=`preceding_setup` for same-science; role=`cross_science_background` for other-science). If it grows into meaningful teaching about that other topic, split it into its own excerpt.

Supportive dependency documentation requirement: whenever you keep category-(B) supportive dependency mini-background inside an excerpt, you MUST include the structured `SUPPORTIVE_DEPENDENCIES:` block inside `boundary_reasoning` (see Binding Decisions §8.5).

Validator note: `tools/validate_gold.py` (v0.3.9+) conditionally lints the `SUPPORTIVE_DEPENDENCIES:` block when present (YAML shape + consistency with `context_atoms`).
- `classification_frame` — a condition from an overview list
- `preceding_setup` — earlier text establishing the broader topic / brief prerequisite background needed for comprehension
- `back_reference` — author's reference to prior discussion
- `cross_science_background` — prerequisite from another science

**E. Source spans:** Record which canonical file, which char ranges, which atoms. Type each span as core or context.

**F. Relations:** Link to other excerpts (footnote_supports, has_overview, exercise_tests, belongs_to_exercise_set, answers_exercise_item, etc.).

**G. Boundary reasoning:** Write a clear explanation of why the excerpt starts and ends where it does. This is a training signal for the future extraction app.

**H. Case types:** Annotate which patterns appear (A1_pure_definition, B4_multipage_continuous, C1_scholarly_footnote, etc.). These are training labels.

### Exercise handling:
- Exercise set (framing prompt) → exercise_role=set
- Individual items → exercise_role=item, with belongs_to_exercise_set relation
- Answer footnotes → exercise_role=answer, with answers_exercise_item and belongs_to_exercise_set relations
- tests_nodes = all taxonomy nodes tested. primary_test_node = the most prominent one.

### Common errors to avoid (from Passage 1 lessons):
1. **Evidence misclassified as author_prose.** If the author is quoting someone else's words — whether verse, hadith, or prose — that's evidence, not author_prose. The form (verse vs prose) is irrelevant; the function (citation vs original) determines the role.
2. **Evidence placed in context.** Evidence is ALWAYS core. Context is for external orientation only.
3. **Wrong context is worse than missing context.** If unsure whether an atom should be context for this excerpt, leave it out. A missing context atom is recoverable; a wrong one creates false mental models.
4. **Footnote apparatus vs scholarly content.** Apply the dependency test: does the footnote merely gloss a word (→ exclude as footnote_apparatus), or does it provide substantive scholarly analysis (→ teaching or answer excerpt)?
5. **Overview duplication.** When the author enumerates conditions/categories, the enumeration itself is ONE excerpt at an __overview node. Don't duplicate it as context in every child excerpt.
6. **Source inconsistencies.** If the author contradicts himself (e.g., summary lists different items than the original), document with source_inconsistency internal_tag. Never silently correct.

### Output:
- `{passage}_excerpts_v02.jsonl` — excerpt and exclusion records, mixed

Present each excerpt to the user as you create it: show the taxonomy node, core atoms with roles, context atoms with roles, and boundary reasoning.

**Checkpoint 3: User reviews each excerpt. Verify taxonomy placement, role assignments, boundary decisions, and relation links.**

---

## 5. Exclusions

Every atom not used as core or context must be explicitly excluded. Common reasons:
- `heading_structural` — headings (also referenced in heading_path)
- `footnote_apparatus` — word glosses, إعراب, non-scholarly notes
- `khutba_devotional_apparatus` — opening prayers, بسملة, حمدلة
- `non_scholarly_apparatus` — non-teaching content

Present exclusion summary to user (grouped by reason).

**Checkpoint 4: User confirms no teaching content was accidentally excluded.**

---

## 6. Taxonomy Changes

If any excerpt requires a node that doesn't exist:
1. Create a taxonomy_change record (node_added, leaf_granulated, node_renamed, or node_moved)
2. Follow the taxonomy ID policy (ASCII lowercase + digits + underscores, Franco-Arabic transliteration)
3. Link the change to the triggering excerpt (bidirectional: excerpt.taxonomy_change_triggered ↔ change.triggered_by_excerpt_id)
4. Bump the taxonomy version

**Do NOT create nodes for topics only mentioned in passing.** A node is justified only when an excerpt substantively addresses that topic (dependency test).

### Output:
- Append to `taxonomy_changes.jsonl`
- Update taxonomy YAML file with new version

---

## 7. Validation

Run the validator. It must pass with zero errors before packaging.

```bash
python validate_gold.py \
  --atoms {passage}_matn_atoms_v02.jsonl {passage}_fn_atoms_v02.jsonl \
  --excerpts {passage}_excerpts_v02.jsonl \
  --schema gold_standard_schema_v0.3.3.json \
  --canonical matn:{passage}_matn_canonical.txt footnote:{passage}_fn_canonical.txt \
  --taxonomy-changes taxonomy_changes.jsonl \
  --taxonomy {taxonomy_version}.yaml
```

**Cross-passage relations:** If your passage contains relations that target excerpt_ids in earlier passages (not present in this folder), run validation with `--allow-external-relations` to treat missing targets as warnings in single-passage mode.

The validator checks structural invariants including: schema validation, offset audit, core-uniqueness (with controlled exceptions for interwoven_group_id + shared_shahid evidence), layer-token consistency (all 5 layers), heading dual-state, evidence-not-in-context, role allowlists, exercise set membership, coverage invariant, source spans, taxonomy change bidirectional links, taxonomy node existence, and strict leaf-node enforcement (leaf:true required for childless nodes).

If validation fails, fix the issue and re-run. Do not package until ALL CHECKS PASSED.

**Checkpoint 5: Validator passes with zero errors.**

---

## 8. Packaging

### Files to produce:

```
{passage}_matn_atoms_v02.jsonl
{passage}_fn_atoms_v02.jsonl          (if footnotes exist)
{passage}_excerpts_v02.jsonl
{passage}_matn_canonical.txt
{passage}_fn_canonical.txt            (if footnotes exist)
{passage}_metadata.json               (include continuation block!)
{passage}_lessons_learned.md          (new lessons from this passage)
{passage}_excerpting_report.txt       (generated by generate_report.py)
excerpts_rendered/                   (derived Markdown views; generated by tools/render_excerpts_md.py)
taxonomy_changes.jsonl                (append-only, includes all previous changes)
{taxonomy_version}.yaml               (current tree after this passage's changes)
gold_standard_schema_v0.3.3.json      (copy from baseline)
validate_gold.py                      (copy from baseline)
generate_report.py                    (copy from baseline)
project_glossary.md                   (copy from baseline or project files)
AUDIT_LOG.md                          (append this passage's entry)
baseline_manifest.json                (recomputed hashes)
README.md                             (passage-specific)
```

### Render Markdown excerpt views (derived)
Generate `.md` files for human approval. These are **non-canonical** outputs.

```bash
python3 tools/render_excerpts_md.py \
  --atoms {passage}_matn_atoms_v02.jsonl {passage}_fn_atoms_v02.jsonl \
  --excerpts {passage}_excerpts_v02.jsonl \
  --outdir excerpts_rendered
```

### Metadata must include:
- passage_id, book_id, book_title, author, page_range, topic
- schema_version, taxonomy_version, offset_unit, canonical_derivation
- canonical_files (filename, sha256, char_count, byte_count_utf8, atom_count per layer)
- totals (atoms, excerpts, exclusions, teaching_excerpts, exercise_excerpts)
- **continuation block** (next sequence numbers for the passage after this one)

### Generate report:
```bash
python generate_report.py \
  --atoms {passage}_matn_atoms_v02.jsonl {passage}_fn_atoms_v02.jsonl \
  --excerpts {passage}_excerpts_v02.jsonl \
  --metadata {passage}_metadata.json \
  --output {passage}_excerpting_report.txt
```

### Compute manifest:
SHA-256 for every file. Compute baseline_sha256 fingerprint. Update baseline_id to `{passage}_v0.3.3`.

### Final validation:
Re-run validator after packaging to confirm nothing was corrupted.

**Checkpoint 6: User receives the final package.**
CP6 execution output MUST be captured into:
- `checkpoint_outputs/cp6_validate.stdout.txt` / `checkpoint_outputs/cp6_validate.stderr.txt`
- `checkpoint_outputs/cp6_render_md.stdout.txt` / `checkpoint_outputs/cp6_render_md.stderr.txt`

These files MUST be listed in `checkpoint_state.json` under CP6 artifacts.


---

## 9. Lessons Learned

After each passage, write a lessons_learned file documenting:
- Every new edge case encountered
- Every decision that required deliberation
- Every pattern from Lesson 30's watch list that was encountered
- Any schema or vocabulary gaps discovered

These lessons feed into future protocol updates and eventually into the excerpt_definition revision.

---

## Quick Reference: The 6 Checkpoints

| # | When | What the user checks |
|---|------|---------------------|
| 1 | After text extraction | Clean text, correct layer separation |
| 2 | After atomization | Sentence boundaries, bonded clusters, atom types |
| 3 | During excerpting | Taxonomy placement, roles, boundaries, relations |
| 4 | After exclusions | No teaching content accidentally excluded |
| 5 | After validation | Validator passes with zero errors |
| 6 | After packaging | Package inventory + manifest + audit log are consistent |

---

*Protocol version: 2.4 — Aligned with gold standard schema v0.3.3 and project glossary v1.2.0. Replaces extraction_protocol v0.2.2.*