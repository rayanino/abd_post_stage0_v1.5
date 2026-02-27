# CLAUDE.md — Arabic Book Digester (ABD)

## What This Is

A pipeline that transforms Shamela HTML exports of classical Arabic books into structured excerpts placed in taxonomy trees. Four sciences: إملاء (orthography), صرف (morphology), نحو (syntax), بلاغة (rhetoric). The excerpts feed a future synthesis LLM that produces encyclopedia entries.

## Pipeline Stages

| Stage | Tool | Status | Tests |
|-------|------|--------|-------|
| 0 Intake | `tools/intake.py` | ✅ Complete | `tests/test_intake.py` |
| 1 Normalization | `tools/normalize_shamela.py` | ✅ Complete | `tests/test_normalization.py` |
| 2 Structure Discovery | `tools/discover_structure.py` | ✅ Complete | `tests/test_structure_discovery.py` |
| 3+4 Extraction | `tools/extract_passages.py` | 🟡 Vertical slice done | Needs tests |
| 5 Taxonomy Placement | (implicit in Stage 3+4) | 🟡 Basic | — |
| 6 Synthesis | — | ⬜ Not started | — |

## Running Things

```bash
# Tests (389 pass, ~20s)
python -m pytest tests/ -q

# Single test file
python -m pytest tests/test_structure_discovery.py -q

# Extraction dry run (no API needed)
python tools/extract_passages.py \
  --passages /path/to/passages.jsonl \
  --pages /path/to/pages.jsonl \
  --taxonomy taxonomy/imlaa_v0.1.yaml \
  --book-id qimlaa --book-title "قواعد الإملاء" --science imlaa \
  --output-dir /tmp/output --dry-run

# Extraction with API
export ANTHROPIC_API_KEY="sk-ant-..."
# Same command without --dry-run
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
3. `3_extraction/RUNBOOK.md` — the current work: vertical slice through extraction

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

**Stage I/O chain:** Each stage reads the previous stage's JSONL output. Books are registered in `books/` with `intake_metadata.json`. Normalization produces `pages.jsonl`. Structure discovery produces `passages.jsonl` + `divisions.json`. Extraction produces `atoms` + `excerpts` per passage.

**LLM calls:** Tools call Claude/OpenAI APIs directly via httpx. API key passed as CLI arg or env var `ANTHROPIC_API_KEY`. LLM-dependent stages gracefully degrade if API fails mid-run (e.g., Stage 2 Pass 3b uses whatever Pass 3a produced).

**Validation:** Each tool has built-in validation. Extraction validates 6 invariants (atom coverage, reference integrity, leaf placement, etc.). Structure discovery validates range monotonicity, overlap, coverage.

**Testing:** pytest, no fixtures framework. Tests are self-contained with inline data. Test files mirror tool files: `test_normalization.py` tests `normalize_shamela.py`.

**Text handling:** All Arabic text is verbatim — never corrected, never normalized in the primary representation. A separate `normalized_text` field exists for search/matching. Diacritics preserved exactly as source.

## Code Conventions

- Python 3.11+, type hints used but not enforced
- CLI tools use argparse, not click
- JSONL for data, YAML for taxonomy, JSON for metadata
- Markdown for human review reports
- All tools are standalone scripts in `tools/`, importable as modules
- Test with `python -m pytest`, not `pytest` directly (ensures correct path)

## Current State and What to Work On

The vertical slice through Stages 3+4 proved the pipeline works end-to-end on قواعد الإملاء. Two passages extracted successfully with correct taxonomy placement.

**Immediate priorities (in order):**
1. Run full book extraction (46 passages, ~$1.50) and review quality
2. Fix the 2 minor prompt issues found in testing (placeholder atoms, coverage gaps)
3. Write tests for `extract_passages.py`
4. Build Stage 6: take excerpts at one taxonomy leaf → synthesize an encyclopedia entry
5. Run the pipeline on شذا العرف (صرف science) to test cross-science generalization

**Do NOT spend time on:**
- Perfecting Stage 2 edge cases (600+ heading chunking, structureless books, etc.) — wait until a book actually needs them
- Multi-judge consensus — single-pass extraction quality is sufficient for now
- Building review UIs — markdown review reports are good enough

## Registered Books

```
books/
├── imla/          # قواعد الإملاء (77p, إملاء) — vertical slice target
├── shadha/        # شذا العرف (187p, صرف) — next test target
├── jawahir/       # جواهر البلاغة (بلاغة) — gold baseline source
├── qatr/          # قطر الندى (نحو)
├── ibn_aqil/      # شرح ابن عقيل (نحو)
├── miftah/        # مفتاح العلوم (بلاغة)
├── dalail/        # دلائل الإعجاز (بلاغة)
└── Other Books/   # Raw Shamela exports (not yet intaked)
```

## Gotchas

- **Shamela HTML is uniform**: All 788 files use the same template. No structural variants.
- **Page numbering**: Multi-volume books may restart numbering per volume or use continuous pagination. `seq_index` is always monotonic.
- **Binding decisions override specs**: If `00_BINDING_DECISIONS_v0.3.16.md` says X and a stage spec says Y, binding decisions win.
- **Gold baselines are for بلاغة only**: The jawahir baselines are hand-crafted for بلاغة. إملاء has a simpler discourse structure (rules + examples, minimal scholarly disputes).
- **`__overview` leaves**: Parent taxonomy nodes that receive overview/framing content need `__overview` companion leaves (convention from the vertical slice).
- **Passage boundaries are guidance**: Stage 2 passages are structural suggestions. Extraction may find content that spans passage boundaries (prose_tail detection handles this).
