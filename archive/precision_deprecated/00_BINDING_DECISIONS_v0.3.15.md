# 00_BINDING_DECISIONS_v0.3.15

> **DEPRECATED (superseded):** Use `00_BINDING_DECISIONS_v0.3.16.md`.


This file is **binding**. It exists to prevent ambiguity when older narrative drafts conflict with the gold standard schema/glossary/checklists/protocol.

This version **supersedes**: `00_BINDING_DECISIONS_v0.3.13.md`.

## 1) Document precedence (source-of-truth order)
When documents disagree, use this order (highest wins):
1. This file: `00_BINDING_DECISIONS_v0.3.15.md`
2. Schema: `schemas/gold_standard_schema_v0.3.3.json` (structure, canonical) + this binding file (semantic clarifications)
   - Baseline packages may carry a snapshot copy for reproducibility; if any snapshot differs from `ABD/schemas/`, treat the canonical schema as authoritative.
3. Glossary: `project_glossary.md` (canonical)
4. Checklists: `2_atoms_and_excerpts/checklists_v0.4.md` (canonical)
   - Baseline packages may carry older checklist snapshots; the canonical checklist is the reference for interpreting checklist IDs.
5. Gold extraction protocol: `2_atoms_and_excerpts/extraction_protocol_v2.4.md` (canonical)
6. Gold baselines (e.g., Passage baselines)
7. Historical narrative drafts / legacy baselines (in `_ARCHIVE/`)

**Canonical file locations:** When a filename exists in multiple places (e.g., inside a baseline package), treat the repo-level canonical paths above as authoritative. Baseline copies are reproducibility snapshots and MUST NOT silently diverge.

## 2) Canonical data vs derived views (JSONL is source-of-truth)
**Canonical (authoritative) persisted outputs are structured data only:**
- `*_atoms_*.jsonl` (atoms)
- `*_excerpts_*.jsonl` (excerpt + exclusion records)
- `taxonomy_changes.jsonl` (cumulative)
- `*_metadata.json` + `baseline_manifest.json`
- taxonomy YAML

**Markdown is a derived review artifact (never canonical):**
- Any excerpt `.md` is a *deterministic rendering* of canonical JSONL.
- `.md` files must be **regeneratable** from JSONL (no hand edits).
- Human approval gates may read `.md` views, but approvals MUST write back to JSONL (or produce a structured patch that updates JSONL).

## 3) Checkpoint-1 intermediate artifacts are required
The 6-checkpoint pipeline includes a mandatory intermediate state:
- `passageX_clean_matn_input.txt`
- `passageX_clean_fn_input.txt` (may be empty, but must exist)
- `passageX_source_slice.json`

These represent the **clean extracted text** (post-normalization, pre-atomization) and the **provenance** of the slice inside the source HTML.

### 3.1 Source locator contract (v0.1)
`passageX_source_slice.json` is a **source locator** object and MUST validate against:
- `schemas/source_locator_schema_v0.1.json` (baseline-local copy)

The authoritative specification is:
- `spec/source_locator_contract_v0.1.md`

Gold baselines may temporarily reconstruct CP1 artifacts for older passages, but MUST mark that explicitly inside the locator `notes` field.

## 3.2 Checkpoint state machine artifact is required
Each baseline package MUST include `checkpoint_state.json` at the baseline root.

Purpose:
- Make the 6-checkpoint pipeline **operationally explicit** (approval gates, reruns, and automation).
- Remove ambiguity for future AI builders about what artifacts exist at each checkpoint.

Requirements:
- `checkpoint_state.json` MUST validate against baseline-local `schemas/checkpoint_state_schema_v0.1.json`.
- It MUST list required artifacts for each checkpoint and accurately reflect `checkpoint_last_completed`.
- `integrity.baseline_manifest_sha256` MUST equal the sha256 of `baseline_manifest.json`.

The authoritative pipeline runner that maintains this file is:
- `tools/pipeline_gold.py`



## 3.3 Checkpoint outputs capture is required
Each baseline package MUST include `checkpoint_outputs/` and capture stdout/stderr for key steps.

Required files:
- CP1: `checkpoint_outputs/cp1_extract_clean_input.stdout.txt`, `checkpoint_outputs/cp1_extract_clean_input.stderr.txt`
- CP6: `checkpoint_outputs/cp6_validate.stdout.txt`, `checkpoint_outputs/cp6_validate.stderr.txt`, `checkpoint_outputs/cp6_render_md.stdout.txt`, `checkpoint_outputs/cp6_render_md.stderr.txt`
- CP1+: `checkpoint_outputs/index.txt` (deterministic derived index; must not be hand-edited; validator enforces exact match)

