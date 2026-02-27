# Extraction Runbook — قواعد الإملاء End-to-End

## What This Is

A complete pipeline from Shamela HTML → structured excerpts for one book (قواعد الإملاء, 77 pages, إملاء science). The tool (`tools/extract_passages.py`, 1389 lines) handles atomization, excerpting, taxonomy placement, post-processing, validation (17 checks), and correction retries in a single automated pass per passage.

## Pipeline Status

| Stage | Status | Output |
|-------|--------|--------|
| Stage 0: Intake | ✅ Complete | Book registered, metadata frozen |
| Stage 1: Normalization | ✅ Complete | `books/imla/stage1_output/pages.jsonl` (77 pages, matn+footnotes separated) |
| Stage 2: Structure Discovery | ✅ Complete | `books/imla/stage2_output/passages.jsonl` (46 passages) |
| Stage 3+4: Extraction | ✅ Complete | Tool built, tested (80 tests), verified on 5 passages with real API |
| Stage 5: Taxonomy Placement | ✅ Complete | Taxonomy node assigned per-excerpt during extraction |
| Stage 6: Synthesis | ⬜ Future | Uses excerpts as input to produce encyclopedia entries |

## End-to-End Verification Results

Tested on 5 diverse passages with real Claude API calls:

| Passage | Pages | Atoms | Excerpts | Fn Excerpts | Validation | Retries | Cost |
|---------|-------|-------|----------|-------------|------------|---------|------|
| P004 | 1p | 5 | 2 | 1 | pass | 0 | $0.07 |
| P005 | 2p | 9 | 3 | 2 | pass | 0 | $0.12 |
| P006 | 3p | 17 | 5 | 1 | pass | 0 | $0.16 |
| P010 | 5p | 23 | 9 | 0 | pass | 0 | $0.23 |
| P020 | 1p | 5 | 2 | 1 | pass | 0 | $0.07 |

All pass with 0 errors, 0 warnings, 0 retries.

## What You Need

1. **API key** with credits (Anthropic). Set it:
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

2. **httpx** installed:
   ```bash
   pip install httpx
   ```

3. **Stage 2 outputs** in `books/imla/`:
   - `books/imla/stage1_output/pages.jsonl` — normalized pages (77 pages)
   - `books/imla/stage2_output/passages.jsonl` — passage boundaries (46 passages)
   - `books/imla/stage2_output/divisions.json` — structural divisions

## How to Run

### Option 1: Single passage test (~$0.07–0.23)

```bash
python tools/extract_passages.py \
  --passages books/imla/stage2_output/passages.jsonl \
  --pages books/imla/stage1_output/pages.jsonl \
  --taxonomy taxonomy/imlaa_v0.1.yaml \
  --book-id qimlaa \
  --book-title "قواعد الإملاء" \
  --science imlaa \
  --gold 3_extraction/gold/P004_gold_excerpt.json \
  --output-dir output/imlaa_extraction \
  --passage-ids P004
```

### Option 2: Multiple specific passages

```bash
python tools/extract_passages.py \
  --passages books/imla/stage2_output/passages.jsonl \
  --pages books/imla/stage1_output/pages.jsonl \
  --taxonomy taxonomy/imlaa_v0.1.yaml \
  --book-id qimlaa \
  --book-title "قواعد الإملاء" \
  --science imlaa \
  --gold 3_extraction/gold/P004_gold_excerpt.json \
  --output-dir output/imlaa_extraction \
  --passage-ids P004,P005,P006
```

### Option 3: Full book (~$3–5)

```bash
python tools/extract_passages.py \
  --passages books/imla/stage2_output/passages.jsonl \
  --pages books/imla/stage1_output/pages.jsonl \
  --taxonomy taxonomy/imlaa_v0.1.yaml \
  --book-id qimlaa \
  --book-title "قواعد الإملاء" \
  --science imlaa \
  --gold 3_extraction/gold/P004_gold_excerpt.json \
  --output-dir output/imlaa_extraction
```

### Option 4: Dry run (inspect prompts, $0)

Add `--dry-run` to any command. Saves the full system+user prompt to the output dir for inspection.

