# CLAUDE.md — Arabic Book Digester (ABD)

## What This Is

ABD is a precision pipeline that transforms classical Arabic books (Shamela HTML exports) into self-contained, accurately-placed excerpts organized in taxonomy folder trees. The engine is science-agnostic — it currently covers إملاء (orthography), صرف (morphology), نحو (syntax), بلاغة (rhetoric), and has been E2E-tested on عقيدة (creed). Future expansion to 20+ Islamic sciences is planned (see VISION.md).

## Core Design Principles

**1. Precision above all.** Every operation — excerpting, taxonomy placement, tree evolution — must be surgically accurate. Errors in excerpting propagate to every downstream consumer. The system uses multi-model consensus, cross-validation, human gates with feedback loops, and regression testing to approach flawless output.

**2. Intelligence over algorithms.** High-stakes content decisions (excerpt boundaries, taxonomy placement, tree evolution) are LLM-driven, not hardcoded. Multiple models work independently and their outputs are compared. Mechanical checks (schema validation, coverage verification, character counts) use algorithms where appropriate, but content understanding always requires LLM intelligence.

**3. Self-containment.** Every excerpt must be independently understandable. When the synthesis LLM receives an excerpt, it must be able to extract everything it needs from that single file — the Arabic text, author identity, scholarly tradition, topic context — without requesting additional files or cross-referencing.

**4. Living taxonomy.** The taxonomy tree is not a fixed container — it evolves as new books reveal finer topic distinctions. Excerpts are king; the tree serves them, never the other way around.

**5. Self-improving system.** When a human corrects an error, the full correction cycle is saved. The system traces root causes (prompt ambiguity? definition gap? domain knowledge gap?) and proposes fixes to its own rules. Every fix requires human approval and regression testing before being applied.

## How It Works

### The end goal

For each granular topic (leaf node) within a science, accumulate self-contained excerpts from multiple books by different scholars. Each excerpt independently explains that topic from its author's perspective. An **external synthesis LLM** (outside this repo) reads all excerpts at each leaf folder and synthesizes them into one comprehensive encyclopedia article for **Arabic-language students**, presenting and attributing all scholarly positions.

### Taxonomy = folder structure

Each science's taxonomy YAML defines a real directory tree:
- Root folder = science name (e.g., `imlaa/`)
- Branches = nested folders
- Leaf folders = endpoints where excerpt files are placed

"Placing an excerpt at a taxonomy node" means writing the excerpt file into that node's folder. Multiple books contribute excerpt files to the same tree, so a leaf folder accumulates excerpts from different authors on the same topic.

### Excerpting is purely content-driven

Excerpt boundaries come from the text — what atoms naturally form a self-contained teaching unit. The taxonomy tree has **zero influence** on how excerpting happens. You excerpt first (what is a coherent teaching unit?), place second (where does this belong?), evolve third (is the tree granular enough?). These are three distinct operations.

### Taxonomy evolution

The taxonomy starts from a base outline and grows as books reveal finer distinctions. When a new excerpt reveals that a leaf node covers multiple sub-topics, the tree evolves:

1. The system detects the need for finer granularity (evolution signal)
2. An LLM proposes new sub-nodes, reading the Arabic text of ALL excerpts at the affected node (including from previously processed books)
3. Existing excerpts are redistributed to the new sub-nodes based on their content
4. Safety checks: every excerpt has a home (zero orphans), the new structure makes sense, no progress is lost
5. Human approves before the evolution is applied
6. Full rollback capability via taxonomy version control

### One excerpt per book per node (quality preference)

If extraction produces two excerpts from the same book at the same node, that's a signal: either merge them (they're about the same thing) or evolve the node (they cover different sub-aspects). This is a quality preference that drives proper granularity, not a constraint on excerpting itself.

### Multi-model consensus

For precision-critical operations (extraction, taxonomy placement, evolution), multiple models (Claude, GPT-4o, others) work independently on the same input. Where all agree: high confidence. Where they disagree: an arbiter resolves, or the disagreement is flagged for human review.

### Human gates and feedback learning