These files MUST be listed in `checkpoint_state.json` under the corresponding checkpoint's `artifacts`.

Authoritative specification:
- `spec/checkpoint_outputs_contract_v0.3.md`

The pipeline runner that maintains these capture files is:
- `tools/pipeline_gold.py` (v0.2+)

## 4) Excerpt self-containment
- Each excerpt must be **independently understandable**:
  - no cut-off sentences,
  - no dangling referents when avoidable,
  - no "as mentioned earlier" without an explicit cross-excerpt relation.
- If an excerpt depends on other locations in the book, the system must store explicit **relations** to relevant excerpt(s) so downstream synthesis can follow the chain.



### 4.2 Excerpt titles (human label + source-anchored disambiguator)

**Why this exists:** `excerpt_id` is machine-unique but not human-readable. When multiple excerpts live under the **same** `taxonomy_node_id` (common: overview + summary; matn + footnote explanation; exercise set + items + answers), reviewers and future automation need a stable **display name** that also remains unique.

**Canonical fields (schema v0.3.3+):**
- `excerpt_title` — required human-readable label
- `excerpt_title_reason` — short justification of the construction (training signal)

**Binding naming rule (must be followed in all new gold baselines):**
1) **Base label:** derived from the last segment of `taxonomy_path` (i.e., the Arabic leaf title). If multiple excerpts under the same node share the same base label, add a short functional qualifier such as:
   - `تعداد الشروط` / `ملخص القول`
   - `حاشية` / `نقل مصدر` / `تعليل`
   - `تطبيق: مجموعة السؤال` / `تطبيق 1` / `جواب تطبيق 3`
2) **Source-anchored disambiguator:** append a parenthetical that contains, at minimum:
   - printed page range (from `page_hint` across the excerpt's atoms),
   - `source_layer` (e.g., `matn`, `footnote`),
   - and a stable core-atom span or list (e.g., `000022–000040` or `000029+000032`).

**Recommended canonical format:**
- `<base label>: <qualifier> (ص ٢٠–٢١؛ footnote 000006–000010)`
- `<base label> (ص ١٩؛ matn 000004–000008)`

**Non-goals:**
- `excerpt_title` is **not** an ontology and must not replace taxonomy. It is an audit/readability label.
- Do not encode long quotations inside the title; keep it concise.


### 4.3 Source anomaly flags (machine-readable `content_anomalies`)

**Why this exists:** sometimes the source itself is inconsistent (summary vs enumeration mismatch, typo, contradictory labels). We must preserve **source sovereignty** while also giving downstream synthesis a deterministic, structured warning.

**Canonical field (schema v0.3.3+):**
- `content_anomalies`: optional list of anomaly objects on an excerpt record.

**Anomaly object shape (binding semantics):**
- `type`: controlled token (recommended examples: `summary_mismatch`, `source_typo`, `author_contradiction`, `editorial_inconsistency`).
- `details`: concise description of the anomaly.
- `evidence_atom_ids`: list of atom IDs in this passage that directly evidence the anomaly.
- `evidence_excerpt_ids` (optional): anchor excerpt IDs when the anomaly spans excerpts.
- `synthesis_instruction` (optional): explicit instruction for downstream synthesis.

**Binding rules:**
1) `content_anomalies` must **never** “repair” the source. It is a warning/annotation only.
2) `evidence_atom_ids` must be sufficient to verify the anomaly without external context.
3) When an anomaly is crucial for avoiding incorrect ontology growth (e.g., summary-only mentions), include a `synthesis_instruction`.

## 5) Headings are metadata-only (NO heading atoms inside excerpts)
- Heading atoms are **structural metadata** and must **never** appear in excerpts:
  - never in `core_atoms`
  - never in `context_atoms`
- Headings are always excluded with exclusion reason `heading_structural` and referenced only via `heading_path`.

## 6) Placement convention for general/branch-level content
- Parent-level / branch-intro / general content must be placed at the branch's `__overview` leaf.
- If the appropriate `__overview` leaf does not exist, it must be created via **taxonomy_change** (review-gated).

