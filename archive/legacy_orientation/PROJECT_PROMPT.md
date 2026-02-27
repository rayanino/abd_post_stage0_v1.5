# ABD Project Prompt — Stage 2 Handoff

**Use this prompt when starting a new chat in this project to pick up where we left off.**

---

## What this project is

The Arabic Book Digester (ABD) is an automated pipeline that transforms Shamela HTML book exports into structured excerpts for four Arabic linguistic sciences: إملاء (orthography), صرف (morphology), نحو (syntax), بلاغة (rhetoric). The excerpts will later be consumed by a separate synthesis LLM to produce encyclopedic texts.

The pipeline has 7 stages (0–6). Stages 0 and 1 are complete and validated. Stage 2 is next.

## What is built and working

### Stage 0 — Intake (complete)
Freezes source HTML, extracts metadata, registers books. Implementation: `tools/intake.py`, tests: `tests/test_intake.py`. Spec: `0_intake/INTAKE_SPEC.md`.

### Stage 1 — Normalization (complete)
Transforms raw Shamela HTML into structured JSONL: one record per printed page, with separated matn/footnote layers. Implementation: `tools/normalize_shamela.py` (1120 lines), tests: `tests/test_normalization.py` (1940 lines, 198 tests). Spec: `1_normalization/NORMALIZATION_SPEC_v0.4.md` (needs bump to v0.5 for the latest round of fixes).

**Stage 1 has been stress-tested across the full corpus (788 files, 168K pages, 401 MB) through 2 rounds of adversarial analysis. Key guarantees:**

- Zero silent data loss: 168,038 PageText blocks → 168,038 accounted for
- Zero residual HTML tags in output
- Zero encoding issues (all files clean UTF-8)
- Byte-level Arabic text fidelity verified
- Shamela uses exactly ONE HTML template — no structural variants exist

**Stage 1 output schema (per page, schema_version 1.1):**
- `seq_index` — unique page ID within book (monotonic across volumes)
- `volume`, `page_number_arabic`, `page_number_int`
- `matn_text` — cleaned author's text (tag-stripped, fn refs removed, whitespace normalized)
- `footnotes` — list of `{number, text}` (only for `numbered_parens` format)
- `footnote_preamble` — text before first (N) marker, OR entire section for non-parens formats
- `footnote_section_format` — `"numbered_parens"` | `"bare_number"` | `"unnumbered"` | `"none"`
- `footnote_ref_numbers` — deduplicated sorted list of refs found in matn
- `has_verse`, `has_tables`, `starts_with_zwnj_heading`, `is_image_only`
- `warnings` — includes `DUPLICATE_PAGE`, `FN_PREAMBLE`, `FN_UNPARSED_SECTION`, `EMPTY_PAGE`, orphan refs/fns

**Stage 1 report includes:** page counts, footnote counts, character counts (matn/footnote/preamble), verse/table/image/ZWNJ/duplicate page counts, orphan cross-reference counts.

**Known accepted limitations (documented, non-blocking):**
- 25,189 pages have bare-number footnotes (classified but not parsed into individual records — deferred to Stage 2 where LLM can disambiguate)
- ~1,300 verse false positives remain (pages with real verse AND prose-etc patterns on same page)
- 1 ZWNJ false negative in 167K pages
- 88 pages with `//` verse separators not detected (deferred to Stage 2)

### Gold samples
14 samples from 5 books covering every edge case: standard footnotes, bare-number footnotes, unnumbered footnotes, no footnotes, verse (hemistich + star), tables, image-only, ZWNJ headings, duplicate page numbers, true preamble, 10+ footnotes, orphan footnotes, empty pages. All roundtrip-verified. See `1_normalization/gold_samples/`.

### Corpus
- `books/Other Books/كتب البلاغة/` — 78+ بلاغة books
- `books/Other Books/كتب النحو والصرف/` — 150+ نحو/صرف books  
- `books/Other Books/كتب اللغة/` — 79+ لغة books
- Plus registered intake books in `books/` (jawahir, shadha, qatr, etc.)
- `books/books_registry.yaml` — book metadata registry

## What is NOT built yet

Stages 2–6 have draft specs and survey documents but zero implementation:

- **Stage 2 — Structure Discovery** (NEXT): Find book divisions, build hierarchy, define passage boundaries
- **Stage 3 — Atomization**: Split passages into minimal auditable units (atoms)
- **Stage 4 — Excerpting**: Group atoms into excerpts, each teaching one subtopic
- **Stage 5 — Taxonomy**: Place excerpts into science taxonomy trees
- **Stage 6 — Validation/Packaging**: Final quality checks and output packaging

## Key files to read for Stage 2

**Essential (read before starting):**
1. `2_structure_discovery/STRUCTURE_SPEC.md` — draft spec (332 lines, status: least mature stage)
2. `2_structure_discovery/ZOOM_BRIEF.md` — identified gaps and deliverables
3. `2_structure_discovery/structural_patterns.yaml` — pattern library (validated across 157 files)
4. `2_structure_discovery/edge_cases.md`
5. `1_normalization/NORMALIZATION_SPEC_v0.4.md` — understand the input format

**Useful context:**
- `2_structure_discovery/MASTER_CORPUS_SURVEY.md` and per-science surveys
- `1_normalization/SHAMELA_HTML_REFERENCE.md` — complete HTML structure documentation
- `1_normalization/gold_samples/GOLD_SAMPLES.md` — what normalized pages look like
- `00_SESSION_CONTEXT.md` — project-level context
- `project_glossary.md` — term definitions
- `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` — binding rules

## Working principles established in Stages 0–1

1. **Precision over generality.** Every scenario must be precisely specified, not handled with "general approaches." Edge cases drive the spec.
2. **Corpus-driven decisions.** Systematic surveys across the full corpus before implementing. Patterns must be verified, not assumed.
3. **Build and validate one stage completely before moving to the next.** Stage 1 went through 2 rounds of adversarial analysis before being declared stable.
4. **Nothing assumed or left unchecked.** If a pattern is claimed universal, prove it across 788 files.
5. **Gold samples cover every edge case type.** Not just the easy path.
6. **Human gate = skim.** The LLM judge system means human involvement is limited to skimming, not detailed review.

## Technical setup

- Python 3.12+ (tools use type hints, f-strings, dataclasses)
- `tools/` directory for all implementations
- `tests/` directory for all test suites (pytest)
- LLM API calls: Claude and OpenAI, unlimited budget assumption
- All tools are CLI-based, called from project root
