# Stage 4: Excerpting — Specification

**Status:** Draft — rules are the most mature of all stages (extensive manual workflow precision), automation layer underspecified
**Precision level:** High for rules, Low for LLM automation
**Dependencies:** Stage 3 (Atomization) must be complete for the target passage.

---

## 1. Purpose

Group atoms into **excerpts** — coherent teaching or exercise units that each teach exactly one topic. Assign each excerpt to a taxonomy node and a science. Build relations between excerpts.

This is the most complex stage. It makes the highest-stakes decisions in the pipeline: what is being taught, where it belongs in the knowledge tree, and how it connects to other knowledge.

---

## 2. Inherited Precision

This stage inherits the richest body of precision rules:

| Rule set | Source document | Checklist IDs |
|----------|----------------|---------------|
| Core vs context assignment | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §8 | EXC.C.1 – EXC.C.4 |
| Excerpt boundary rules | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §8 | EXC.B.1 – EXC.B.6 |
| Layer isolation | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §8 | EXC.L.1 – EXC.L.3 |
| Exercise structure | `2_atoms_and_excerpts/checklists_v0.4.md` | EXC.X.1 – EXC.X.4 |
| Topic scope guard | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §8 | — |
| Dependency test | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §8.2 | — |
| Boundedness guardrail | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §8.3 | — |
| Interwoven content | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §10 | — |
| Shared evidence | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §10.2 | — |
| Placement rules | `2_atoms_and_excerpts/checklists_v0.4.md` | PLACE.P.1 – PLACE.P.6 |
| Cross-science flags | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §8.6 | PLACE.X.1 – PLACE.X.4 |
| Relation rules | `2_atoms_and_excerpts/checklists_v0.4.md` | REL.R.1 – REL.R.6 |
| Excerpt titles | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §4.2 | — |
| Content anomalies | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §4.3 | — |
| Excerpt self-containment | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §4 | — |

**These rules are NOT restated here.** This spec defines how the app executes them.

---

## 3. The Multi-Topic Excerpt Problem

This is the single most nuanced aspect of the entire pipeline. The user flagged it explicitly: "An excerpt may talk about 2 topics... this does not blindly mean anything." The rules for handling this are in Binding Decisions §8 (Topic Scope Guard) and §10 (Core Duplication Policy), but they deserve a precise operational summary here.

### 3.1 The situation

A group of atoms is being assembled into an excerpt for taxonomy node X. Some atoms within this group reference topic Y (a different node, possibly in a different science).

### 3.2 The three categories (from BD §8.1)

| Category | Name | Definition | Action |
|----------|------|------------|--------|
| **A** | Incidental mention | Topic Y is mentioned in passing (e.g., "unlike in بلاغة where..."). Removing it would not affect the teaching of topic X. | **Keep as-is.** The atom stays in the excerpt, assigned role `core`. No special handling needed. |
| **B** | Supportive dependency | Topic Y content is necessary for understanding topic X. The author explains Y because X requires it. These atoms are NOT independently teaching Y — they serve X. | **Keep, but mark role as `context`.** These atoms get `role: context` and `context_justification` explaining the dependency. Supportive Dependency Review Block (BD §8.5) is mandatory. |
| **C** | Sovereign teaching | The author has shifted to independently teaching topic Y. These atoms constitute a self-contained lesson on Y that doesn't serve X — it's a new topic. | **Split.** These atoms become a separate excerpt placed at node Y. The boundary between X's excerpt and Y's excerpt is drawn where the sovereign teaching begins. |

### 3.3 The dependency test (from BD §8.2)

To distinguish B from C, ask: **"If I removed this content, would the excerpt at node X still be complete and coherent?"**

