# Arabic Book Digester — Repository Map

**Purpose:** A precision pipeline that transforms classical Arabic books (Shamela HTML exports) into self-contained excerpts placed in taxonomy folder trees — one tree per science. The engine is science-agnostic: currently covers إملاء, صرف, نحو, بلاغة (892 leaves), with عقيدة E2E-tested. Each excerpt file is independently understandable. The taxonomy tree is alive: it evolves as new books reveal finer topic distinctions. Multiple books converge at leaf folders. An external synthesis LLM (outside this repo) reads all excerpt files at each leaf folder and produces one encyclopedia article for Arabic-language students, attributing all scholarly positions.

**Core properties:** Precision (multi-model consensus, human gates, feedback learning) and Intelligence (LLM-driven content decisions, self-improving system). See `CLAUDE.md` for full design principles.

**Pipeline:** Intake → Enrichment → Normalization → Structure Discovery → Extraction (multi-model consensus) → Taxonomy Trees → Taxonomy Evolution (Phase A) → Assembly + Folder Distribution → *external synthesis (out of scope)*

---

## Directory Structure

### Pipeline Stage Specs

| Directory | Stage | Maturity | Key files |
|-----------|-------|----------|-----------|
| `0_intake/` | Book intake & source freezing | ✅ Complete (v1.6) | `INTAKE_SPEC.md`, `edge_cases.md` |
| `1_normalization/` | HTML → structured JSONL | ✅ Complete (spec v0.5) | `NORMALIZATION_SPEC_v0.5.md`, `SHAMELA_HTML_REFERENCE.md`, `CORPUS_SURVEY_REPORT.md`, `gold_samples/` |
| `2_structure_discovery/` | Detect divisions, build passage boundaries | ✅ Complete | `STRUCTURE_SPEC.md`, `structural_patterns.yaml`, 3 corpus surveys, `STAGE2_GUIDELINES.md` |
| `3_atomization/` | Break passages into atoms (legacy spec) | Superseded by Stage 3+4 tool | `ATOMIZATION_SPEC.md` (reference only; automated tool implements these rules) |
| `3_extraction/` | Automated extraction (atoms + excerpts) | ✅ Multi-model consensus, إملاء + عقيدة verified | `RUNBOOK.md`, `gold/P004_gold_excerpt.json` |
| `4_excerpting/` | Excerpt definition + specs | **`EXCERPT_DEFINITION.md` = single source of truth** (needs update) | `EXCERPTING_SPEC.md`, `EXCERPT_DEFINITION.md` |
| `5_taxonomy/` | Build taxonomy trees per science, evolve trees | ✅ All 4 core sciences + عقيدة (892+ leaves) | `TAXONOMY_SPEC.md` |

### Precision Documents (Binding Authority)

Canonical location: `2_atoms_and_excerpts/`

| File | What it governs |
|------|----------------|
| `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` | Atom boundaries, excerpt rules, topic scope guard, core duplication, headings |
| `2_atoms_and_excerpts/checklists_v0.4.md` | ATOM.*, EXC.*, PLACE.*, REL.* checklist items |
| `2_atoms_and_excerpts/extraction_protocol_v2.4.md` | Checkpoint sequence (CP1–CP6) |
| `project_glossary.md` | Authoritative definitions for all terms |

**Deprecated:** `archive/precision_deprecated/` contains older versions (v0.3.10, v0.3.15 binding; v0.3 checklists; v2 protocol). **Do not read these — they will cause confusion** with outdated rules. Only the versions in `2_atoms_and_excerpts/` are current.

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

Each taxonomy YAML defines a folder structure for one science. The YAML hierarchy maps directly to nested directories: the root key is the science name (= root folder), branches become subfolders, and leaf nodes become the endpoint folders where excerpt files are placed. Multiple books' excerpts accumulate as files in the same leaf folder.

```
taxonomy/
├── taxonomy_registry.yaml              — version registry
├── README.md
├── imlaa_v0.1.yaml                     — إملاء taxonomy v0 (44 leaves)
├── imlaa/imlaa_v1_0.yaml              — إملاء taxonomy v1 (105 leaves)
├── sarf/sarf_v1_0.yaml                — صرف taxonomy v1 (226 leaves)
├── nahw/nahw_v1_0.yaml                — نحو taxonomy v1 (226 leaves)
├── balagha/balagha_v1_0.yaml          — بلاغة taxonomy v1 (335 leaves)
├── balagha/balagha_v0_{2,3,4}.yaml    — historical بلاغة versions (gold baselines)
├── aqidah/aqidah_v0_1.yaml            — عقيدة taxonomy v0.1 (21 leaves)
└── aqidah/aqidah_v0_2.yaml            — عقيدة taxonomy v0.2 (28 leaves, evolved)
```

**892 leaves across 4 core sciences** (إملاء 105 + صرف 226 + نحو 226 + بلاغة 335). عقيدة is an E2E test science (28 leaves after evolution).

