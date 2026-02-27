# Stage 3: Atomization — Specification

> **SUPERSEDED:** This spec describes the manual atomization workflow. Atomization is now handled automatically by `tools/extract_passages.py` (Stage 3+4), which combines atomization + excerpting + taxonomy placement in one LLM pass. The rules below are implemented in the automated tool. Do not follow this spec manually.

**Status:** Superseded by automated extraction tool
**Precision level:** High for rules (inherited from Binding Decisions + Checklists), Low for LLM prompt design
**Dependencies:** Stage 2 (Structure Discovery) must be complete. Requires `passages.jsonl` and `pages.jsonl`.

---

## 1. Purpose

Break each passage's text into **atoms** — the smallest semantically complete units of meaning. Atoms are the building blocks from which excerpts are assembled in Stage 4.

---

## 2. Inherited Precision

This stage's rules are already defined with high precision in the manual workflow documents. The app must implement these rules exactly:

| Rule set | Source document | Checklist IDs |
|----------|----------------|---------------|
| Atom boundary rules | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §7 | ATOM.A.1 – ATOM.A.5 |
| Bonded cluster triggers | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §7 | ATOM.B.1 – ATOM.B.6 |
| Heading recognition | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §5 | ATOM.H.1 – ATOM.H.3 |
| Verse/quotation handling | `2_atoms_and_excerpts/checklists_v0.4.md` | ATOM.V.1 – ATOM.V.4 |
| List item handling | `2_atoms_and_excerpts/checklists_v0.4.md` | ATOM.L.1 – ATOM.L.3 |
| Exclusion rules | `2_atoms_and_excerpts/checklists_v0.4.md` | ATOM.E.1 – ATOM.E.3 |
| Granularity rule | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §7 | — |

**These rules are NOT restated here.** The canonical source is the checklist + binding decisions. This spec defines HOW the app executes those rules, not WHAT the rules are.

---

## 3. Input

| Input | Source | Purpose |
|-------|--------|---------|
| `passages.jsonl` | Stage 2 | Passage boundaries and metadata |
| `pages.jsonl` | Stage 1 | Full normalized text |
| Gold passage baselines | Project gold data | Few-shot examples for LLM |

---

## 4. Processing Model

Atomization is **per-passage, sequential**.

For each passage in `passages.jsonl` where `digestible == true`:

### 4.1 CP1: Extract Clean Input

**Method:** Deterministic (no LLM)
**Action:** Extract the passage's text from `pages.jsonl` using the page range defined in the passage.
**Output:** `clean_input.txt` — the raw text of the passage, matn only (footnotes available separately).
**Validation:** Character count matches expected range for page count.

### 4.2 CP2: Atomize

**Method:** LLM-driven with post-processing validation
**Action:** The LLM reads the clean input and the gold few-shot examples, then produces atoms.

**LLM prompt must include:**
1. The clean input text
2. The atomization rules (ATOM.A, ATOM.B, ATOM.H, ATOM.V, ATOM.L, ATOM.E — or a distilled version)
3. 2–3 gold few-shot examples showing input text → atom list
4. The expected output format (JSON)

**LLM output:** A list of atoms, each with:
```json
{
  "atom_id": "A001",
  "text_ar": "الكلمة ثلاثة أقسام: اسم، وفعل، وحرف.",
  "source_page": 13,
  "source_locator": {"page": 13, "line_start": 5, "line_end": 5},
  "is_heading": false,
  "bond_group": null,
  "bond_reason": null,
  "notes": null
}
```

**Post-processing validation (deterministic):**
- Every character in the source text must be covered by exactly one atom (no gaps, no overlaps)
- Atom IDs are sequential within the passage
- `source_locator` is valid (page exists, lines exist)
- Heading atoms flagged correctly (cross-reference with Stage 1 `headings` field)
- Bond groups are internally consistent (all atoms in a group are contiguous)

**On validation failure:** Auto-retry with error feedback (up to 3 retries). If still failing, flag for human review.

---

