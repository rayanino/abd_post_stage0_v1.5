# Stage 2 Guidelines — What It Needs and What's Hard

## What Stage 2 must accomplish

Stage 1 delivers a flat sequence of normalized pages. Stage 2 must transform that into a hierarchical structure with defined passage boundaries. A **passage** is the unit of work for everything downstream (atomization, excerpting, taxonomy placement).

Concretely, for each book, Stage 2 must produce:
1. A **division tree** — the book's internal structure (باب, فصل, مبحث, etc.) with hierarchy
2. A **passage list** — contiguous page ranges assigned as work units for Stage 3
3. A **digestibility classification** — which divisions contain real teaching content vs editor apparatus

## What Stage 1 gives you to work with

Each page in the JSONL has:
- `matn_text` — the author's text (cleaned, faithful to source)
- `starts_with_zwnj_heading` — True for 15,814 pages where a double-ZWNJ marks a section heading
- `has_verse` — useful for identifying poetry sections
- `footnote_section_format` — tells you what kind of scholarly apparatus exists
- `warnings` — duplicate pages, orphan refs, etc.
- `seq_index` — the only reliable unique page ID (page numbers can duplicate)

Critically, Stage 1 does NOT give you:
- Any structural hierarchy (that's Stage 2's job)
- Any interpretation of what the ZWNJ headings mean in context
- Any parsing of bare-number footnotes into individual records (25K pages — you'll need LLM for these)

## The three-pass algorithm (from existing draft spec)

The draft spec (`2_structure_discovery/STRUCTURE_SPEC.md`) defines a three-pass approach:

**Pass 1 (Deterministic):** Extract HTML-tagged headings from `<span class="title">` in the frozen source HTML. Note: Stage 1 strips tags, so Pass 1 must read the original HTML, not the JSONL. The `structural_patterns.yaml` documents that double-quote `class="title"` spans are content headings (9,505 across 79 بلاغة files) while single-quote `class='title'` spans are metadata labels (685 across 79 files, all in the first PageText div). This differentiator is 100% reliable across the corpus.

**Pass 2 (Deterministic):** Keyword heuristic scan of normalized matn_text for division keywords (باب, فصل, مبحث, تقسيم, خاتمة, etc.) at line-start positions. Must filter false positives (mid-sentence keywords, citations, long lines).

**Pass 3 (LLM-assisted):** Fill gaps that Passes 1–2 missed. This is where the hard problems live.

## What's actually hard (and what the draft spec underspecifies)

### 1. Most books have untagged divisions

The draft spec acknowledges this but doesn't quantify it. From the corpus surveys: many books have sections where the author shifts topic without any tagged heading or keyword. The LLM must detect these implicit boundaries from content alone. This is fundamentally different from the deterministic work in Stages 0–1.

**Decision needed:** How much text does the LLM see per call? Full book? Chapter-by-chapter? What's the context window strategy for 500+ page books?

### 2. Hierarchy inference is ambiguous

The same keyword can appear at different hierarchy levels. In شذا العرف: `الباب الأول: في الفعل` (top-level) contains `التقسيم الأول` which contains `الباب الأول: فَعَلَ يَفعُل` (leaf-level). Same keyword "باب" at two different depths. The hierarchy is book-specific, not universal.

**Decision needed:** Is hierarchy inferred purely from the LLM's understanding of the text, or are there deterministic rules that can help? (The draft spec lists 5 inference rules in priority order — these need validation against real books.)

### 3. Digestibility is a judgment call

Which divisions are "digestible" (teaching content in one of our 4 sciences) vs "non-digestible" (editor introduction, table of contents, endorsements, bibliography)? The draft spec lists obvious cases but the boundary is fuzzy. An author's مقدمة might contain both praise and substantive definitions.

**Decision needed:** Is this a binary classification or a spectrum? Can the LLM handle this with a good prompt, or does it need examples?

### 4. Passage sizing requires merge/split logic

The draft spec says passages should be 2–15 pages. Short divisions (<1 page) should merge with neighbors. Long divisions (>30 pages) should split. But merge/split rules interact with never-merge constraints (never merge across different باب, different علم, exercises with teaching content).

**Decision needed:** Should merge/split happen in a separate sub-step after the division tree is built? Or should the LLM handle it during Pass 3?

### 5. LLM prompt design is entirely unspecified

The draft spec says "[TO BE SPECIFIED]" for the LLM prompt. This is the most important piece. The prompt must:
- Show the LLM the existing Pass 1+2 headings
- Provide enough text context for gap detection
- Request structured JSON output with division list + hierarchy + digestibility
- Handle books of vastly different sizes (50 pages to 3000+ pages)

### 6. The 25K bare-number footnote pages need handling

Stage 1 correctly captured the footnote content in `footnote_preamble` and classified these as `bare_number` format. But individual footnote records are empty. If Stage 2 needs footnote content for structure discovery (e.g., editor notes that say "this section begins here"), it will need to deal with unparsed footnote sections.

**Decision needed:** Does Stage 2 need individual footnote parsing? Or can it work from matn_text alone for structure discovery, deferring footnote parsing to Stage 3?

## Relationship to Stage 1 outputs

Stage 2 reads from TWO sources:
1. **Stage 1 JSONL** (`pages.jsonl`) — normalized text, footnotes, flags
2. **Frozen source HTML** (from Stage 0) — for Pass 1 HTML-tagged heading extraction

This is because Stage 1 intentionally strips HTML tags (its job is text extraction). But `<span class="title">` tags carry structural information that Stage 2 needs. The frozen HTML is the source of truth for these tags.

Stage 2 also needs:
- `intake_metadata.json` (Stage 0) — book metadata, science classification
- `structural_patterns.yaml` — keyword patterns and hierarchy rules
- `normalization_report.json` (Stage 1) — page counts, footnote stats for sanity checks

## What Stage 2 must deliver to Stage 3

Stage 3 (Atomization) expects:
- `divisions.json` — complete division tree with hierarchy, page ranges, digestibility flags
- `passages.jsonl` — one passage per line, with page range, content type, sizing notes
- `structure_report.json` — summary stats and review flags
- `structure_review.md` — human-readable review document

The passage list is the contract between Stage 2 and Stage 3. Each passage defines a contiguous page range that will be independently atomized and excerpted. Getting passage boundaries wrong means excerpts will be split at the wrong places or topics will be merged that shouldn't be.

## Recommended approach

1. **Start with corpus analysis** — before writing any code, survey the structural patterns across representative books from each science. The existing surveys cover بلاغة and some نحو/صرف, but are pre-Stage 1.

2. **Implement Pass 1 first** — it's deterministic and gives you a baseline to measure against. Validate against books where you can manually verify the division list.

3. **Implement Pass 2 second** — also deterministic. Measure how many divisions it adds beyond Pass 1. Measure false positive rate.

4. **Design Pass 3 carefully** — this is where most of the time should go. Start with a single book (jawahir is the most studied), get the prompt right, then test across diverse books.

5. **Build the passage constructor last** — once the division tree is solid, passage boundary logic is relatively straightforward.

6. **Gold samples needed** — just as Stage 1 has gold samples showing exact input→output, Stage 2 needs gold samples showing: "for this book, the correct division tree is X, and the correct passages are Y." Start with jawahir (already well-understood) and add 2-3 more.