## 7) Granularity rule (semantic granulation, not author packaging)
- Excerpt boundaries follow **semantic granularity**, even when the author packages items together.
- Example: `تعريف ... لغة` and `تعريف ... اصطلاحا` are two distinct subtopics → two distinct excerpts and (typically) two distinct taxonomy leaves.

## 8) Topic scope guard (dependency-aware, synthesis-safe)
**Baseline invariant:** each excerpt is anchored to **one** target topic (its `taxonomy_node_id`).

However, real texts often include small amounts of material about other topics. The system MUST treat this strictly and consistently, because it affects both (a) excerpt boundaries and (b) what the synthesis LLM should treat as authoritative for the node.

### 8.1 Three categories of "other-topic" material
When atoms inside an excerpt contain content about a different topic **Y** while the excerpt's node is **X**, classify that Y-content into exactly one of these categories:

**(A) Incidental mention / bridge (allowed, non-teaching).**
- The text merely *mentions* Y, uses Y as an example label, or provides a transition.
- It does **not** teach anything meaningful about Y on its own.
- This may remain in the excerpt without special handling.

**(B) Supportive dependency mini-background (allowed, but MUST be context).**
- The text gives a *brief reminder* / *micro-definition* / *minimal prerequisite* about Y that is needed to understand X at this point.
- It is **subordinate** to X (serves X's argument, not its own).
- It is **bounded** (small and local); if it grows, it becomes category (C).
- **Placement rule:** such atoms MUST be placed in `context_atoms` (not `core_atoms`) so the synthesis LLM treats them as framing, not as authoritative content for node X.
  - Use `role=preceding_setup` for same-science prerequisites.
  - Use `role=cross_science_background` only when Y belongs to another science.

**(C) Sovereign teaching of another topic (NOT allowed in a single-topic excerpt).**
- The Y-content becomes a meaningful teaching unit about Y: new definition/rule/breakdown/dispute/evidence *about Y* that could reasonably stand as its own excerpt.
- This MUST trigger an excerpt boundary: split into a separate excerpt placed at Y's node.
- If the text is genuinely inseparable at atom boundaries (rare), use `B3_interwoven` with a shared `interwoven_group_id` and `interwoven_sibling` relations.

### 8.2 The dependency test (decision procedure)
To decide between (B) and (C), apply the **Dependency Test**:
1) If the Y-content is removed, does the X-discussion become materially unclear or logically broken?
2) Could a reader learn something meaningful about Y from that Y-content alone?

Interpretation:
- If (1) = no → category (A) (incidental).
- If (1) = yes AND (2) = no → category (B) (supportive dependency background) → keep, but as context.
- If (2) = yes (regardless of (1)) → category (C) (sovereign teaching) → split (or interwoven).

### 8.3 Boundedness guardrail (strict)
Category (B) is allowed only when it remains *small*. The system MUST enforce one of:
- Keep it within **at most 2** prose-sentence atoms (or 1 bonded_cluster) by default, OR
- If it exceeds that, explicitly justify the exception in `boundary_reasoning` under a dedicated line:
  - `SUPPORTIVE_DEPENDENCY_EXCEPTION: <why boundedness was still satisfied>`

### 8.4 Taxonomy-change guard
Category (B) supportive dependency material MUST NOT by itself justify:
- creating a new taxonomy node,
- granulating a leaf,
- renaming/moving a node.

Taxonomy changes are justified only by **core teaching** about a topic (or by a dedicated excerpt whose core teaching is about that topic).


### 8.5 Supportive Dependency Review Block (mandatory when category B is used)
When category **(B) Supportive dependency mini-background** is invoked in an excerpt, the excerpt's `boundary_reasoning` MUST include a machine-readable block named `SUPPORTIVE_DEPENDENCIES:`.

Purpose:
- Make category-(B) usage reviewable and consistent.
- Allow future automation to parse and enforce the dependency test and boundedness constraints.
- Prevent the downstream synthesis LLM from treating prerequisite mini-background as authoritative node teaching.

**Rule:** Every supportive dependency entry MUST correspond to atoms placed in `context_atoms` (never `core_atoms`).

**Template (copy-paste, fill values):**