## 5. Atom Properties (from schema)

Each atom has the following fields (per `schemas/gold_standard_schema_v0.3.3.json`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `atom_id` | string | Yes | Sequential within passage (A001, A002...) |
| `text_ar` | string | Yes | Arabic text of the atom |
| `source_page` | integer | Yes | Page number where the atom appears |
| `source_locator` | object | Yes | `{page, line_start, line_end}` |
| `is_heading` | boolean | Yes | True if this atom is a heading (Binding Decisions §5) |
| `bond_group` | string | No | Group ID if bonded to adjacent atoms (ATOM.B) |
| `bond_reason` | string | No | Why these atoms are bonded |
| `notes` | string | No | Any special notes about this atom |

---

## 6. Key Rules Summary (pointers, not restatements)

- **ATOM.A.1:** One assertion, definition, or example per atom. See Binding Decisions §7.
- **ATOM.B.1–B.6:** Bonded atoms must stay together (condition+result, verse+explanation, etc.)
- **ATOM.H.1–H.3:** Headings are atoms with `is_heading: true`. They are metadata-only — not part of any excerpt's content. See Binding Decisions §5.
- **ATOM.E.1–E.3:** Certain content is excluded from atomization (purely structural markers, page numbers, footnote markers in matn).
- **Granularity (BD §7):** Semantic granulation, not author packaging. If the author writes one long sentence containing two definitions, that's two atoms.

---

## 7. Output Artifacts

### 7.1 Per-passage outputs (in `books/{book_id}/passages/{passage_id}/`)

| File | Description |
|------|-------------|
| `clean_input.txt` | CP1 output: extracted passage text |
| `atoms.jsonl` | CP2 output: one atom per line |
| `atomization_report.json` | Stats: atom count, heading count, bond groups, coverage check |
| `atomization_decisions.jsonl` | Decision log: which checklist items were applied, why |

### 7.2 Validation checks (automated, per passage)

| Check | Method | Pass condition |
|-------|--------|----------------|
| Coverage | Deterministic | All source text accounted for by atoms |
| No gaps | Deterministic | No text between atoms that isn't assigned |
| No overlaps | Deterministic | No text assigned to multiple atoms |
| Heading consistency | Deterministic | Atoms marked as headings match Stage 1 heading data |
| Bond group integrity | Deterministic | All atoms in a bond group are contiguous |
| Schema compliance | JSON Schema validation | Every atom matches schema |

---

## 8. Science-Specific Considerations

Different sciences have different atomization patterns:

| Science | Pattern notes |
|---------|---------------|
| بلاغة | Dense definitions with embedded examples. Verse citations are common. Gold data available (3 passages). |
| صرف | Conjugation tables, morphological paradigms, pattern lists. May require table-aware atomization. **No gold data yet.** |
| نحو | Syntactic parsing examples, إعراب. Rule+exception patterns. **No gold data yet.** |
| إملاء | Spelling rules with examples. Simpler structure typically. **No gold data yet.** |

**Critical gap:** Gold data exists only for بلاغة. Before processing صرف/نحو/إملاء books at scale, we need gold passages for each science to validate that the atomization rules generalize and to provide science-specific few-shot examples.

---

## 9. Open Questions (To Resolve During Zoom-In)

1. **Few-shot selection:** Which gold passages are most useful as few-shot examples? Should we select based on structural similarity to the target passage?
2. **Token budget:** For a 15-page passage, atomization input may be 3,000–5,000 tokens. With few-shot examples and rules, total prompt could be 15,000–20,000 tokens. Is this within budget?
3. **Table handling (صرف):** Conjugation tables in صرف books may need special atomization logic — each cell as an atom? Each row? Each table as a bonded group?
4. **Footnote atoms:** Are footnotes atomized separately or integrated into matn atoms? Current gold data suggests footnotes are excluded from atoms but available as context.
5. **LLM prompt optimization:** Should the full checklist be in the system prompt, or a distilled version? Too much instruction may confuse the LLM; too little may cause rule violations.
