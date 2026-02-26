# Arabic Book Digester — Repository Map

**Purpose:** Extract tagged excerpts from 788 classical Arabic books (Shamela HTML exports) and place them in taxonomy trees for four sciences: بلاغة, صرف, نحو, إملاء.

**Pipeline:** Intake → Normalization → Structure Discovery → Atomization → Excerpting → Taxonomy Placement

---

## Directory Structure

### Pipeline Stage Specs

| Directory | Stage | Maturity | Key files |
|-----------|-------|----------|-----------|
| `0_intake/` | Book intake & source freezing | ✅ Complete (v1.6) | `INTAKE_SPEC.md`, `edge_cases.md` |
| `1_normalization/` | HTML → structured JSONL | ✅ Complete (spec v0.5) | `NORMALIZATION_SPEC_v0.5.md`, `SHAMELA_HTML_REFERENCE.md`, `CORPUS_SURVEY_REPORT.md`, `gold_samples/` |
| `2_structure_discovery/` | Detect divisions, build passage boundaries | Draft (least mature) | `STRUCTURE_SPEC.md`, `structural_patterns.yaml`, 3 corpus surveys, `STAGE2_GUIDELINES.md` |
| `3_atomization/` | Break passages into atoms | Draft (rules mature, spec has schema drift) | `ATOMIZATION_SPEC.md` (see ZOOM_BRIEF for drift details) |
| `4_excerpting/` | Group atoms into excerpts, assign to taxonomy | Draft (most complex, major schema drift) | `EXCERPTING_SPEC.md`, `EXCERPT_DEFINITION.md` |
| `5_taxonomy/` | Place excerpts in taxonomy trees, evolve trees | Draft | `TAXONOMY_SPEC.md` |

### Precision Documents (Binding Authority)

Canonical location: `2_atoms_and_excerpts/`

| File | What it governs |
|------|----------------|
| `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` | Atom boundaries, excerpt rules, topic scope guard, core duplication, headings |
| `2_atoms_and_excerpts/checklists_v0.4.md` | ATOM.*, EXC.*, PLACE.*, REL.* checklist items |
| `2_atoms_and_excerpts/extraction_protocol_v2.4.md` | Checkpoint sequence (CP1–CP6) |
| `project_glossary.md` | Authoritative definitions for all terms |

**Deprecated:** `precision/` contains older versions (v0.3.10, v0.3.15 binding; v0.3 checklists; v2 protocol). Retained for historical baseline reproducibility only.

**Rule:** Stage 3/4 specs say "rules are NOT restated here — canonical source is binding decisions + checklists." When in doubt, `2_atoms_and_excerpts/` overrides stage specs.

### Gold Baselines (Proven Ground Truth)

```
gold_baselines/jawahir_al_balagha/
├── passage1_v0.3.13/   (59 matn atoms, 36 fn atoms, 21 excerpts)  — pages 19–25
├── passage2_v0.3.22/   (86 atoms, 103 excerpts, 64 decisions)     — pages 26–32
└── passage3_v0.3.14/   (75 atoms, 81 excerpts, 77 decisions)      — pages 33–40
```

Active gold index: `2_atoms_and_excerpts/1_jawahir_al_balagha/ACTIVE_GOLD.md`

Each passage contains: atoms (matn + footnote), excerpts, decisions log, canonical text, source slice, checkpoint reports, rendered excerpts, taxonomy changes, validation report. Passage 2 went through 22 revision iterations.

### Schemas

| File | Purpose |
|------|---------|
| `schemas/intake_metadata_schema.json` | Stage 0 metadata validation (v0.2) |
| `schemas/gold_standard_schema_v0.3.3.json` | **Authoritative** atom + excerpt + exclusion schema (903 lines) |
| `schemas/gold_standard_schema_v0.3.{1,2}.json` | Earlier schema versions (for archive reference) |
| `schemas/baseline_manifest_schema_v0.1.json` | Passage manifest validation |
| `schemas/checkpoint_state_schema_v0.1.json` | Checkpoint state tracking |
| `schemas/decision_log_schema_v0.1.json` | Decision log validation |
| `schemas/passage_metadata_schema_v0.1.json` | Passage metadata validation |
| `schemas/source_locator_schema_v0.1.json` | Source anchor validation |

### Taxonomy

```
taxonomy/
├── taxonomy_registry.yaml          — version registry
├── README.md
└── balagha/
    ├── balagha_v0_2.yaml           — used by passage 1 gold
    ├── balagha_v0_3.yaml           — used by passages 2–3 gold
    └── balagha_v0_4.yaml           — latest (202 nodes, 143 leaves)
```

**Missing:** صرف, نحو, إملاء trees (not yet created).

### Tools

| Tool | Lines | Stage | Purpose |
|------|-------|-------|---------|
| `tools/intake.py` | ~1450 | 0 | Book intake, source freezing, metadata extraction |
| `tools/enrich.py` | ~560 | 0.5 | Scholarly context enrichment (interactive/ترجمة/API) |
| `tools/normalize_shamela.py` | ~1120 | 1 | HTML → pages.jsonl (deterministic) |
| `tools/extract_clean_input.py` | 234 | 3 (CP1) | Extract clean text from HTML for atomization |
| `tools/validate_gold.py` | ~1930 | QA | Validate gold baselines against schema |
| `tools/render_excerpts_md.py` | 271 | QA | Render excerpts as readable Markdown |
| `tools/scaffold_passage.py` | 272 | Util | Create passage directory structure |
| `tools/pipeline_gold.py` | 512 | Util | Run full gold pipeline |
| `tools/build_baseline_manifest.py` | 214 | Util | Generate baseline manifests |
| `tools/run_all_validations.py` | 97 | QA | Run all validation checks |
| `tools/corpus_audit.py` | 219 | QA | Corpus-wide analysis |

### Spec Contracts

```
spec/
├── checkpoint_outputs_contract_v0.{1,2,3}.md  — what each checkpoint produces
├── normalization_contract_v0.1.md             — normalization input/output contract
├── runtime_contract_v0.1.md                   — runtime requirements
└── source_locator_contract_v0.1.md            — source anchor spec
```

### Books

```
books/
├── books_registry.yaml              — registry of all intaken books
├── {book_id}/                       — per-book directory (7 books intaken)
│   ├── intake_metadata.json         — frozen metadata (schema v0.2)
│   └── source/                      — frozen source HTML (read-only)
└── Other Books/                     — raw Shamela exports (788 files, not yet intaken)
```

### Tests

2723 test lines: 665 intake + 118 enrich + 1940 normalization.

---

## Known Schema Drift (Stages 3–4)

The ZOOM_BRIEF files in stages 3 and 4 document **schema drift** between the stage specs and the actual gold data. The gold data + `schemas/gold_standard_schema_v0.3.3.json` + `2_atoms_and_excerpts/` are authoritative. Stage specs that contradict them need updating. Key drifts:

- Atom IDs: specs say `A001`, gold says `jawahir:matn:000001`
- Atom fields: specs say `text_ar`, gold says `text`; `source_page` vs `page_hint`; `is_heading` vs `atom_type`
- Excerpt fields: specs say `placed_at`, gold says `taxonomy_node_id` + `taxonomy_path`
- Relation types: specs fabricate types; real types are in glossary §7

**Always trust:** gold data > schema v0.3.3 > binding decisions > checklists > stage specs
