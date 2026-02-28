# ABD Architectural Vision

**Version:** 2.0
**Status:** Active — this document defines the target architecture for the Arabic Book Digester.
**Date:** 2026-02-28

---

## Authority

This document defines the architectural direction of ABD. It governs structural decisions — what parts of the system exist, what boundaries they have, what each part's responsibilities are, and in what sequence features are built.

This document does **not** override the operational authority hierarchy for content decisions (binding decisions → gold standard schema → glossary → checklists → extraction protocol → gold baselines → stage specs). It sits alongside that hierarchy as the structural counterpart: content rules govern what the pipeline *produces*; this document governs how the pipeline is *organized*.

When a stage spec or tool implementation conflicts with the architectural boundaries defined here, this document takes precedence on matters of system structure.

---

## 1. What ABD Is

ABD is a system that builds a comprehensive, structured knowledge base of the classical Arabic linguistic sciences. It does this by finding source material (books, online scholarly content, recorded lectures, and other formats), extracting self-contained teaching units from that material, and placing each unit at the correct location in a taxonomy tree — one tree per science.

The four sciences are:

| ID | Arabic | English | Base leaves |
|----|--------|---------|-------------|
| `imlaa` | علم الإملاء | Orthography | 105 |
| `sarf` | علم الصرف | Morphology | 226 |
| `nahw` | علم النحو | Syntax | 226 |
| `balagha` | علم البلاغة | Rhetoric | 335 |

The base taxonomy trees currently contain 892 leaf nodes across the four sciences. This number is not a constant — taxonomy trees are living structures that evolve as new source material reveals finer topic distinctions. When the system discovers that a leaf node covers multiple distinguishable sub-topics, the tree evolves: the leaf splits into finer sub-nodes, existing excerpts are redistributed, and the total leaf count grows. This taxonomy evolution is a defining characteristic of ABD, not an edge case. The goal is to populate every leaf with self-contained excerpts from multiple sources — books, online content, recorded lectures — by different scholars, so that each topic has comprehensive coverage from diverse scholarly perspectives.