```yaml
SUPPORTIVE_DEPENDENCIES:
  - other_topic_hint: "<short label for topic Y>"
    other_topic_expected_node_id: "<optional taxonomy leaf id for Y if it ever becomes sovereign>"  # or "" if unknown
    atoms: ["<atom_id>", "<atom_id>"]
    dependency_test:
      removal_breaks_X: true
      teaches_Y: false
    why_needed: "<1–3 sentences: why this mini-background is necessary to understand X here>"
    boundedness:
      within_default: true
      exception: ""  # required non-empty iff within_default=false
    handling:
      placement: "context_atoms"
      context_roles: ["preceding_setup"]  # or ["cross_science_background"]
    links:
      related_excerpt_id: ""  # optional: if a dedicated excerpt about Y already exists
      relation_type_if_linked: ""  # optional
```

**Mandatory field semantics:**
- `dependency_test.removal_breaks_X` answers: If the Y-atoms are removed, does the X-discussion become materially unclear or logically broken?
- `dependency_test.teaches_Y` MUST be `false` for category (B). If it is `true`, the content is category (C) and MUST be split (or treated as B3_interwoven if inseparable).
- `boundedness.within_default` is `true` only if the supportive dependency stays within the default bound: at most **2 prose_sentence** atoms or **1 bonded_cluster**.
  - If `within_default=false`, `boundedness.exception` MUST be non-empty and the excerpt MUST also include the summary line `SUPPORTIVE_DEPENDENCY_EXCEPTION: ...` for fast human scanning.
- `handling.context_roles` MUST be `preceding_setup` for same-science prerequisites, and `cross_science_background` only when the prerequisite topic belongs to another science.

**Multiple supportive dependencies:** Use multiple list entries under `SUPPORTIVE_DEPENDENCIES:`.


### 8.6 Cross-science excerpt flags (excerpt-level; distinct from context roles)

**What this is:** `cross_science_context` is an excerpt-level label stating that the excerpt **uses technical concepts** from another linguistic science (صرف/نحو/عروض/لغة) as part of its teaching about the current node.

It is **distinct** from the context-atom role `cross_science_background`:
- `cross_science_background` is used when specific prerequisite atoms about another science are placed in `context_atoms`.
- `cross_science_context` is used whenever the excerpt **depends on**, **invokes**, or **explains** another science’s technical content — regardless of whether that content is in core or context.

**Threshold rule (set `cross_science_context=true` when ANY applies):**
1) The excerpt contains an explicit technical claim, rule, or analysis from another science (e.g., صرف: وزن/صيغة/مادة/اشتقاق; نحو: إعراب/عامل/تقدير; عروض: زحاف/علّة; لغة: اشتراك/ترادف/نقل لغوي) that functions as a premise/explanation for the current topic.
2) A reader would reasonably need at least minimal competence in that other science to fully interpret the author’s reasoning here (even if the other-science material is subordinate to the current node).

**Do NOT set it when:**
- another science is only mentioned by name,
- it appears only in a scholar’s epithet/title (e.g., “النحوي”),
- the text uses a casual label with no technical content.

**Required accompanying fields (binding):**
- When `cross_science_context=true`, `related_science` MUST be set (one of `sarf`, `nahw`, `3arud`, `lughah`, `other`).
- `rhetorical_treatment_of_cross_science` is meaningful only when `cross_science_context=true` and MUST NOT be true when `cross_science_context=false`.
- When `cross_science_context=true`, `case_types` MUST include `D4_cross_science` (training label consistency).

**Practical alignment with Topic Scope Guard (§8.1):**
- If the other-science material is category-(B) supportive dependency, place the prerequisite atoms in `context_atoms` with role `cross_science_background` **and** keep `cross_science_context=true`.
- If the other-science material becomes sovereign teaching about that other science, split into its own excerpt at the other science’s node (or use `B3_interwoven` if inseparable).

**Worked examples (Jawahir Passage 1):**
- `jawahir:exc:000008` — mentions “موافقتها للقواعد الصرفية” and “تسلم مادتها وصيغتها” (صرف prerequisite).
- `jawahir:exc:000011` — explanation of the morphological pattern “فعّل” (صرف premise for البلاغة discussion).
- `jawahir:exc:000006` / `jawahir:exc:000012` — مخالفة القياس with explicit صرف framing (already labeled).


## 9) Split discussions (resumes later)
When the same topic resumes later in the book:
- create **multiple excerpts** at the same leaf,
- connect them via `relations` of type `split_continues_in` / `split_continued_from`,
- do not merge separated spans into one excerpt.

**Authoritative rule:** split continuity is encoded in `relations`. The `split_discussion` object is allowed only as a redundant mirror and MUST match the `relations` split pointers exactly.

