# Stage 3: Atomization — Zoom-In Brief

## Mandate

The atomization rules are mature (inherited from 3 gold passages of manual work), but the spec was written before the gold baselines solidified. The spec contains significant **schema drift** — it uses placeholder field names and structures that don't match the actual proven data model. The zoom-in must reconcile the spec with reality and design the LLM automation layer.

## Pre-Identified Issues — Schema Drift (Critical)

The spec (§5, §4.2) describes an atom schema that **does not match** the actual gold data or the authoritative `gold_standard_schema_v0.3.3.json`:

| Spec says | Actual schema/gold data says | Status |
|-----------|------------------------------|--------|
| `atom_id`: `A001` | `atom_id`: `jawahir:matn:000004` | **Wrong format** |
| `text_ar` | `text` | **Wrong field name** |
| `source_page` | `page_hint` (string like `ص:١٩`) | **Wrong field name and type** |
| `source_locator: {page, line_start, line_end}` | `source_anchor: {char_offset_start, char_offset_end}` | **Wrong structure** |
| `is_heading` (boolean) | `atom_type: "heading"` (enum) | **Wrong representation** |
| `bond_group` / `bond_reason` | `bonded_cluster_trigger: {trigger_id, reason}` | **Wrong structure** |
| `notes` | `atomization_notes` | **Wrong field name** |
| No `footnote_refs` | `footnote_refs: [{marker_text, footnote_atom_ids}]` | **Missing** |
| No `internal_tags` | `internal_tags: [{tag_type, text_fragment, note}]` | **Missing** |
| No `canonical_text_sha256` | `canonical_text_sha256` | **Missing** |
| No `book_id` | `book_id` (required) | **Missing** |
| No `source_layer` | `source_layer` (required) | **Missing** |

**The gold data and schema are authoritative.** The spec must be rewritten to match them.

## Pre-Identified Issues — Other

1. **Open question §9.4 is already answered.** "Are footnotes atomized separately?" — Yes. The gold data has separate `*_fn_atoms_v02.jsonl` files. Footnote atoms use `source_layer: "footnote"` and have their own layer token (`fn`). This is well-established.

2. **Open question §9.1 (few-shot selection) needs concrete design.** Which gold passages make good few-shot examples? The 3 passages have different characteristics: P1 has teaching + exercises, P2 has dense exercises + footnotes, P3 has diverse atom types.

3. **CP structure mismatch.** The spec defines CP1 (extract) and CP2 (atomize) as the two checkpoints. The extraction protocol defines 6 checkpoints where CP1 = extract, CP2 = atomize, CP3 = canonical text. The spec should reference the extraction protocol's CP numbering.

4. **Science-specific patterns (§8) need expansion.** The spec identifies that صرف has tables and نحو has إعراب patterns, but offers no concrete design for handling them. This may be blocked until gold data exists for those sciences.

5. **Coverage validation is partially defined.** The spec mentions "every character must be covered" but the actual invariant from the gold data is character-offset-based: `atom.text == canonical_text[char_offset_start:char_offset_end]`. The spec should use the precise formulation.

6. **LLM prompt design is blank.** The spec identifies the need for an LLM prompt but doesn't sketch one. At minimum, the zoom-in should produce a prompt skeleton that references the right rules and includes a gold few-shot example.

## What to Read

- `3_atomization/ATOMIZATION_SPEC.md` (primary — but read critically, it has drift)
- `schemas/gold_standard_schema_v0.3.3.json` — search for `"atom"` record type definition. **This is the truth.**
- `gold_baselines/jawahir_al_balagha/passage1_v0.3.14/passage1_matn_atoms_v02.jsonl` — read 5–10 atom records to see what real atoms look like
- `gold_baselines/jawahir_al_balagha/passage1_v0.3.14/passage1_fn_atoms_v02.jsonl` — footnote atoms
- `project_glossary.md` §3 (Atoms) — authoritative definitions
- `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §5 (headings), §7 (granularity) — binding rules
- `2_atoms_and_excerpts/checklists_v0.4.md` — ATOM.* checklist items
- `2_atoms_and_excerpts/extraction_protocol_v2.4.md` §2 (Atomization checkpoint)

## Expected Deliverables

- Rewritten `ATOMIZATION_SPEC.md` with correct schema fields matching `gold_standard_schema_v0.3.3.json`
- Resolved open questions (mark answered ones, keep genuinely open ones)
- LLM prompt skeleton for atomization
- Defined few-shot selection strategy
- Updated CP numbering aligned with extraction protocol
- Honest assessment of what can't be finalized without non-بلاغة gold data