- **If yes → Category A** (incidental, just drop or keep as-is)
- **If no, AND the content is bounded (doesn't sprawl) → Category B** (supportive dependency)
- **If no, AND the content is unbounded / self-contained → Category C** (sovereign teaching)

### 3.4 The boundedness guardrail (from BD §8.3)

Category B (supportive dependency) must be **bounded**: the Y-content must be a clearly delimited excursion, not an open-ended exploration. Signals that it's bounded:
- Short (1–3 atoms typically)
- The author explicitly returns to topic X after the excursion
- The Y-content is definitional or reference-like, not full teaching

If the Y-content exceeds 5 atoms or the author doesn't return to X, reclassify as C (sovereign teaching → split).

### 3.5 Interwoven content (from BD §10.1)

When X and Y content is so thoroughly mixed that splitting would destroy both:
- The excerpt is placed at node X (primary topic)
- The ENTIRE excerpt is **duplicated** at node Y with `interwoven_group_id` linking the copies
- Both copies are identical in content
- Each copy has its own `placed_at` pointing to its respective node
- The `B3_interwoven` flag is set

**This is a last resort.** It requires that:
1. Splitting was genuinely attempted and would result in incoherent fragments
2. Both topics are substantively taught (not just one mentioned in passing)
3. The interwoven teaching spans more than 3 atoms for each topic

### 3.6 Science classification per excerpt

Every excerpt is independently classified:

| Field | Type | Description |
|-------|------|-------------|
| `science_classification` | enum | `balagha`, `sarf`, `nahw`, `imlaa`, `unrelated` |
| `science_classification_reasoning` | string | Brief explanation of why this science was assigned |
| `science_classification_confidence` | float | 0.0–1.0 |

**The book's declared science is a routing hint, not a constraint.** A صرف book may contain نحو excerpts. Those excerpts go into the نحو taxonomy.

An excerpt classified as `unrelated` (outside all four sciences) is preserved in a holding area, not discarded.

---

## 4. Processing Model

Excerpting is **per-passage, sequential, multi-turn**.

For each passage with completed atomization:

### 4.1 CP3: Initial Excerpting

**Method:** LLM-driven
**Input:** Atom list, passage context, taxonomy tree for expected science(s), gold few-shot examples
**Action:** The LLM groups atoms into excerpts, assigns roles, places in taxonomy, classifies science.

**LLM must decide for each excerpt:**
1. Which atoms belong to this excerpt
2. Role of each atom: `core` or `context`
3. If `context`: the `context_justification` (why this atom is needed for the core topic)
4. Excerpt title (human label + source-anchored disambiguator, per BD §4.2)
5. Excerpt type: `teaching` or `exercise`
6. Taxonomy placement: which leaf node
7. Science classification
8. Content anomalies (if any, per BD §4.3)

### 4.2 CP4: Relations

**Method:** LLM-driven
**Input:** All excerpts from this passage + excerpts from previously processed passages
**Action:** The LLM identifies relations between excerpts.

**Relation types (from REL.R):**
- `prerequisite`: Excerpt A must be understood before excerpt B
- `builds_on`: Excerpt B extends or deepens excerpt A
- `contrasts`: Excerpts present opposing or contrasting concepts
- `exemplifies`: One excerpt provides examples for another's theory
- `cross_reference`: Explicit author cross-reference ("as we mentioned in باب...")

### 4.3 CP5: Validation

**Method:** Deterministic schema validation + LLM Judge (validation layer)
**Checks:**
- Every atom in the passage is assigned to exactly one excerpt (no orphan atoms, no double-assignment — except B3_interwoven)
- Excerpt boundaries don't violate bond groups
- Taxonomy placement points to a valid leaf node
- Science classification is one of the five valid values
- Relation targets exist
- Schema compliance

### 4.4 CP6: Packaging

**Method:** Deterministic
**Output:** Final excerpt files, rendered Markdown views, manifest.

---

## 5. Output Artifacts

### 5.1 Per-passage outputs

| File | Description |
|------|-------------|
| `excerpts.jsonl` | One excerpt per line, full schema |
| `relations.jsonl` | One relation per line |
| `excerpt_decisions.jsonl` | Decision log with checklist citations |
| `excerpt_report.json` | Stats: excerpt count by type, science distribution |
| `rendered_excerpts.md` | Human-readable Markdown view |

### 5.2 Excerpt schema (per `schemas/gold_standard_schema_v0.3.3.json`)

```json
{
  "excerpt_id": "EXC_001",
  "title": "تعريف الكلمة وتقسيمها — jawahir p.13",
  "type": "teaching",
  "atoms": [
    {"atom_id": "A003", "role": "core"},
    {"atom_id": "A004", "role": "core"},
    {"atom_id": "A005", "role": "context", "context_justification": "Defines prerequisite term (اسم) needed for the core definition"}
  ],
  "placed_at": "balagha/maani/khabar/haqiqat_al_khabar",
  "science_classification": "balagha",
  "science_classification_reasoning": "Excerpt defines a core بلاغة concept (الخبر) within علم المعاني",
  "science_classification_confidence": 0.95,
  "cross_science_context": null,
  "related_science": null,
  "content_anomalies": [],
  "interwoven_group_id": null
}
```

---

## 6. Open Questions (To Resolve During Zoom-In)

1. **Multi-turn strategy:** Should the LLM excerpt the entire passage in one call, or work excerpt-by-excerpt? One-shot risks quality; multi-turn risks inconsistency.
2. **Taxonomy awareness:** How much of the taxonomy tree does the LLM see? Full tree? Just the branch relevant to the book's science? All four sciences' trees?
3. **Cross-passage relations:** The LLM needs to see previous passages' excerpts to build cross-passage relations. How is this managed within context window limits?
4. **Science classification prompting:** Should classification be a separate LLM call after excerpting, or part of the same call? Separate call allows a "fresh eyes" review.
5. **Exercise detection:** How does the LLM distinguish exercise content from teaching content? In بلاغة, exercises are explicit (تطبيق sections). In صرف, they may be embedded (تمارين or inline).
6. **The "good to know" vs "sovereign teaching" judgment:** This is the hardest call in the pipeline. The LLM will need very precise prompting and multiple gold examples of each category. How many examples are enough?
