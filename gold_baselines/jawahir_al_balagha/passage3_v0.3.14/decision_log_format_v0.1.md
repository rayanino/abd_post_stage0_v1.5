# Decision Log Format — v0.1

**Purpose:** Machine-readable record of every placement decision and edge-case atomization decision, referencing checklist IDs from `checklists_v0.1.md`.

**File:** `{passage}_decisions.jsonl` — one JSON record per line (same JSONL convention as other data files).

**Validation:** `validate_gold.py` enforces:
1. Every excerpt_id in the excerpts file has exactly one decision record
2. All checklist IDs referenced exist in `checklists_v0.1.md`
3. All mandatory placement checklist items (PLACE.P1–P7) are present with boolean values
4. Required labeled blocks exist in the excerpt's `boundary_reasoning` field

---

## Record Types

### 1. Excerpt Decision Record (required for every excerpt)

```json
{
  "record_type": "excerpt_decision",
  "excerpt_id": "jawahir:exc:000021",
  "checklist_version": "checklists_v0.1",
  "placement_checklist": {
    "PLACE.P1": { "pass": true, "note": "Excerpt defines الخبر اصطلاحا; node ta3rif_alkhabar_istilah covers exactly this." },
    "PLACE.P2": { "pass": true, "note": "Node is leaf=true in balagha_v0_2." },
    "PLACE.P3": { "pass": true, "note": "Excerpt addresses the specific technical definition, not a general introduction." },
    "PLACE.P4": { "pass": true, "note": "Considered sidq_kadhib (too specific — that's a sub-topic discussed separately) and ta3rif_alkhabar (branch, not leaf)." },
    "PLACE.P5": { "pass": true, "note": "Existing leaf fits; no TC needed." },
    "PLACE.P6": { "pass": true, "note": "Single node assigned." },
    "PLACE.P7": { "pass": true, "note": "N/A — no new node created." },
    "PLACE.P8": { "pass": true, "note": "N/A — no taxonomy change triggered." }
  },
  "solidifying_indicators": ["PLACE.S1"],
  "alternatives_considered": [
    {
      "node_id": "sidq_kadhib",
      "rejection_reason": "صدق/كذب is a sub-topic within the definition but is treated separately by the author in later atoms."
    }
  ],
  "notes": ""
}
```

**Required fields:**
- `record_type`: always `"excerpt_decision"`
- `excerpt_id`: must match an excerpt in the excerpts JSONL
- `checklist_version`: version of the checklists file used
- `placement_checklist`: object with keys PLACE.P1 through PLACE.P8, each having `pass` (boolean) and `note` (string). All eight are mandatory.
- `solidifying_indicators`: array of PLACE.S* IDs that apply (may be empty)
- `alternatives_considered`: array of objects with `node_id` and `rejection_reason` (may be empty if placement is unambiguous)
- `notes`: free text for anything not captured above

### 2. Atom Decision Record (optional — only for edge cases)

Used for atoms where the decision required non-trivial judgment: bonded clusters, heading recognition ambiguity, quote-role ambiguity, merge-vs-split deliberation.

```json
{
  "record_type": "atom_decision",
  "atom_id": "jawahir:matn:000065",
  "decision_type": "bonded_cluster",
  "checklist_refs": ["ATOM.B1", "ATOM.A9"],
  "reasoning": "Two sentences merged: 'والفصاحة في اصطلاح...' + 'بحيث يكون...' — second sentence has no independent subject (refers back to الفصاحة via anaphoric pronoun). T1 applies. Conservative merge per ATOM.A9.",
  "alternatives_considered": "Keeping as two prose_sentence atoms was considered, but the second sentence begins 'بحيث' which is a dependent subordinator with no independent predication.",
  "notes": ""
}
```

**Required fields:**
- `record_type`: always `"atom_decision"`
- `atom_id`: must match an atom in the atom files
- `decision_type`: one of `"bonded_cluster"`, `"heading_recognition"`, `"quote_role"`, `"merge_vs_split"`, `"type_ambiguity"`, `"internal_tag"`, `"exclusion_edge_case"`
- `checklist_refs`: array of checklist IDs that were applied
- `reasoning`: detailed explanation of the decision
- `alternatives_considered`: what other option was evaluated and why rejected
- `notes`: free text

### 3. Structured boundary_reasoning Template

Every excerpt's `boundary_reasoning` field (in the excerpts JSONL, within the existing schema) must follow this labeled-block format:

```
GROUPING: These atoms form one teaching unit because [reason]. The author presents [topic] as a continuous discussion from atom X to atom Y.
BOUNDARY: Starts at atom X because [reason — e.g., first substantive atom after heading, explicit topic marker]. Ends before atom Z because [reason — e.g., new heading, topic transition, author's structural break].
ROLES: [For each non-trivial role assignment] Atom X has role=evidence because [it is a verse cited by the author as proof, not the author's own words]. Atom Y has role=author_prose because [it is the author's attribution formula introducing the verse].
PLACEMENT: Placed at node [node_id] because [subject alignment reasoning]. The excerpt teaches [specific topic] which matches the node's scope [node title].
CHECKLIST: PLACE.P1 ✓, PLACE.P2 ✓, PLACE.P3 ✓, PLACE.P4 ✓, PLACE.P5 ✓, PLACE.P6 ✓, PLACE.P7 ✓, PLACE.P8 ✓
ALTS: Considered [alternative_node] — rejected because [reason]. [Or: "No plausible alternative — unambiguous placement."]
```

**Validation:** The validator checks (via regex) that all six labeled blocks (GROUPING, BOUNDARY, ROLES, PLACEMENT, CHECKLIST, ALTS) are present in the boundary_reasoning string.

### 4. Structured atomization_notes Template

Every atom's `atomization_notes` field must follow this format:

```
TYPE: [atom_type] — [reason for this type, e.g., "Terminal period ends sentence" or "H1+H2: short (12 chars), no verb, section keyword 'تعريف'"]. BOUNDARY: [why boundary is here — e.g., "Period after 'الحال'" or "Paragraph break in source"]. CHECKLIST: [comma-separated checklist IDs, e.g., "ATOM.A1, ATOM.A4"]. EDGE: [any edge case notes, or "None"].
```

For bonded clusters, add:
```
BOND: [trigger_id] — [concrete textual evidence, e.g., "Second sentence 'بحيث يكون' has no independent subject"]. CHECKLIST: ATOM.B1, ATOM.A9.
```

---

*Format version: 0.1 — Created for Passage 2. Will be revised after Passage 2 based on lessons learned.*
