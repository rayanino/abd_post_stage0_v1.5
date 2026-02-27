# CLAUDE.md — Arabic Book Digester (ABD)

## What This Is

A pipeline that transforms Shamela HTML exports of classical Arabic books into structured excerpts placed in taxonomy trees. Four sciences: إملاء (orthography), صرف (morphology), نحو (syntax), بلاغة (rhetoric).

**Downstream consumer:** The excerpts collected at each taxonomy leaf node are fed to an **external synthesis LLM** (outside this repo's scope) that produces encyclopedia entries. ABD's job ends at producing well-structured, accurately placed excerpts. Synthesis is not a stage of this application — but structural decisions within ABD (excerpt boundaries, taxonomy granularity, metadata richness, relation chains) must be made with that downstream LLM consumer in mind.

## Pipeline Stages

| Stage | Tool | Status | Tests |
|-------|------|--------|-------|
| 0 Intake | `tools/intake.py` | ✅ Complete | `tests/test_intake.py` |
| 1 Normalization | `tools/normalize_shamela.py` | ✅ Complete | `tests/test_normalization.py` |
| 2 Structure Discovery | `tools/discover_structure.py` | ✅ Complete | `tests/test_structure_discovery.py` |
| 3+4 Extraction | `tools/extract_passages.py` | ✅ Complete | `tests/test_extraction.py` |
| 5 Taxonomy Placement | (implicit in Stage 3+4) | ✅ Complete | — |

**Note:** There is no Stage 6 in this application. Synthesis is handled by an external LLM that consumes the excerpts at each taxonomy leaf. See "Downstream consumer" above.

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

# Extraction with API (full book, ~$1.50)
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

**Stage I/O chain:** Each stage reads the previous stage's JSONL output. Books are registered in `books/` with `intake_metadata.json`. Normalization produces `pages.jsonl`. Structure discovery produces `passages.jsonl` + `divisions.json`. Extraction produces `atoms` + `excerpts` per passage. The final output — excerpts grouped by taxonomy leaf — is the handoff point to the external synthesis LLM. Structural decisions (excerpt boundaries, metadata fields, relation chains) are made to serve that downstream consumer.

**LLM calls:** Tools call Claude/OpenAI APIs directly via httpx. API key passed as CLI arg or env var `ANTHROPIC_API_KEY`. LLM-dependent stages gracefully degrade if API fails mid-run (e.g., Stage 2 Pass 3b uses whatever Pass 3a produced).

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

## Current State and What to Work On

Stages 0–4 are complete and tested. The extraction tool has been rewritten against the binding decisions and gold standard schema v0.3.3, with 17-check validation, post-processing, and a correction retry loop. End-to-end verification on 5 diverse passages (P004, P005, P006, P010, P020) all pass with 0 errors and 0 retries.

**Immediate priorities (in order):**
1. Run full book extraction on قواعد الإملاء (46 passages, ~$3–5) and review quality
2. Run the pipeline on شذا العرف (صرف science) to test cross-science generalization
3. Scale to full corpus

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

- **`2_atoms_and_excerpts/` is NOT Stage 2.** Despite the numbering, it's a precision rules folder (binding decisions, checklists, gold baselines) from the manual workflow. Stage 2 is `2_structure_discovery/`. See its README.md. Several tools have hardcoded paths to it — don't rename.
- **`3_atomization/` and `3_extraction/` both exist.** `3_atomization/` is the old spec for manual atomization. `3_extraction/` is the automated extraction (complete). The automated tool (`tools/extract_passages.py`, 1389 lines) combines atomization + excerpting + taxonomy placement into one LLM pass with post-processing and validation.
- **`archive/` contains dead docs.** Old orientation files (READ_FIRST, PROJECT_PROMPT, SESSION_CONTEXT) and deprecated precision versions. Ignore entirely.
- **Shamela HTML is uniform**: All 788 files use the same template. No structural variants.
- **Page numbering**: Multi-volume books may restart numbering per volume or use continuous pagination. `seq_index` is always monotonic.
- **Binding decisions override specs**: If `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` says X and a stage spec says Y, binding decisions win.
- **Gold baselines are for بلاغة only**: The jawahir baselines are hand-crafted for بلاغة. إملاء has a simpler discourse structure (rules + examples, minimal scholarly disputes).
- **`__overview` leaves**: Parent taxonomy nodes that receive overview/framing content need `__overview` companion leaves (convention from the vertical slice).
- **Passage boundaries are guidance**: Stage 2 passages are structural suggestions. Extraction may find content that spans passage boundaries (prose_tail detection handles this).