After major steps, the system pauses for human review:
- **After extraction:** Excerpts are presented. The user can flag disagreements on specific excerpts with feedback. The flagged excerpt's source passage is re-extracted with the feedback. Once approved, the full correction cycle is saved.
- **After taxonomy evolution:** The proposed changes are shown as a diff before being applied.

Saved corrections are analyzed for patterns. If the system detects a systemic issue (e.g., "8 of 20 corrections were about bonded clusters"), it proposes a root cause fix (prompt adjustment, definition clarification). The fix requires human approval and regression testing (re-run on previously approved excerpts to ensure no regressions).

### Self-containment in detail

Each excerpt file in a leaf folder must contain everything the synthesis LLM needs:
- The full Arabic text (core content + context), not atom ID references
- Author identity and scholarly context (madhab, grammatical school, era)
- Book title and source page references
- Taxonomy path and topic context
- Content type metadata (case_types, roles, boundary_reasoning)

The synthesis LLM reads one excerpt at a time, accumulating understanding. It must never need to say "I need excerpt X too" or "could you provide more context."

### Author context

Because multiple books from different scholars feed the same taxonomy leaf, author identity matters. Each book's `intake_metadata.json` carries a `scholarly_context` block (author death date, fiqh madhab, grammatical school, geographic origin). These fields are currently sparse — the enrichment step (`tools/enrich.py`) needs extension into an intelligent research system to fill them.

## The Pipeline

```
Phase 1: Book Preparation
  1. Intake — register book, freeze source HTML
  2. Enrichment — research author scholarly context
  3. Normalization — HTML → pages.jsonl (deterministic)
  4. Structure Discovery — pages → passages (LLM-assisted)

Phase 2: Extraction (per passage → multiple excerpts)
  5. Multi-model extraction — 3 models independently:
     - Break passage text into atoms
     - Group atoms into self-contained excerpts
     - Assign taxonomy placement per excerpt
     - Flag evolution signals where placement is imprecise
  6. Consensus engine — compare outputs, merge agreements, flag disagreements
  7. Human gate — review excerpts, provide feedback on flagged items
     → Correction cycle saved, root cause analysis, system self-improvement

Phase 3: Taxonomy Evolution (after full book extraction)
  8. Analyze all placements + evolution signals
     - Detect nodes needing finer granularity
     - Read Arabic text of ALL excerpts at affected nodes (all books)
     - Propose new sub-nodes (multi-model consensus)
     - Validate: no orphans, structure makes sense, no progress lost
  9. Human gate — approve evolution before applying
     → Checkpoint/snapshot, dry run, rollback capability

Phase 4: Assembly + Distribution
  10. Assemble self-contained excerpt files (inline text + embed metadata)
  11. Place in taxonomy folder tree (one file per excerpt per leaf)

Cross-cutting: quality scoring, placement cross-validation,
self-containment validation, taxonomy coherence checks,
provenance tracking, taxonomy version control
```

## Pipeline Stage Status

| Stage | Tool | Status | Tests |
|-------|------|--------|-------|
| 0 Intake | `tools/intake.py` | ✅ Complete | `tests/test_intake.py` |
| 0.5 Enrichment | `tools/enrich.py` | 🟡 Basic | `tests/test_enrich.py` |
| 1 Normalization | `tools/normalize_shamela.py` | ✅ Complete | `tests/test_normalization.py` |
| 2 Structure Discovery | `tools/discover_structure.py` | ✅ Complete | `tests/test_structure_discovery.py` |
| 3+4 Extraction | `tools/extract_passages.py` | ✅ Multi-model consensus | `tests/test_extraction.py` |
| 3+4 Consensus | `tools/consensus.py` | ✅ Complete | `tests/test_consensus.py` |
| 5 Taxonomy Trees | `taxonomy/*.yaml` | ✅ All 4 sciences (892 leaves) | — |
| 6 Taxonomy Evolution | `tools/evolve_taxonomy.py` | ✅ Phase A + B (signal detect, LLM propose, apply, rollback, multi-model consensus) | `tests/test_evolution.py` |
| 7 Assembly + Distribution | `tools/assemble_excerpts.py` | ✅ Complete | `tests/test_assembly.py` |
| — Human Gate | `tools/human_gate.py` | ✅ Complete (corrections, replay, patterns, checkpoints) | `tests/test_human_gate.py` |
| — Cross-Validation | `tools/cross_validate.py` | ✅ Complete (placement, self-containment, cross-book) | `tests/test_cross_validate.py` |