**The synthesis step is NOT part of ABD.** A separate, external synthesis LLM (entirely outside this repository and outside this application's architecture) reads all excerpts at each leaf and produces a single encyclopedic entry aimed at Arabic-language students, presenting and attributing all scholarly positions. ABD has no code, no tooling, no stages, and no design related to synthesis itself. However, every design decision *within* ABD — excerpt boundaries, self-containment requirements, metadata richness, scholarly context, taxonomy granularity — is made to serve that downstream synthesis LLM so it can produce the best possible synthesizations. ABD's job ends at producing well-structured, accurately placed, self-contained excerpts. The quality of those excerpts is measured by how well a synthesis LLM could use them, even though synthesis is someone else's problem.

---

## 2. The End-State Vision

The long-term vision for ABD is a system that:

1. **Discovers** relevant source material across diverse source types — book libraries, online scholarly content, and recorded lectures.

2. **Acquires** that material programmatically wherever possible, falling back to guided manual acquisition where necessary.

3. **Normalizes** each source into a single canonical intermediate format, regardless of where it came from or what format it was in originally.

4. **Extracts** self-contained teaching units from the normalized content using multi-model LLM consensus, with human oversight at key checkpoints.

5. **Places** each teaching unit at the correct taxonomy leaf, evolving the taxonomy trees as new material reveals finer topic distinctions.

6. **Tracks coverage** across all taxonomy leaves (growing through evolution), prioritizing sources that fill gaps in under-covered areas.

This vision is realized incrementally. Not all of these capabilities exist today, and they are built in a deliberate sequence where each capability is proven before the next is started. See §7 (Implementation Strategy) for the sequencing.

---

## 3. The Architecture

ABD is organized into two major parts separated by one critical boundary. The **Source Pipeline** handles everything about finding, documenting, and preparing source material. The **Engine** handles everything about understanding the content, extracting teaching units, and populating the taxonomy. The **normalization boundary** between them is the single most important architectural constraint in the system.

```
╔═════════════════════════════════════════════════════════════╗
║                    SOURCE PIPELINE                          ║
║                                                             ║
║  ┌────────────────────────────────────────────────────────┐ ║
║  │  STEP 0.1: SOURCE GATHERING                           │ ║
║  │                                                        │ ║
║  │  Find and acquire raw source material.                │ ║
║  │  Output: frozen raw source files in native format.    │ ║
║  └───────────────────────┬────────────────────────────────┘ ║
║                          │                                  ║
║                          ▼                                  ║
║  ┌────────────────────────────────────────────────────────┐ ║
║  │  STEP 0.2: SOURCE INTAKE                              │ ║
║  │                                                        │ ║
║  │  Document the source: metadata, provenance, context.  │ ║
║  │  Living metadata — enriched over time as more is      │ ║
║  │  learned (during normalization, extraction, research). │ ║
║  │  Output: intake metadata (initial, grows over time).  │ ║
║  └───────────────────────┬────────────────────────────────┘ ║
║                          │                                  ║
║                          ▼                                  ║
║  ┌────────────────────────────────────────────────────────┐ ║
║  │  STEP 0.3: SOURCE NORMALIZATION                       │ ║
║  │                                                        │ ║
║  │  Convert raw source into the universal normalized     │ ║
║  │  structure. Includes structure discovery (headings,   │ ║
║  │  divisions, passage boundaries).                      │ ║
║  │                                                        │ ║
║  │  One normalizer per source format.                    │ ║
║  │  All normalizers produce identical output schema.     │ ║
║  │                                                        │ ║
║  │  Output: complete normalized package (pages,          │ ║
║  │          structure, passages) ready for the engine.   │ ║
║  └───────────────────────┬────────────────────────────────┘ ║
║                          │                                  ║
╚══════════════════════════╪══════════════════════════════════╝
                           │
              ═════════════╪═════════════  ← THE NORMALIZATION BOUNDARY
                           │                 (see §4)
                           │
╔══════════════════════════╪══════════════════════════════════╗
║                          ▼           ENGINE                 ║
║                                                             ║
║  ┌────────────────────────────────────────────────────────┐ ║
║  │  EXTRACTION                                            │ ║
║  │                                                        │ ║
║  │  Break normalized content into self-contained          │ ║
║  │  excerpts with taxonomy placement.                    │ ║
║  │  Atomization → Excerpting → Placement                 │ ║
║  │  Multi-model consensus, human gates, self-improvement │ ║
║  │                                                        │ ║
║  │  Input: ONLY the normalized package from Step 0.3     │ ║
║  │  Output: atoms, excerpts, placement decisions         │ ║
║  └───────────────────────┬────────────────────────────────┘ ║
║                          │                                  ║
║                          ▼                                  ║
║  ┌────────────────────────────────────────────────────────┐ ║
║  │  PLACEMENT                                             │ ║
║  │                                                        │ ║
║  │  Populate and evolve taxonomy trees.                  │ ║
║  │  Assemble self-contained excerpt files.               │ ║
║  │  Place files in taxonomy folder tree.                 │ ║
║  │  Detect evolution signals, propose tree changes.      │ ║
║  │  Track coverage across all taxonomy leaves.           │ ║
║  │                                                        │ ║
║  │  Output: populated taxonomy folder trees,             │ ║
║  │          coverage reports and gap analysis             │ ║
║  └────────────────────────────────────────────────────────┘ ║
║                                                             ║
╚═════════════════════════════════════════════════════════════╝
```

The intellectual core of ABD is the Engine — Extraction and Placement. This is where the value lives. The Source Pipeline is support infrastructure that feeds the engine. The system is designed so that improvements to the source pipeline have zero impact on the engine, and vice versa. The normalization boundary enforces this separation.

---

## 4. The Normalization Boundary

The single most important architectural constraint in ABD.

### 4.1 The rule

**Everything below the normalization boundary must be completely independent of the source format.** The Engine (Extraction and Placement) must never know or care whether the input came from a Shamela HTML export, a KetabOnline JSON download, a web article, a YouTube transcript, or any other source. It receives a normalized package conforming to a defined schema, and that is the entirety of its contract with the source pipeline.

Conversely, **everything above the normalization boundary is format-specific by design.** The source pipeline deals with the messy reality of diverse source formats. Each format gets its own normalizer. The normalizers are expected to differ wildly from each other — that's fine. The whole point is that this complexity is contained in the source pipeline and doesn't leak into the engine.

### 4.2 What crosses the boundary

The normalization boundary is defined by the output schema of Step 0.3 (Source Normalization). This is the contract that all normalizers must produce and that the engine consumes. The exact schema is to be specified when Step 0.3 is designed in detail, but it must include at minimum:

**Normalized pages** — content broken into sequential units, each carrying:
- Source identity (which source this came from, via a source-agnostic ID)
- Sequential ordering (monotonically increasing index)
- Page/position reference (physical page numbers where applicable, null where not)
- Main body text, cleaned and normalized
- Footnotes and annotations, separated from main text
- Content-type classification and structural markers

**Structural divisions** — the source's internal hierarchy:
- Division identifiers, titles, heading paths, nesting levels
- Mapped to page ranges via sequential index

**Passage boundaries** — processing units derived from the structural analysis:
- Passage identifiers with start/end positions (referencing normalized pages)
- Content type, digestibility classification
- Predecessor/successor linking for sequential processing

The current implementation uses `pages.jsonl`, `divisions.json`, and `passages.jsonl` with specific field schemas (see `spec/normalization_contract_v0.1.md` and the existing Stage 1/Stage 2 outputs for the current format). These schemas will be formalized and potentially revised when Step 0.3 is specified in detail to ensure they are genuinely source-agnostic and support all source types.

These schemas constitute the normalization contract. Any source type added to ABD must have a normalizer in Step 0.3 that produces output conforming to these schemas. The schemas may evolve over time, but changes must be coordinated across all normalizers — they always produce the same output format.

### 4.3 What must NOT cross the boundary

The following must never appear in or be assumed by the Engine (Extraction or Placement):

- Source format names (Shamela, KetabOnline, HTML, JSON, etc.)
- Source-specific structural markers (`<div class='PageText'>`, `<span class='title'>`, etc.)
- Source-specific metadata field names or conventions
- Assumptions about how page numbers are encoded in the raw source
- Assumptions about how footnotes are formatted in the raw source
- File paths or references to frozen source files
- Any logic that would produce different results depending on which source format produced the normalized data

### 4.4 Known boundary violation (current state)

**Structure discovery (`tools/discover_structure.py`) currently sits outside the source pipeline as a separate stage (Stage 2) that violates the normalization boundary.** It takes a `--html` argument pointing to the raw frozen Shamela HTML and uses it for Pass 1 heading extraction, directly parsing `<span class="title">` tags and `<span class='PageNumber'>` spans from the source HTML.

Under the new architecture, structure discovery belongs inside Step 0.3 (Source Normalization). The heading information that structure discovery extracts from raw HTML must be captured during normalization as part of building the normalized package. This means each source format's normalizer is responsible for both page-level normalization AND structural analysis, producing the complete normalized package (pages + divisions + passages) that the engine consumes.

This restructuring is a prerequisite for adding any second source format. The exact design will be specified when Step 0.3 is designed in detail.

---

## 5. Step Specifications

### 5.1 Step 0.1: Source Gathering

**Responsibility:** Find and acquire raw source material relevant to the four Arabic sciences. Get it into a format that the application can work with for the next step.

**Input:** The outside world — book libraries, websites, recordings, manual user input.

**Output:** A frozen raw source file (or set of files) in one of the application's supported source formats. "Frozen" means immutable from this point forward — neither Step 0.2 nor Step 0.3 may modify the raw source. The source is frozen immediately upon acquisition, before any documentation or processing begins.

**Key characteristics:**

This step is purely about finding and acquiring — locating a piece of relevant knowledge and getting it into the application's hands. It does not analyze content, extract metadata from content, or transform format. It simply answers: "here is a source that has relevant knowledge, and here is the raw material."

The application defines a set of **supported source formats** — the formats it knows how to work with in subsequent steps. Each supported format corresponds to a normalizer in Step 0.3. Adding a new source format to the application means building a new normalizer, and is therefore a deliberate decision — not every format on the internet is automatically supported.

For each supported source format, this step must specify **how the raw material is handled**: is a web article downloaded as an HTML file? Is it accessed directly and saved as plain text? Is a recording downloaded or streamed? These are source-format-specific decisions that determine what the frozen source looks like.

The current state is fully manual: the user downloads a Shamela HTML export and provides a file path. This remains a valid acquisition method permanently — manual input is one source adapter among many, and serves as the fallback when no programmatic adapter exists.

**Deduplication:** The system must know what sources have already been acquired and must not re-acquire them. The mechanism for this is to be specified when this step is designed in detail.

**What this step does NOT do:** It does not read or analyze the content of the source. It does not extract metadata from the content. It does not assess quality. It does not transform the format. It simply acquires and freezes.

### 5.2 Step 0.2: Source Intake

**Responsibility:** Document the source — comprehensively record everything knowable about it, so that downstream stages and the eventual external synthesis have full context about where this knowledge came from.

**Input:** A frozen raw source from Step 0.1.

**Output:** Intake metadata — a structured record documenting the source. This metadata is **living**: the initial documentation happens in this step, but the metadata continues to be enriched over the lifetime of the source as more information is learned:
- During Step 0.3 (normalization may reveal inconsistencies, encoding issues, structural patterns)
- During engine processing (extraction may reveal information about the author's positions or style)
- Through external research at any time (author biography, scholarly context, reputation)

**Key characteristics:**

This step is about documentation, not content processing. It answers: "what do we know about this source, independent of what the engine will extract from it?"

The metadata must include (at minimum — exact schema to be specified when this step is designed in detail):
- **Provenance:** Where the source came from, when it was acquired, the original URL or file path, how it was obtained
- **Identity:** Title, author, editor/publisher where applicable
- **Author context:** Biography, scholarly tradition, madhab, grammatical school, death/birth dates, geographic origin — critical for the external synthesis to distinguish and attribute scholarly positions. This information may be sparse initially and enriched over time through research.
- **Source characteristics:** Content type (book, article, lecture, etc.), language, encoding, approximate content length
- **Reputation and reliability:** The standing of the source — is it a classical reference text, a peer-reviewed encyclopedia, an informal blog post? This affects how the engine and downstream synthesis should weight its content.
- **Relevance:** Why this source is considered relevant to the four sciences. What sciences it covers. Why it was selected.
- **Dates:** When the content was written/published (not just when it was acquired)

**The metadata is living.** Step 0.2 captures the initial documentation, but the metadata record remains open for enrichment. Other steps may write back to it as they learn things. For example:
- Step 0.3 might discover encoding anomalies or structural irregularities and record them
- The engine might discover that the author takes a specific position on a grammatical debate, enriching the scholarly context
- A researcher (human or automated) might fill in the author's death date or madhab months after initial intake

The current `intake_metadata.json` and enrichment tool (`tools/enrich.py`) implement a version of this concept. The enrichment of author scholarly context is particularly important: it determines whether the external synthesis can properly attribute opinions to specific scholars and traditions.

**What this step does NOT do:** It does not process the content for extraction purposes. It may lightly parse the source to pull metadata fields (e.g., reading a title from an HTML metadata card, or extracting an author name from an API response), but it does not perform deep content analysis, identify teaching units, or understand the Arabic text. That is the engine's job.

### 5.3 Step 0.3: Source Normalization

**Responsibility:** Transform the raw source into the universal normalized structure that the engine consumes. This is the final step of the source pipeline and produces the input to the engine.

**Input:** A frozen raw source from Step 0.1, documented by intake metadata from Step 0.2.

**Output:** The complete **normalized package** — a set of files conforming to a universal schema that is identical regardless of source format. This package includes normalized pages, structural divisions, and passage boundaries. After this step, the source's native format is irrelevant — only the normalized package matters.

**Key characteristics:**

This step performs two major operations that are conceptually distinct but produce a single unified output:

1. **Content normalization:** Transform the raw source content into a clean, uniform page-level representation. Strip format-specific markup, normalize whitespace and encoding, separate footnotes from main text, handle format-specific quirks. This is deterministic and format-specific — each source format has its own normalizer.

2. **Structure discovery:** Analyze the content to identify the source's internal organization — headings, chapter boundaries, hierarchical divisions — and define passage boundaries that segment the content into units suitable for extraction. This may be deterministic, heuristic, or LLM-assisted depending on the source format and its structural clarity.

Both operations happen within the same step because they are tightly coupled: structural signals often exist in format-specific markup (e.g., HTML heading tags, JSON table-of-contents fields) that is only available before format stripping. By including structure discovery in normalization, each format's normalizer can use the richest possible information to determine structure, rather than trying to reconstruct structure from already-stripped text.

**One normalizer per source format.** Each supported source format has its own normalizer — a module that knows the specific challenges of that format and produces conformant output. Normalizer complexity is unlimited and self-contained: a normalizer can be thousands of lines, multiple passes, even LLM-assisted, as long as its output conforms to the universal schema. The complexity does not leak into the engine.

**All normalizers produce identical output.** The engine receives the same normalized package regardless of which normalizer produced it. The engine does not know and cannot determine which source format the data came from. This is the normalization boundary — the output schema of Step 0.3 defines it.

**Metadata enrichment.** Step 0.3 may discover things about the source that should be recorded in the intake metadata (from Step 0.2). For example: encoding inconsistencies, pages with unusual structure, content that appears corrupted, or structural patterns that reveal information about the source's organization. These discoveries are written back to the metadata, which is why the metadata is living.

**What this step does NOT do:** It does not understand the content at a semantic level. It does not identify teaching units, determine topic classifications, or make content decisions. It normalizes format and discovers structure — the intellectual work of content understanding belongs to the engine.

### 5.4 The Engine: Extraction

**Responsibility:** Take the normalized package and decompose its content into self-contained, accurately typed excerpts with taxonomy placement. This is the intellectual core of ABD — where content understanding happens.

**Input:** ONLY the normalized package from Step 0.3. The engine never touches raw source files, never reads source-format-specific data, and never behaves differently based on source provenance.

**Output:** Atoms (smallest indivisible text units), excerpts (self-contained teaching units composed of atoms), and placement decisions (which taxonomy leaf each excerpt belongs to).

**What the engine does, per passage:**

1. **Atomization:** Break the passage's text into typed atoms — the smallest indivisible units. Each atom has a type (definition, rule, example, evidence, introduction, transition, etc.), a source layer (matn, footnote, sharh), and precise character offsets.

2. **Excerpting:** Group atoms into self-contained teaching units. Each excerpt must be independently understandable — it carries everything the external synthesis LLM needs (full Arabic text, author identity, scholarly context, topic description). Excerpt boundaries come from the text's natural teaching structure, not from the taxonomy.

3. **Taxonomy placement:** Assign each excerpt to a taxonomy leaf node. This is a classification decision: given what this excerpt teaches, where does it belong in the tree?

4. **Evolution signal detection:** Flag cases where the taxonomy seems insufficiently granular for the content — a leaf that would need to receive two excerpts about distinguishably different sub-topics.

5. **Multi-model consensus:** Multiple LLMs perform steps 1–4 independently on the same input. Where they agree, confidence is high. Where they disagree, an arbiter LLM resolves with detailed reasoning, or the disagreement is escalated to human review.

6. **Validation:** Algorithmic checks verify mechanical correctness (atom coverage, reference integrity, character count verification, range monotonicity, schema compliance). LLM-based checks verify content quality (self-containment, placement accuracy).

**What the engine must never do:**
- Read or reference raw source files
- Assume anything about the source format
- Behave differently based on source provenance
- Modify the input text (faithful extraction, not editing)

### 5.5 The Engine: Placement

**Responsibility:** Assemble self-contained excerpt files, place them in the taxonomy folder tree, evolve the taxonomy as needed, and track coverage.

**Current state:** Base taxonomy trees exist for all 4 sciences (currently 892 leaves, expected to grow through evolution). Taxonomy evolution engine and assembly/distribution are not yet built.

**What this step does:**

1. **Excerpt assembly:** Take the raw extraction output (atoms + excerpts + placement decisions) and produce self-contained excerpt files. Each file embeds the full Arabic text, author identity, scholarly context, source reference, taxonomy path, and all metadata the external synthesis LLM needs. The file must be independently readable — no cross-references to other files.

2. **Folder distribution:** Place each excerpt file into its taxonomy leaf's folder. The taxonomy YAML maps directly to a directory tree. Multiple sources contribute files to the same leaf folder, building up multi-perspective coverage.

3. **Taxonomy evolution:** When extraction signals that a leaf node is too coarse (multiple distinguishably different sub-topics landing at the same leaf), this step:
   - Analyzes all excerpts at the affected node (from all sources processed so far)
   - Proposes new sub-nodes using multi-model consensus
   - Redistributes existing excerpts to the new sub-nodes
   - Validates: no orphaned excerpts, structure is coherent, no progress lost
   - Requires human approval before applying

4. **Coverage tracking:** Maintains a view of which taxonomy leaves have excerpts, how many, from which sources. Identifies gaps — leaves with no coverage or thin coverage. This information feeds back into Step 0.1 (source gathering) to prioritize finding material that fills gaps.

---

## 6. Source Diversity

The four Arabic sciences draw knowledge from fundamentally different types of sources: books, online scholarly content, and recorded lectures. Each type differs in format, structure, acquisition method, text quality, and the nature of the knowledge it contributes. These differences are precisely what the source pipeline is designed to absorb — each source type will have its own gathering method (Step 0.1), its own metadata characteristics (Step 0.2), and its own normalizer (Step 0.3), but the engine sees the same normalized package regardless.

The specific sources, their characteristics, and their acquisition strategies are documented when each source type is designed and implemented — not in this architecture document. What matters architecturally is:

- **Source types vary in structural clarity.** Some sources have explicit chapter/section structure (e.g., books with tables of contents). Others have implicit structure that must be discovered (e.g., topic transitions in lectures). Step 0.3 normalizers must handle the full range.
- **Source types vary in content quality.** Some are peer-reviewed and editorially curated. Others are informal. The intake metadata (Step 0.2) must capture this so downstream stages and the external synthesis can weight content appropriately.
- **Source types vary in acquisition complexity.** Some can be acquired programmatically via APIs. Others require manual download. Some require transcription from audio/video. Step 0.1 handles this diversity.
- **Not all sources have physical page numbers.** The normalized package must work for both paginated and non-paginated content. Sequential ordering is always present; physical page references may be null.
- **Each new source type requires a normalizer.** Adding a source type is a deliberate decision with implementation cost. The application defines its set of supported formats, and this set grows incrementally as normalizers are built and proven.

---

## 7. Implementation Strategy

The vision described above is built in concentric circles. Each circle is a self-contained milestone that produces usable output and validates the assumptions that the next circle depends on. No circle is started until the preceding circle is proven.

### Circle 1: Prove the engine (current focus)

**Goal:** Demonstrate that the extraction pipeline works end-to-end — from a normalized source through to excerpts placed in taxonomy folders — with acceptable quality.

**Scope:**
- Complete the Placement step (taxonomy evolution + assembly + distribution)
- Process the `imla` book (already normalized) through the full pipeline
- Verify that excerpts land in the correct taxonomy leaves
- Verify that excerpts are truly self-contained
- Verify that the taxonomy evolves sensibly when needed
- Fix BUG-001 (taxonomy format divergence), BUG-002 (prose_tail loops), BUG-003 (stale extraction output)

**Success criteria:** A taxonomy folder tree for إملاء populated with self-contained excerpts from قواعد الإملاء, validated by human review.

**What this proves:** The engine works. Extraction and Placement can take normalized input and produce the desired output.

### Circle 2: Scale with same source format

**Goal:** Process multiple sources of the same format through the proven pipeline. Fill taxonomy leaves. Discover where coverage is thin.

**Scope:**
- Process additional sources through the full pipeline
- Run extraction across all four sciences (not just إملاء)
- Track coverage: which leaves have excerpts, from how many sources
- Tune extraction quality based on observed issues across diverse sources
- Enrich author scholarly context where gaps exist

**Success criteria:** All four taxonomy trees have meaningful coverage from multiple sources. Coverage report identifies specific under-served areas.

**What this proves:** The pipeline scales. It handles diverse content structures, multiple sciences, different scholarly styles. The taxonomy evolution engine works with multi-source convergence.

### Circle 3: Add a second source format

**Goal:** Break the single-format assumption. Add a second supported source format. Prove the normalization boundary holds.

**Scope:**
- Build a new source adapter for the second format (Step 0.1)
- Build a new normalizer producing the same schema as the existing normalizer (Step 0.3)
- Fix the current normalization boundary violation (§4.4) — structure discovery must move into Step 0.3
- Process sources in the new format through the same engine, verify identical quality

**Success criteria:** Sources from both formats produce indistinguishable results in the taxonomy trees. The engine code is untouched — only source pipeline code was added.

**What this proves:** The normalization boundary works in practice. The architecture supports multiple source formats.

### Circle 4: Automate discovery and gap-filling

**Goal:** The system actively seeks out material to fill coverage gaps, rather than waiting for manual direction.

**Scope:**
- Coverage-driven discovery: the system examines which taxonomy leaves are under-served and searches for sources likely to fill those gaps
- Batch processing with approval checkpoints: the system proposes batches of sources, the user approves, and processing runs autonomously
- Cross-source quality: verify that excerpts from different sources at the same leaf are consistent, complementary, and correctly attributed
- Quality scoring: rank excerpts by quality to surface the best coverage at each leaf

**Success criteria:** The system can autonomously propose and process batches of sources that measurably improve taxonomy coverage, with human approval at the batch level (not per-source).

**What this proves:** The system can scale from manual operation to supervised automation.

### Circle 5: Diversify source types (future)

**Goal:** Add fundamentally different source types — not just different formats of the same type (e.g., books), but different kinds of sources (online scholarly content, recorded lectures).

**Scope:**
- Build source adapters and normalizers for new source types
- Process new source types through the engine, verify quality
- Evaluate: are excerpts from non-book sources as reliable as book-derived ones?

**Success criteria:** Excerpts from diverse source types appear in taxonomy trees alongside each other, with appropriate provenance marking. Quality is acceptable after human review.

**What this proves:** The architecture works for fundamentally different source types. The normalization boundary abstracts away the difference between books, web pages, and spoken content.

### Circle 6: Full automation and continuous operation (future)

**Goal:** Systematic sweep of all available sources across all source types. The system runs continuously, finding and processing new material as it becomes available.

**Scope:**
- Continuous monitoring for new source material
- Fully autonomous pipeline with human review at quality checkpoints
- Comprehensive coverage reporting and gap analysis
- Cross-source quality comparison and deduplication

**Success criteria:** All taxonomy leaves have multi-source, multi-author coverage. The system has processed all known relevant sources across all supported source types.

---

## 8. What "Done" Means

ABD has two levels of "done":

### Minimum viable completion

Every one of the taxonomy leaves (currently 892, growing through evolution) has at least one self-contained excerpt from at least one source. The taxonomy trees are populated. The external synthesis LLM can produce an encyclopedic entry for every leaf.

This is achievable likely within Circle 2 or Circle 3 of the implementation strategy.

### Full completion

Every taxonomy leaf has excerpts from multiple sources by different scholars, capturing the diversity of scholarly positions on that topic. The taxonomy has evolved to its natural level of granularity — fine enough to distinguish topics that different scholars treat differently, without over-splitting topics that are naturally unified.

This is the end-state vision, likely requiring Circles 4–6 of the implementation strategy.

### A note on "complete" vs. "living"

The taxonomy is a living structure. New books may reveal finer distinctions that require further evolution. New scholars may introduce perspectives not yet represented. "Done" does not mean "frozen" — it means "comprehensive enough to serve the downstream synthesis with high quality, while remaining open to improvement."

---

## 9. Design Principles

These principles are inherited from the existing project (see `CLAUDE.md`) and augmented for the multi-source architecture.

### Inherited principles (unchanged)

1. **Precision above all.** Every content decision must be surgically accurate. Multi-model consensus, cross-validation, human gates with feedback loops, and regression testing.

2. **Intelligence over algorithms.** Content understanding is LLM-driven. Mechanical checks use algorithms. Content decisions require intelligence.

3. **Self-containment.** Every excerpt must be independently understandable by the synthesis LLM without cross-references.

4. **Living taxonomy.** The tree evolves as new material reveals finer distinctions. Excerpts are king; the tree serves them.

5. **Self-improving system.** Corrections are saved, root causes analyzed, fixes proposed and regression-tested.

### New principles (from the multi-source architecture)

6. **Source agnosticism below the boundary.** The engine must work identically regardless of source format. This is not a preference — it is a hard architectural constraint. Any source-specific logic that leaks below the normalization boundary is a bug.

7. **Normalizer freedom above the boundary.** Each normalizer is free to use whatever techniques it needs — complex parsing, LLM assistance, multi-pass processing — to produce conformant output. Normalizer complexity is unlimited and self-contained.

8. **Incremental value at every stage.** Each implementation circle produces a usable system. Circle 1 produces a working pipeline for one book. Circle 2 produces populated taxonomy trees. No circle depends on future circles for its value.

9. **Prove before expanding.** No new source type, automation level, or architectural change is built until the previous level is proven to work. The engine must be validated before source gathering is automated. The normalization boundary must be clean before a second source format is added.

10. **Coverage-driven prioritization.** Once the engine is proven, the choice of what to process next is driven by which taxonomy leaves need more coverage, not by what material is easiest to acquire.

---

## 10. Mapping to Current Pipeline Stages

The new architecture maps onto the existing pipeline stages as follows:

| Architecture step | Pipeline stages | Current tools |
|-------------------|----------------|---------------|
| Step 0.1: Source Gathering | (manual — user provides file paths) | — |
| Step 0.2: Source Intake | Stage 0 (Intake) + Stage 0.5 (Enrichment) | `intake.py`, `enrich.py` |
| Step 0.3: Source Normalization | Stage 1 (Normalization) + Stage 2 (Structure Discovery) | `normalize_shamela.py`, `discover_structure.py` |
| Engine: Extraction | Stages 3+4 (Extraction + Consensus) | `extract_passages.py`, `consensus.py` |
| Engine: Placement | Stage 5 (Taxonomy Trees) + Stage 6 (Evolution) + Stage 7 (Assembly) | Taxonomy YAMLs; Stages 6–7 not yet built |

**Notable:** The current Stage 0 (Intake) mixes concerns that the new architecture separates. It handles both source-format-specific metadata parsing (reading Shamela HTML cards) and universal documentation (assigning IDs, recording provenance, freezing). As the source pipeline matures, Stage 0's responsibilities will be distributed across Steps 0.1, 0.2, and 0.3 as appropriate.

**Notable:** Structure discovery (Stage 2) currently violates the normalization boundary (see §4.4). Under the new architecture it belongs inside Step 0.3, not as a separate post-normalization stage.

---

## 11. Glossary Additions

The following terms are introduced by this document:

**Source pipeline:** The three-step process (Steps 0.1–0.3) that finds, documents, and normalizes source material before the engine processes it. Everything in the source pipeline is source-format-specific.

**Engine:** The source-agnostic part of ABD (Extraction + Placement) that processes normalized content, extracts teaching units, and populates taxonomy trees. The engine never touches raw source files.

**Source adapter:** A module responsible for searching, identifying, and acquiring raw source material from a specific source. Belongs to Step 0.1.

**Normalizer:** A module that transforms raw source material from a specific format into ABD's universal normalized structure. One normalizer per source format. Includes both content normalization and structure discovery. Belongs to Step 0.3.

**Normalized package:** The complete output of Step 0.3 — pages, structural divisions, and passage boundaries in a universal schema. This is what crosses the normalization boundary and enters the engine.

**Normalization boundary:** The architectural dividing line between the source pipeline and the engine. Everything below this boundary is source-agnostic. Everything above it is source-specific. Defined by the output schema of Step 0.3.

**Living metadata:** The intake metadata record (Step 0.2) that is enriched over time as more information about the source is learned — during normalization, extraction, and external research.

**Supported source format:** A format for which the application has a working normalizer in Step 0.3. Adding a new format requires building a new normalizer and is a deliberate decision.

**Coverage:** The degree to which taxonomy leaves are populated with excerpts. A leaf with zero excerpts has no coverage. A leaf with excerpts from multiple sources by different scholars has rich coverage.

**Circle (implementation):** A self-contained milestone in the implementation strategy. Each circle builds on the previous one and produces independently usable output. See §7.

---

*This document was created on 2026-02-28 and reflects the architectural direction agreed upon during the Stage 0 deep-dive discussion. It should be updated as the architecture evolves, with version numbers incremented for substantive changes.*
