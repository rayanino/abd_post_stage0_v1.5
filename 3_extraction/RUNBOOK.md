# Vertical Slice Runbook — قواعد الإملاء End-to-End

## What This Is

A complete pipeline from Shamela HTML → structured excerpts for one book (قواعد الإملاء, 77 pages, إملاء science). This proves the full chain works before investing more time perfecting individual stages.

## What's Already Done

| Stage | Status | Output |
|-------|--------|--------|
| Stage 0: Intake | ✅ Complete | Book registered, metadata frozen |
| Stage 1: Normalization | ✅ Complete | `/tmp/imlaa_full.jsonl` (77 pages, matn+footnotes separated) |
| Stage 2: Structure Discovery | ✅ Complete | `/tmp/imlaa_stage2_v3/qawaid_imlaa_passages.jsonl` (46 passages) |
| Stage 3+4: Extraction | 🟡 Ready to run | Tool built, gold sample created, prompts verified |
| Stage 5: Taxonomy Placement | 📋 Implicit | Taxonomy node assigned per-excerpt during extraction |
| Stage 6: Synthesis | ⬜ Future | Uses excerpts as input to produce encyclopedia entries |

## What You Need

1. **API key** with credits (Anthropic). Set it:
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

2. **httpx** installed:
   ```bash
   pip install httpx
   ```

3. **Stage 2 outputs** in `/tmp/`:
   - `/tmp/imlaa_full.jsonl` — normalized pages
   - `/tmp/imlaa_stage2_v3/qawaid_imlaa_passages.jsonl` — passage boundaries

   If these don't exist, re-run Stage 1+2 normalization and structure discovery first.

## How to Run

### Option 1: Test on 2 passages first (~$0.06)

```bash
cd ABD

python tools/extract_passages.py \
  --passages /tmp/imlaa_stage2_v3/qawaid_imlaa_passages.jsonl \
  --pages /tmp/imlaa_full.jsonl \
  --taxonomy taxonomy/imlaa_v0.1.yaml \
  --book-id qimlaa \
  --book-title "قواعد الإملاء" \
  --science imlaa \
  --gold 3_extraction/gold/P004_gold_excerpt.json \
  --output-dir /tmp/imlaa_extraction \
  --passage-ids P004,P010
```

### Option 2: Full book (~$1.50)

```bash
python tools/extract_passages.py \
  --passages /tmp/imlaa_stage2_v3/qawaid_imlaa_passages.jsonl \
  --pages /tmp/imlaa_full.jsonl \
  --taxonomy taxonomy/imlaa_v0.1.yaml \
  --book-id qimlaa \
  --book-title "قواعد الإملاء" \
  --science imlaa \
  --gold 3_extraction/gold/P004_gold_excerpt.json \
  --output-dir /tmp/imlaa_extraction
```

### Option 3: Dry run (inspect prompts, $0)

Add `--dry-run` to either command. Saves prompts to output dir for inspection.

## What You Get

For each passage, the tool produces:

```
/tmp/imlaa_extraction/
├── P001_extraction.json     # Raw LLM output: atoms + excerpts
├── P001_review.md           # Human-reviewable report
├── P002_extraction.json
├── P002_review.md
├── ...
└── extraction_summary.json  # Totals, costs, issue counts
```

### Review Format (P004_review.md)

```markdown
# Extraction Review: P004 — الحالة الأولى: ترسم ألفاً

- Pages: 9–9 (1p)
- Atoms: 6
- Excerpts: 3
- Cost: ~$0.0280

## ✅ Validation: All checks passed

## Atoms
- 📌 `qimlaa:matn:000001` [heading] الْهَمْزَةُ وَسَطَ الْكَلِمَةِ
- 📝 `qimlaa:matn:000002` [prose_sentence] لِلْهَمْزَةِ فِي وَسَطِ الْكَلِمَةِ خَمْسُ حَالَاتٍ
- 🔗 `qimlaa:matn:000003` [bonded_cluster] 1 - أَنْ تُسَكَّنَ أَوْ تُفْتَحَ...

## Excerpts
### qimlaa:exc:000001: حالات الهمزة وسط الكلمة — تقسيم عام
- **Node:** `al_hamza_wasat_al_kalima__overview`
- **Core atoms:** qimlaa:matn:000002
...
```

## Validation Checks (Automatic)

The tool runs these checks on every passage:

1. **All atoms have required fields** (atom_id, type, text)
2. **All excerpt atom references are valid** (no dangling IDs)
3. **Every non-heading, non-tail atom appears in exactly one excerpt as core** (coverage)
4. **No atom is core in multiple excerpts** (no double-counting)
5. **All taxonomy placements are at leaf nodes** (not parent nodes)
6. **All excerpts have required fields** (boundary_reasoning, etc.)

Issues are flagged in the review reports. Zero issues = ready for human skim.

## Cost Estimate

| Scope | Passages | Est. Cost |
|-------|----------|-----------|
| 2 test passages | 2 | ~$0.06 |
| Full book | 46 | ~$1.50 |
| With Opus instead of Sonnet | 46 | ~$7.50 |

Uses Claude Sonnet by default. For higher quality on difficult passages, add `--model claude-opus-4-5-20250514`.

## What to Look For in Review

When skimming the review reports:

1. **Atom boundaries**: Did the LLM correctly identify sentence breaks? Are bonded clusters justified?
2. **Taxonomy placement**: Is each excerpt at the right leaf node?
3. **Continuation tails**: Did the LLM correctly identify text that belongs to the previous passage?
4. **Coverage**: Every teaching sentence should appear in an excerpt. The validator catches gaps.
5. **Overview vs detail**: Framing sentences (like "للهمزة خمس حالات") should go to `__overview` nodes, not to specific case nodes.

## Known Limitations

1. **Taxonomy may need growth**: The starter taxonomy covers قواعد الإملاء's main structure. If the LLM maps to `_unmapped`, a new leaf is needed.
2. **Cross-page content**: Some passages span page boundaries where content flows mid-sentence. The tool handles this via `prose_tail` detection, but edge cases may need manual correction.
3. **Footnotes**: Currently extracted but not yet processed through the full excerpt pipeline. Footnote excerpts are a lighter-weight format.
4. **No multi-judge yet**: Single LLM pass per passage. Production should use the multi-judge consensus from the spec.

## After Running

1. **Skim the review reports** — focus on passages with validation issues first
2. **Check `_unmapped` placements** — these indicate taxonomy gaps
3. **Compare P004 output against the gold sample** (`3_extraction/gold/P004_gold_excerpt.json`)
4. **Decide**: Is quality sufficient to proceed to Stage 6 (synthesis), or does the extraction prompt need tuning?

## Next Steps After Vertical Slice

Once you've validated that excerpts look correct:

1. **Build Stage 6**: Take excerpts for one taxonomy leaf and synthesize an encyclopedia entry
2. **Run on شذا العرف** (صرف science): Test the same pipeline on a different science
3. **Port to Claude Code**: Move iterative development there for faster cycles
4. **Scale**: Process the full corpus systematically

## Files Created

```
ABD/
├── taxonomy/
│   └── imlaa_v0.1.yaml              # إملاء taxonomy (44 leaves)
├── 3_extraction/
│   ├── gold/
│   │   └── P004_gold_excerpt.json    # Hand-crafted gold sample
│   └── prompts/
│       └── extract_v0.1.py           # Prompt templates (reference)
└── tools/
    └── extract_passages.py           # Extraction CLI tool
```