**Extraction verified on إملاء and عقيدة.** إملاء: 5 passages (P004, P005, P006, P010, P020) with Claude + GPT-4o consensus. عقيدة: 10 passages from العقيدة الواسطية — full E2E pipeline (intake → normalize → discover → extract → assemble → evolve). Other sciences have taxonomy trees but extraction is untested against them.

**Not yet built:**
- Enrichment extension (intelligent author scholarly context research)
- Quality scoring and provenance tracking

## Running Things

```bash
# Unit tests (1024 pass, ~35s)
python -m pytest tests/ -q

# Single test file
python -m pytest tests/test_consensus.py -q

# Extraction dry run (no API needed)
python tools/extract_passages.py \
  --passages books/imla/stage2_output/passages.jsonl \
  --pages books/imla/stage1_output/pages.jsonl \
  --taxonomy taxonomy/imlaa_v0.1.yaml \
  --book-id qimlaa --book-title "قواعد الإملاء" --science imlaa \
  --gold 3_extraction/gold/P004_gold_excerpt.json \
  --output-dir output/imlaa_extraction --dry-run

# Single-model extraction (Anthropic only)
export ANTHROPIC_API_KEY="sk-ant-..."
python tools/extract_passages.py \
  --passages books/imla/stage2_output/passages.jsonl \
  --pages books/imla/stage1_output/pages.jsonl \
  --taxonomy taxonomy/imlaa_v0.1.yaml \
  --book-id qimlaa --book-title "قواعد الإملاء" --science imlaa \
  --gold 3_extraction/gold/P004_gold_excerpt.json \
  --output-dir output/imlaa_extraction \
  --passage-ids P004

# Multi-model consensus extraction (Claude + GPT-4o)
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-proj-..."
PYTHONIOENCODING=utf-8 PYTHONPATH=. python tools/extract_passages.py \
  --passages books/imla/stage2_output/passages.jsonl \
  --pages books/imla/stage1_output/pages.jsonl \
  --taxonomy taxonomy/imlaa_v0.1.yaml \
  --book-id qimlaa --book-title "قواعد الإملاء" --science imlaa \
  --gold 3_extraction/gold/P004_gold_excerpt.json \
  --output-dir output/imlaa_consensus \
  --models claude-sonnet-4-5-20250929,gpt-4o \
  --passage-ids P004

# Assembly + folder distribution (no API needed)
PYTHONIOENCODING=utf-8 PYTHONPATH=. python tools/assemble_excerpts.py \
  --extraction-dir output/imlaa_extraction \
  --intake-metadata books/imla/intake_metadata.json \
  --taxonomy taxonomy/imlaa_v0.1.yaml \
  --science imlaa \
  --output-dir output/imlaa_assembled \
  --dry-run
```

