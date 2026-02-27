# CLAUDE.md — Arabic Book Digester (ABD)

## What This Is

ABD extracts structured excerpts from classical Arabic books (Shamela HTML exports) and places them in taxonomy folder trees. It covers four sciences: إملاء (orthography), صرف (morphology), نحو (syntax), بلاغة (rhetoric). Each science has its own independent taxonomy tree.

**Taxonomy = folder structure:** Each science's taxonomy YAML defines a real directory tree. The root folder is the science name (e.g., `imlaa/`). Branches become nested folders. Leaf folders are the endpoints where excerpt files are saved. "Placing an excerpt at a taxonomy node" means writing the excerpt file into that node's folder. Multiple books contribute excerpt files to the same folder tree, so a leaf folder accumulates excerpts from different authors on the same topic.

**The downstream consumer:** An **external synthesis LLM** (outside this repo) reads all excerpt files at each leaf folder and produces a single encyclopedia article aimed at **Arabic-language students**. When authors disagree — different madhabs, different eras, different grammatical schools — the synthesis LLM presents all scholarly positions and attributes each to its author.

**Why this matters for ABD:** Every structural decision in this pipeline exists to serve that downstream synthesis. Excerpt boundaries must be clean enough that the synthesis LLM can understand each excerpt in isolation. Metadata must be rich enough that the synthesis LLM can attribute opinions to specific authors and resolve conflicting views. Relation chains (`split_continues_in`, `split_continued_from`) must be intact so the synthesis LLM can reconstruct multi-passage arguments. The `case_types`, `boundary_reasoning`, roles, and taxonomy placement all help the synthesis LLM understand *what kind of content* it's looking at and *where it fits* in the topic.

**Author context is critical:** Because multiple books from different scholars feed the same taxonomy leaf, author identity matters. Each book's `intake_metadata.json` carries a `scholarly_context` block (author death date, fiqh madhab, grammatical school, geographic origin) — but these fields are currently sparse (mostly auto-extracted). The enrichment step (`tools/enrich.py`) is intended to fill them with researched mini-biographies. This is a known gap: intake captures basic metadata, but deep scholarly context (madhab, school affiliation, era, intellectual lineage) needs to be extended into an intelligent research system.

## Pipeline Stages

| Stage | Tool | Status | Tests |
|-------|------|--------|-------|
| 0 Intake | `tools/intake.py` | ✅ Complete | `tests/test_intake.py` |
| 0.5 Enrichment | `tools/enrich.py` | 🟡 Basic | `tests/test_enrich.py` |
| 1 Normalization | `tools/normalize_shamela.py` | ✅ Complete | `tests/test_normalization.py` |
| 2 Structure Discovery | `tools/discover_structure.py` | ✅ Complete | `tests/test_structure_discovery.py` |
| 3+4 Extraction | `tools/extract_passages.py` | ✅ Complete | `tests/test_extraction.py` |
| 5 Taxonomy Trees | `taxonomy/*.yaml` | 🟡 إملاء done, 3 sciences remaining | — |

Taxonomy placement *per excerpt* is handled by the extraction tool (Stage 3+4), which assigns each excerpt a `taxonomy_node_id`. But the taxonomy trees themselves — one per science — must be built before extraction can run on that science. Currently only `taxonomy/imlaa_v0.1.yaml` (44 leaves) exists. صرف, نحو, and بلاغة trees still need to be created and placed in `taxonomy/`.

**Not yet implemented:** Converting the flat extraction output into the taxonomy folder structure (science root → nested topic folders → excerpt files at leaves). Currently extraction saves all results flat in `output_dir/`. A future step must distribute excerpt files into the folder tree defined by the taxonomy YAML.

There is no synthesis stage in ABD. The external synthesis LLM reads excerpt files from each taxonomy leaf folder to produce one encyclopedia article per leaf, targeting Arabic-language students.

## Running Things