**The taxonomy is alive:** Trees evolve as books reveal finer topic distinctions. Evolution is LLM-driven with human approval. See `CLAUDE.md` for the full evolution model.

**Taxonomy evolution engine:** `tools/evolve_taxonomy.py` — Phase A + B complete (signal detection, LLM proposals, apply proposals to YAML, excerpt redistribution, rollback, multi-model consensus). 5 signal types: unmapped, same_book_cluster, category_leaf, multi_topic_excerpt, user_specified.

### Tools

| Tool | Lines | Stage | Purpose |
|------|-------|-------|---------|
| `tools/intake.py` | ~1450 | 0 | Book intake, source freezing, metadata extraction |
| `tools/enrich.py` | ~560 | 0.5 | Scholarly context enrichment (interactive/ترجمة/API) |
| `tools/normalize_shamela.py` | ~1120 | 1 | HTML → pages.jsonl (deterministic) |
| `tools/discover_structure.py` | ~2856 | 2 | Passage boundary detection, division hierarchy |
| `tools/extract_passages.py` | ~2115 | 3+4 | **LLM-based extraction**: atomization + excerpting + taxonomy placement. Multi-model consensus. Verified on إملاء + عقيدة. |
| `tools/consensus.py` | ~1722 | 3+4 | Multi-model consensus engine: text-overlap matching, LLM arbiter |
| `tools/assemble_excerpts.py` | ~530 | 7 | Self-contained excerpt assembly + taxonomy folder distribution |
| `tools/evolve_taxonomy.py` | ~2280 | 6 | Taxonomy evolution: signal detection, LLM proposals, apply, redistribute, rollback, multi-model consensus (Phase A + B) |
| `tools/extract_clean_input.py` | 234 | 3 (CP1) | Extract clean text from HTML for manual atomization (legacy) |
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

### Books (Test Cases)

The books in `books/` are test cases for developing and validating the pipeline tools. They are not a production queue.

```
books/
├── books_registry.yaml              — registry of all intaken books
├── {book_id}/                       — per-book directory (8 books intaken)
│   ├── intake_metadata.json         — frozen metadata (schema v0.2), includes scholarly_context
│   └── source/                      — frozen source HTML (read-only, gitignored)
└── Other Books/                     — raw Shamela exports (gitignored, present locally)
    ├── كتب العقيدة/                 — 804 books (عقيدة — creed/theology)
    ├── كتب الفقه الحنبلي/           — 147 books (فقه حنبلي — Hanbali jurisprudence)
    ├── كتب البلاغة/                 — بلاغة — rhetoric
    ├── كتب النحو والصرف/            — نحو + صرف — grammar & morphology
    └── كتب اللغة/                   — لغة — Arabic language/lexicography
```

**Available Shamela exports:** `books/Other Books/` contains a large library of raw Shamela HTML exports organized by science category — ready to be intaken through the pipeline using `tools/intake.py`. These files are gitignored (large binary) but present locally for development.

Each `intake_metadata.json` carries a `scholarly_context` block (author death/birth dates, fiqh madhab, grammatical school, geographic origin). These fields are critical for the downstream synthesis LLM to attribute opinions — but currently most are sparse/auto-extracted. The enrichment tool (`tools/enrich.py`) is intended to fill them via research.

### Tests

869+ tests pass across 8 test files (parametrized tests expand the count).

| Test file | Tests | Covers |
|-----------|-------|--------|
| `tests/test_intake.py` | ~90 | `tools/intake.py` |
| `tests/test_enrich.py` | ~16 | `tools/enrich.py` |
| `tests/test_normalization.py` | ~193 | `tools/normalize_shamela.py` |
| `tests/test_structure_discovery.py` | ~86 | `tools/discover_structure.py` |
| `tests/test_extraction.py` | ~165 | `tools/extract_passages.py` |
| `tests/test_consensus.py` | ~120 | `tools/consensus.py` |
| `tests/test_assembly.py` | ~50 | `tools/assemble_excerpts.py` |
| `tests/test_evolution.py` | ~90 | `tools/evolve_taxonomy.py` |

---

## Known Schema Drift (Stages 3–4)

The ZOOM_BRIEF files in stages 3 and 4 document **schema drift** between the stage specs and the actual gold data. The gold data + `schemas/gold_standard_schema_v0.3.3.json` + `2_atoms_and_excerpts/` are authoritative. Stage specs that contradict them need updating. Key drifts:

- Atom IDs: specs say `A001`, gold says `jawahir:matn:000001`
- Atom fields: specs say `text_ar`, gold says `text`; `source_page` vs `page_hint`; `is_heading` vs `atom_type`
- Excerpt fields: specs say `placed_at`, gold says `taxonomy_node_id` + `taxonomy_path`
- Relation types: specs fabricate types; real types are in glossary §7

**Always trust:** gold data > schema v0.3.3 > binding decisions > checklists > stage specs