**Windows notes:** Set `PYTHONIOENCODING=utf-8` (Windows console defaults to cp1252, which can't encode Arabic). Set `PYTHONPATH=.` so `from tools.consensus import ...` resolves correctly.

**API extraction runs should use a virtual environment** to avoid polluting the project:
```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install PyYAML httpx
```

## Dependencies

```bash
pip install PyYAML httpx
```

Python 3.11+ required. API keys needed: `ANTHROPIC_API_KEY` (required for Claude models), `OPENAI_API_KEY` (for GPT models in consensus mode), `OPENROUTER_API_KEY` (optional, for OpenRouter-prefixed models).

## Key Files to Read

**Start here (in order):**
1. This file
2. `REPO_MAP.md` — full directory structure explanation
3. `4_excerpting/EXCERPT_DEFINITION.md` — **single source of truth** for what an excerpt IS (needs updating to match current vision)
4. `3_extraction/RUNBOOK.md` — running the extraction pipeline

**Extraction & consensus (read when working on extraction):**
- `tools/extract_passages.py` — main extraction pipeline (2115 lines), multi-model support
- `tools/consensus.py` — consensus comparison engine (1722 lines)

**Assembly & distribution (read when working on assembly):**
- `tools/assemble_excerpts.py` — self-contained excerpt assembly + folder distribution (~530 lines)

**Taxonomy evolution (read when working on evolution):**
- `tools/evolve_taxonomy.py` — signal detection, LLM proposal generation, apply proposals, excerpt redistribution, rollback, multi-model consensus (~2280 lines)

**Human gate (read when working on review/corrections):**
- `tools/human_gate.py` — correction persistence, correction replay, pattern detection, gate checkpoints (~570 lines)

**Cross-validation (read when working on validation):**
- `tools/cross_validate.py` — placement cross-validation, self-containment validation, cross-book consistency (~530 lines)

**Specs (read when working on a specific stage):**
- `0_intake/INTAKE_SPEC.md`
- `1_normalization/NORMALIZATION_SPEC_v0.5.md`
- `2_structure_discovery/STRUCTURE_SPEC.md`
- `3_atomization/ATOMIZATION_SPEC.md` (superseded by automated tool — reference only)
- `4_excerpting/EXCERPT_DEFINITION.md` — the most important spec
- `4_excerpting/EXCERPTING_SPEC.md`

**Binding authority (overrides stage specs when in conflict):**
- `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md`
- `2_atoms_and_excerpts/checklists_v0.4.md`

**Gold baselines (hand-crafted ground truth for بلاغة):**
- `gold_baselines/jawahir_al_balagha/passage1_v0.3.13/` — 21 excerpts, start here
- `3_extraction/gold/P004_gold_excerpt.json` — gold for إملاء extraction

**Taxonomy:**
- `taxonomy/imlaa/imlaa_v1_0.yaml` — إملاء taxonomy (105 leaves)
- `taxonomy/sarf/sarf_v1_0.yaml` — صرف taxonomy (226 leaves)
- `taxonomy/nahw/nahw_v1_0.yaml` — نحو taxonomy (226 leaves)
- `taxonomy/balagha/balagha_v1_0.yaml` — بلاغة taxonomy (335 leaves)
- `taxonomy/aqidah/aqidah_v0_2.yaml` — عقيدة taxonomy (28 leaves, evolved from v0.1)
- `taxonomy/aqidah/aqidah_v0_1.yaml` — عقيدة taxonomy v0.1 (21 leaves, superseded by v0.2)
- Historical: `imlaa_v0.1.yaml` (44 leaves), `balagha_v0_2` through `v0_4` (143 leaves)

## Architecture Patterns

**Stage I/O chain:** Each stage reads the previous stage's output. Books are registered in `books/` with `intake_metadata.json`. Normalization produces `pages.jsonl`. Structure discovery produces `passages.jsonl` + `divisions.json`. Extraction produces `atoms` + `excerpts` per passage. Assembly produces self-contained excerpt files. Distribution places them in the taxonomy folder tree.

**Multi-book convergence:** Multiple books from different authors feed excerpt files into the same taxonomy folder tree (one tree per science). A leaf folder may contain excerpts from several books. Every excerpt must carry enough context for the synthesis LLM to attribute views to specific authors.

**LLM calls:** Tools call Claude/OpenAI APIs directly via httpx with 3-way dispatch: Anthropic direct (default), OpenAI direct (models starting with `gpt-`/`o1-`/`o3-`/`o4-`), or OpenRouter (models containing `/`). `_resolve_key_for_model()` ensures each call gets the correct provider's API key. API keys via env vars `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`. LLM-dependent stages gracefully degrade if API fails mid-run.

**Multi-model consensus:** `tools/consensus.py` compares two model outputs using text-overlap matching (character 5-gram Jaccard with diacritics stripping). Excerpt pairs are classified as full agreement (same text + same taxonomy), placement disagreement (same text + different taxonomy), or unmatched. An LLM arbiter resolves disagreements with detailed Arabic linguistic reasoning. Per-model raw outputs are saved alongside the consensus result for auditability.

**Validation layers:**
- **Algorithmic checks:** Schema validation, atom coverage, reference integrity, character count verification, range monotonicity — fast, deterministic, catch mechanical errors.
- **LLM-based validation:** Self-containment verification, placement cross-validation, cross-book consistency, taxonomy coherence — require content understanding.
- **Human gates:** After extraction and taxonomy evolution. Feedback saved and used for system self-improvement.

**Testing:** pytest, no fixtures framework. Tests are self-contained with inline data. Test files mirror tool files: `test_normalization.py` tests `normalize_shamela.py`.

**Text handling:** All Arabic text is verbatim — never corrected, never normalized in the primary representation. A separate `normalized_text` field exists for search/matching. Diacritics preserved exactly as source.

## Code Conventions

- Python 3.11+, type hints used but not enforced
- CLI tools use argparse, not click
- JSONL for data, YAML for taxonomy, JSON for metadata/excerpts
- Markdown for human review reports
- All tools are standalone scripts in `tools/`, importable as modules
- Test with `python -m pytest`, not `pytest` directly (ensures correct path)
- All file I/O uses `encoding="utf-8"` explicitly (Windows defaults to cp1252)
- API extraction runs use a virtual environment (`.venv/`, gitignored)

## Current State and What to Work On

**What exists and works:**
- Stages 0–2 complete and tested (intake, enrichment, normalization, structure discovery)
- Extraction tool with multi-model consensus (2115 lines, `tools/extract_passages.py`)
- Consensus engine (1722 lines, `tools/consensus.py`) — text-overlap matching, LLM arbiter for disagreements, per-excerpt confidence scoring
- Assembly tool (`tools/assemble_excerpts.py`) — transforms extraction output into self-contained excerpt files placed in taxonomy folder tree
- Taxonomy evolution engine Phase A + B (`tools/evolve_taxonomy.py`) — signal detection (5 types), LLM proposal generation, apply approved proposals to YAML (v0 + v1 formats), excerpt redistribution, rollback capability, multi-model consensus for proposals, taxonomy registry version control
- Human gate infrastructure (`tools/human_gate.py`) — correction persistence (JSONL), correction replay (re-extract with correction context), pattern detection (recurring errors, model/node/passage analysis), gate checkpoints (reviewed/pending tracking per excerpt)
- Cross-validation layers (`tools/cross_validate.py`) — placement cross-validation (independent LLM re-checks placement), self-containment validation (algorithmic + LLM), cross-book consistency (topic coherence at multi-book leaves)
- 1024 tests pass across the full suite (~168 extraction, ~122 consensus, ~70 assembly, ~108 evolution, ~90 intake, ~46 human gate, ~34 cross-validation, ~96 structure discovery, ~80 normalization, ~13 utility tools)
- 3-way API dispatch: Anthropic direct, OpenAI direct, OpenRouter (model prefix routing)
- Live-validated on 5 إملاء passages (P004, P005, P006, P010, P020) with Claude + GPT-4o consensus
- All 4 core taxonomy trees complete: إملاء (105 leaves), صرف (226), نحو (226), بلاغة (335) — 892 total leaves
- عقيدة taxonomy v0.2 (28 leaves) — evolved from v0.1 (21 leaves) after E2E testing revealed granularity gaps

**What needs to be built (in priority order):**
1. Enrichment extension (intelligent author scholarly context research)
2. Quality scoring and provenance tracking

**Do NOT spend time on:**
- Building synthesis tooling — synthesis is external to this repo
- Building a GUI — CLI is sufficient for now (GUI is a future goal)
- Bulk-processing books — `books/` contains test cases for tool development
- Perfecting Stage 2 edge cases — wait until a book needs them

## Test Books

The books in `books/` are test cases for developing and validating the pipeline tools. They are not a production queue.

### Intaken Books (pipeline-ready)

```
books/
├── imla/          # قواعد الإملاء (77p, إملاء) — primary test book, has Stage 1+2 outputs
├── wasitiyyah/    # العقيدة الواسطية (32p, عقيدة) — E2E test for new science, has Stage 1+2 outputs
├── shadha/        # شذا العرف (187p, صرف) — next test target (different science)
├── jawahir/       # جواهر البلاغة (بلاغة) — gold baseline source
├── qatr/          # قطر الندى (نحو)
├── ibn_aqil/      # شرح ابن عقيل (نحو)
├── miftah/        # مفتاح العلوم (بلاغة)
├── dalail/        # دلائل الإعجاز (بلاغة)
└── books_registry.yaml  — canonical registry of all intaken books
```

### Available Shamela Exports (raw, not yet intaken)

`books/Other Books/` contains a large library of raw Shamela HTML exports organized by science category. These are **ready to be intaken** through the pipeline using `tools/intake.py`. They are gitignored (large binary files) but present locally for test and development use.

```
books/Other Books/
├── كتب العقيدة/           # 804 books (عقيدة — creed/theology)
├── كتب الفقه الحنبلي/     # 147 books (فقه حنبلي — Hanbali jurisprudence)
├── كتب البلاغة/           # بلاغة — rhetoric
├── كتب النحو والصرف/      # نحو + صرف — grammar & morphology
└── كتب اللغة/             # لغة — Arabic language/lexicography
```

To intake a new book from this collection, use `tools/intake.py` with the path to the `.htm` file. See `0_intake/INTAKE_SPEC.md` for details.

## Gotchas

- **`2_atoms_and_excerpts/` is NOT Stage 2.** It's the precision rules folder (binding decisions, checklists). Stage 2 is `2_structure_discovery/`. Hardcoded paths — don't rename.
- **`3_atomization/` and `3_extraction/` both exist.** `3_atomization/` is the old manual spec (superseded). `3_extraction/` is the current automated extraction.
- **`archive/` contains dead docs.** Old orientation files and deprecated precision versions. **Ignore entirely — reading these will cause confusion** with outdated binding decisions and checklists.
- **`4_excerpting/EXCERPT_DEFINITION.md` is the single source of truth** for what an excerpt is. It needs updating to match the current vision (self-containment, taxonomy evolution). When updated, it overrides any conflicting information in stage specs.
- **Shamela HTML is uniform**: All exports use the same template. No structural variants.
- **Page numbering**: Multi-volume books may restart numbering per volume. `seq_index` is always monotonic.
- **Binding decisions override specs**: `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` wins over stage specs.
- **Gold baselines are for بلاغة only**: Hand-crafted for بلاغة. إملاء has simpler discourse structure.
- **`__overview` leaves**: Parent taxonomy nodes that receive overview content need `__overview` companion leaves.
- **Passage boundaries are guidance**: Stage 2 passages are structural suggestions. Extraction may find content spanning passage boundaries.
- **Taxonomy YAML = folder structure**: Root = science name, branches = nested folders, leaves = excerpt file endpoints. `tools/assemble_excerpts.py` creates the actual folder tree.
- **Taxonomy is alive**: Trees evolve as books reveal finer distinctions. The tree serves excerpts, not the other way around.
- **Excerpting is content-driven**: Taxonomy has zero influence on excerpt boundaries. Excerpt first, place second, evolve third.
- **Author context gap**: `intake_metadata.json` `scholarly_context` fields are mostly null/auto. Enrichment needs extension.
- **Extraction verified on إملاء and عقيدة**: إملاء (5 passages with consensus) and عقيدة (10 passages, full E2E). Other sciences have taxonomy trees but are untested.
- **GPT-4o produces coarser excerpts**: On long passages (5+ pages), GPT-4o tends toward 1-2 mega-excerpts while Claude produces granular ones. The arbiter handles this correctly but cost increases with more unmatched excerpts.
- **Windows console encoding**: Always set `PYTHONIOENCODING=utf-8` when running extraction on Windows. The default cp1252 codec can't encode Arabic characters.
- **Module imports for consensus**: Set `PYTHONPATH=.` when running `tools/extract_passages.py` so that `from tools.consensus import ...` resolves correctly.