```bash
# Tests (463 pass, ~9s)
python -m pytest tests/ -q

# Single test file
python -m pytest tests/test_structure_discovery.py -q

# Extraction dry run (no API needed)
python tools/extract_passages.py \
  --passages books/imla/stage2_output/passages.jsonl \
  --pages books/imla/stage1_output/pages.jsonl \
  --taxonomy taxonomy/imlaa_v0.1.yaml \
  --book-id qimlaa --book-title "قواعد الإملاء" --science imlaa \
  --gold 3_extraction/gold/P004_gold_excerpt.json \
  --output-dir output/imlaa_extraction --dry-run

# Extraction with API (single passage)
export ANTHROPIC_API_KEY="sk-ant-..."
python tools/extract_passages.py \
  --passages books/imla/stage2_output/passages.jsonl \
  --pages books/imla/stage1_output/pages.jsonl \
  --taxonomy taxonomy/imlaa_v0.1.yaml \
  --book-id qimlaa --book-title "قواعد الإملاء" --science imlaa \
  --gold 3_extraction/gold/P004_gold_excerpt.json \
  --output-dir output/imlaa_extraction \
  --passage-ids P004

# Extraction with API (full book, ~$3–5)
# Same command without --passage-ids
```

## Dependencies

```bash
pip install PyYAML httpx
```

Python 3.11+ required. No virtual env needed for simple runs; use `pip install --break-system-packages` if on system Python.

## Key Files to Read

**Start here (in order):**
1. This file
2. `REPO_MAP.md` — full directory structure explanation
3. `3_extraction/RUNBOOK.md` — running the extraction pipeline

**Specs (read when working on a specific stage):**
- `0_intake/INTAKE_SPEC.md`
- `1_normalization/NORMALIZATION_SPEC_v0.5.md`
- `2_structure_discovery/STRUCTURE_SPEC.md`
- `3_atomization/ATOMIZATION_SPEC.md`
- `4_excerpting/EXCERPT_DEFINITION.md` — the most important spec; defines what an excerpt IS
- `4_excerpting/EXCERPTING_SPEC.md`

**Binding authority (overrides stage specs when in conflict):**
- `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md`
- `2_atoms_and_excerpts/checklists_v0.4.md`

**Gold baselines (proven ground truth for بلاغة):**
- `gold_baselines/jawahir_al_balagha/passage1_v0.3.13/` — 21 excerpts, start here
- `3_extraction/gold/P004_gold_excerpt.json` — gold for إملاء extraction

**Taxonomy:**
- `taxonomy/imlaa_v0.1.yaml` — إملاء taxonomy (44 leaves), built from قواعد الإملاء
- `gold_baselines/jawahir_al_balagha/passage1_v0.3.13/` contains balagha taxonomy snapshots

## Architecture Patterns

**Stage I/O chain:** Each stage reads the previous stage's JSONL output. Books are registered in `books/` with `intake_metadata.json` (includes `scholarly_context` for author madhab, school, era). Normalization produces `pages.jsonl`. Structure discovery produces `passages.jsonl` + `divisions.json`. Extraction produces `atoms` + `excerpts` per passage. The final output is a taxonomy folder tree per science, with excerpt files placed at leaf folders — this is the handoff point to the external synthesis LLM.

**Multi-book convergence:** Multiple books from different authors feed excerpt files into the same taxonomy folder tree (one tree per science). A leaf folder may contain excerpts from several books. The synthesis LLM at each leaf folder must reconcile differing scholarly opinions. This means every excerpt must carry enough context (book_id, author identity via intake_metadata, source_layer, roles, case_types) for the synthesis LLM to attribute views correctly.

**LLM calls:** Tools call Claude APIs directly via httpx. API key passed as CLI arg or env var `ANTHROPIC_API_KEY`. LLM-dependent stages gracefully degrade if API fails mid-run (e.g., Stage 2 Pass 3b uses whatever Pass 3a produced).

**Validation:** Each tool has built-in validation. Extraction validates 17 invariants across 3 severity levels (errors, warnings, info) covering atom coverage, reference integrity, leaf placement, bonding trigger presence, role validation, case_types, layer isolation, and more. Failed validation triggers an automatic correction retry loop (up to 2 retries). Structure discovery validates range monotonicity, overlap, coverage.

**Testing:** pytest, no fixtures framework. Tests are self-contained with inline data. Test files mirror tool files: `test_normalization.py` tests `normalize_shamela.py`.

**Text handling:** All Arabic text is verbatim — never corrected, never normalized in the primary representation. A separate `normalized_text` field exists for search/matching. Diacritics preserved exactly as source.

## Code Conventions

- Python 3.11+, type hints used but not enforced
- CLI tools use argparse, not click
- JSONL for data, YAML for taxonomy, JSON for metadata
- Markdown for human review reports
- All tools are standalone scripts in `tools/`, importable as modules
- Test with `python -m pytest`, not `pytest` directly (ensures correct path)
- All file I/O uses `encoding="utf-8"` explicitly (Windows defaults to cp1252)