## 10) Core atom duplication policy (controlled, explicit exceptions)
**Default invariant:** a non-heading atom may be **core** in **at most one** excerpt.

**Allowed exceptions (must be intentional, not accidental):**

### 10.1 Interwoven multi-topic content (B3_interwoven)
Core atom duplication is allowed only when:
- every excerpt that uses the duplicated atom has the **same non-null** `interwoven_group_id`,
- every excerpt in that group includes `case_types` containing `B3_interwoven`,
- the group is explicitly linked via `relations` of type `interwoven_sibling` (the group must be connected),
- for any duplicated atom_id, its **core role is identical** in all excerpts where it appears,
- the duplicated atom_id does **not** appear as core outside that interwoven group.

### 10.2 Shared evidence (shared_shahid)
Core atom duplication is allowed for **evidence atoms only** when:
- the duplicated atom's core role is `evidence` in all excerpts where it appears,
- those excerpts are explicitly linked via `relations` of type `shared_shahid` (connected component),
- the duplicated atom_id does **not** appear as core in unrelated excerpts.

**Note:** Context atoms may be reused freely across excerpts; this policy governs core duplication only.

## 11) Taxonomy change log scope
Within any baseline package, `taxonomy_changes.jsonl` is **cumulative** up to the package's taxonomy version (not a per-passage delta).

**Governance (human approval gate):**
- A `taxonomy_change` record is a **proposal** until a human reviewer approves it.
- Do NOT update the taxonomy YAML in-place without explicit approval.
- During gold-standard work, approval is recorded out-of-band (review notes / PR / signed-off checklist), but the change itself remains represented as a structured `taxonomy_change` entry.

## 12) Taxonomy strictness
- A taxonomy node is a leaf **only** when `leaf: true` is explicitly present.
- Leaf nodes must not have children.
- Non-leaf nodes must have children.

## 13) Relation target integrity
If a relation has a non-null `target_excerpt_id`, that target excerpt must exist **in the available excerpt-id universe**. In a single-passage package, targets may legitimately refer to earlier passages (cross-passage within the same book). Therefore:
- When validating a single passage in isolation, missing `target_excerpt_id` values are **warnings** only if validation is run with `--allow-external-relations`.
- In strict mode (default), missing targets are errors and must be fixed.

Use `target_hint` only when `target_excerpt_id` is null.

## 14) Gold baseline uniformity (no legacy exceptions)
Gold baselines are **spec-by-example** for the future extraction application. Therefore:
- All active gold baselines MUST pass validator checks **without** `--skip-traceability`.
- Older baselines may exist only in `_ARCHIVE/` and MUST NOT be treated as authoritative.

## 15) Registries are authoritative for scale
As the project scales across many books/sciences, identity must be centralized:
- `books/books_registry.yaml` is authoritative for `book_id` metadata and source file locations.
- `taxonomy/taxonomy_registry.yaml` is authoritative for taxonomy versions and canonical file paths.

## 16) Baseline immutability (active gold is append-only)
Active gold baselines are the project's **spec-by-example** contract. Therefore:
- Any baseline directory referenced by an `ACTIVE_GOLD.md` file is **immutable** once it has passed CP6.
- If any artifact inside such a baseline needs to change (data, metadata, logs, manifests, documentation, or packaging artifacts), you MUST create a **new baseline directory** with a bumped `passageX_v.../` version and move the prior version under `_ARCHIVE/`.
- The only permitted operation on an active baseline is **reading** it (review / synthesis / regression tests).

Rationale (binding): prevents audit drift and guarantees that the file set a future AI software builder sees is exactly what was approved.

## 17) CP6 tool fingerprint is required (audit-grade reproducibility)
When `checkpoint_last_completed >= 6`, the baseline package MUST include:
- `checkpoint_outputs/cp6_tool_fingerprint.json`

This file is a machine-readable fingerprint of:
- the canonical tools used at CP6 (at minimum: `tools/validate_gold.py`, `tools/pipeline_gold.py`, `tools/checkpoint_index_lib.py`, `tools/render_excerpts_md.py`, `tools/build_baseline_manifest.py`),
- the exact validation command executed,
- the baseline directory name and passage_id,
- sha256 of key baseline artifacts (at minimum: atoms JSONL, excerpts JSONL, decisions JSONL, taxonomy YAML, taxonomy_changes.jsonl).

The validator enforces presence of this artifact once CP6 is marked complete.