### Additional flags

- `--max-retries N` — number of correction retries on validation failure (default 2)
- `--model MODEL` — Claude model to use (default: `claude-sonnet-4-20250514`)
- `--passage-ids P004,P010` — comma-separated passage IDs to process

## What You Get

For each passage, the tool produces:

```
output/imlaa_extraction/
├── P001_extraction.json     # Atoms + excerpts + footnote_excerpts + exclusions
├── P001_review.md           # Human-reviewable report with validation status
├── P002_extraction.json
├── P002_review.md
├── ...
└── extraction_summary.json  # Totals, costs, issue counts, retry counts
```

### Extraction JSON structure

Each `_extraction.json` contains:
- `atoms[]` — with `atom_type`, `text`, `is_prose_tail`, `bonded_cluster_trigger`, `source_layer`, `record_type`, `book_id`
- `excerpts[]` — with `core_atoms[{atom_id, role}]`, `context_atoms[{atom_id, role}]`, `taxonomy_node_id`, `case_types[]`, `boundary_reasoning`, `relations[]`
- `footnote_excerpts[]` — lighter-weight excerpts for footnote content
- `exclusions[]` — records for headings and prose_tails excluded from excerpts
- `notes` — LLM's passage-level commentary

### Validation (17 Checks, 3 Severity Levels)

**Errors** (block acceptance, trigger retry):
1. Atom required fields (atom_id, atom_type, text)
2. Excerpt reference integrity (no dangling atom IDs)
3. Atom coverage (every non-heading, non-tail, non-footnote atom in exactly one excerpt as core)
4. No multi-core assignment
5. Missing required excerpt fields
6. Empty atom text

**Warnings** (trigger retry):
7. Bonding trigger presence on bonded_cluster atoms
8. Core atom role validation
9. Context atom role validation
10. case_types valid and non-empty
11. Layer isolation (all atoms in an excerpt share source_layer)
12. Leaf-only taxonomy placement
13. Heading never in excerpt core/context

**Info** (log only):
14. Atom ID format
15. Excerpt ID format
16. Relation type validation
17. Title uniqueness

## What to Look For in Review

When skimming the review reports:

1. **Atom boundaries**: Did the LLM correctly identify sentence breaks? Are bonded clusters justified with proper T1-T6 triggers?
2. **Taxonomy placement**: Is each excerpt at the right leaf node?
3. **Continuation tails**: Did the LLM correctly identify text that belongs to the previous passage?
4. **Coverage**: Every teaching sentence should appear in an excerpt. The validator catches gaps.
5. **Overview vs detail**: Framing sentences (like "للهمزة خمس حالات") should go to `__overview` nodes, not to specific case nodes.
6. **case_types**: Are the A1-E2 labels accurate for the content pattern?
7. **Relations**: Do split_continues_in / split_continued_from chains connect properly across passages?

## Known Limitations

1. **Taxonomy may need growth**: The starter taxonomy covers قواعد الإملاء's main structure. If the LLM maps to `_unmapped`, a new leaf is needed.
2. **Cross-page content**: Some passages span page boundaries where content flows mid-sentence. The tool handles this via `prose_tail` detection, but edge cases may need manual correction.
3. **No multi-judge yet**: Single LLM pass per passage (with correction retries). Production should use the multi-judge consensus from the spec.

## Next Steps

1. **Run full book extraction** (46 passages) and review quality
2. **Build Stage 6**: Take excerpts for one taxonomy leaf and synthesize an encyclopedia entry
3. **Run on شذا العرف** (صرف science): Test the same pipeline on a different science
4. **Scale**: Process the full corpus systematically

## Files

```
taxonomy/
└── imlaa_v0.1.yaml              # إملاء taxonomy (44 leaves)
3_extraction/
├── RUNBOOK.md                    # This file
└── gold/
    └── P004_gold_excerpt.json    # Gold sample (schema v0.3.3 format)
tools/
└── extract_passages.py           # Extraction CLI tool (1389 lines)
tests/
└── test_extraction.py            # 80 unit tests (879 lines)
```