## Current State and What to Work On

Extraction tool is complete and tested (1389 lines, 80 tests, 17-check validation, correction retry loop). End-to-end verification on 5 diverse passages (P004, P005, P006, P010, P020) all pass with 0 errors and 0 retries. Output is currently flat per-passage JSON files — the taxonomy folder distribution step is not yet built.

**Immediate priorities (in order):**
1. Run full book extraction on قواعد الإملاء (46 passages, ~$3–5) and review quality
2. Build the taxonomy folder distribution step — convert flat extraction output into the taxonomy folder tree (science root → nested folders → excerpt files at leaves)
3. Build taxonomy trees for صرف, نحو, بلاغة (only إملاء exists so far)
4. Run the pipeline on شذا العرف (صرف science) to test cross-science generalization
5. Extend intake enrichment — author scholarly context (`scholarly_context` in intake_metadata.json) needs deep, researched metadata (madhab, grammatical school, intellectual lineage) so the synthesis LLM can properly attribute opinions

**Do NOT spend time on:**
- Perfecting Stage 2 edge cases (600+ heading chunking, structureless books, etc.) — wait until a book actually needs them
- Multi-judge consensus — single-pass extraction quality is sufficient for now
- Building review UIs — markdown review reports are good enough
- Building synthesis tooling — synthesis is external to this repo
- Bulk-processing books — the books in `books/` are test cases for tool development, not a production queue

## Test Books

The books in `books/` are test cases for developing and validating the pipeline tools. They are not a production queue — the goal is a working extraction tool, not bulk processing.

```
books/
├── imla/          # قواعد الإملاء (77p, إملاء) — primary test book, has Stage 1+2 outputs
├── shadha/        # شذا العرف (187p, صرف) — next test target (different science)
├── jawahir/       # جواهر البلاغة (بلاغة) — gold baseline source
├── qatr/          # قطر الندى (نحو)
├── ibn_aqil/      # شرح ابن عقيل (نحو)
├── miftah/        # مفتاح العلوم (بلاغة)
├── dalail/        # دلائل الإعجاز (بلاغة)
└── Other Books/   # Raw Shamela exports (additional test candidates)
```

## Gotchas

- **`2_atoms_and_excerpts/` is NOT Stage 2.** Despite the numbering, it's a precision rules folder (binding decisions, checklists, gold baselines) from the manual workflow. Stage 2 is `2_structure_discovery/`. See its README.md. Several tools have hardcoded paths to it — don't rename.
- **`3_atomization/` and `3_extraction/` both exist.** `3_atomization/` is the old spec for manual atomization. `3_extraction/` is the automated extraction (complete). The automated tool (`tools/extract_passages.py`, 1389 lines) combines atomization + excerpting + taxonomy placement into one LLM pass with post-processing and validation.
- **`archive/` contains dead docs.** Old orientation files (READ_FIRST, PROJECT_PROMPT, SESSION_CONTEXT) and deprecated precision versions. Ignore entirely.
- **Shamela HTML is uniform**: All Shamela exports use the same template. No structural variants.
- **Page numbering**: Multi-volume books may restart numbering per volume or use continuous pagination. `seq_index` is always monotonic.
- **Binding decisions override specs**: If `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` says X and a stage spec says Y, binding decisions win.
- **Gold baselines are for بلاغة only**: The jawahir baselines are hand-crafted for بلاغة. إملاء has a simpler discourse structure (rules + examples, minimal scholarly disputes).
- **`__overview` leaves**: Parent taxonomy nodes that receive overview/framing content need `__overview` companion leaves (convention from the vertical slice).
- **Passage boundaries are guidance**: Stage 2 passages are structural suggestions. Extraction may find content that spans passage boundaries (prose_tail detection handles this).
- **Taxonomy YAML = folder structure**: The YAML tree for each science defines a real directory tree. Root folder = science name, branches = nested folders, leaves = folders where excerpt files are placed. Multiple books' excerpts converge as files in the same leaf folders. The folder distribution step (YAML → directories → excerpt files placed) is not yet implemented.
- **One taxonomy tree per science**: إملاء, صرف, نحو, بلاغة each have independent trees. Books within a science share the same tree.
- **Author context gap**: `intake_metadata.json` has a `scholarly_context` block but most fields are null/auto. The enrichment tool needs extension to research and populate author madhab, grammatical school, era, and intellectual lineage — critical for the synthesis LLM to attribute opinions.
