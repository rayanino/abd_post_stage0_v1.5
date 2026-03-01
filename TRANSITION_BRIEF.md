# TRANSITION BRIEF — ABD → خزانة ريان

**Status:** Active directive. Read this BEFORE reading CLAUDE.md.
**Date:** 2026-03-01
**Authority:** This document is a binding directive from the project owner. It supplements CLAUDE.md for the current transitional period. Where this document and CLAUDE.md conflict, this document governs. Where this document is silent, CLAUDE.md governs.

---

## What Is Happening

This codebase (ABD — Arabic Book Digester) is transitioning to **خزانة ريان** (Khizanat Rayan, abbreviated **KR**). KR is a vastly expanded version of ABD: a personal intelligent Islamic scholarly library covering 30+ Islamic and supporting sciences, multiple source formats, and a synthesis engine that generates encyclopedic entries as a primary knowledge product. The full architectural specification is being written in parallel with this engine work and is not yet available in the repo.

**The transition is NOT happening yet.** No renaming, no directory restructuring, no new taxonomy trees, no new source format support. What IS happening right now is: the engine components (extraction, taxonomy evolution, assembly, validation) are being hardened and completed so they work correctly across any science — not just the four Arabic language sciences they were originally built for. When the full KR specification is ready and committed to the repo, the restructuring will happen in one clean pass. Until then, the codebase remains ABD in name and structure.

**Why this matters to you (Claude Code):** everything you build right now must be **science-agnostic**. The extraction engine, the taxonomy evolution engine, the human gate infrastructure, the validation layers — none of these should contain logic that only works for إملاء or only works for Arabic language sciences. They must work identically for فقه, عقيدة, تفسير, حديث, or any other science that will exist under KR. The engine does not know or care which science it is processing; it processes normalized content against taxonomy trees. That principle is already in the architecture, but some code may have implicit assumptions about the original four sciences that need to be found and removed.

---

## What KR Changes (Design Decisions Already Finalized)

The following decisions are finalized in the KR specification and are binding on all work you do now. They are listed here so you can design toward them even though the full specification is not yet in the repo.

**1. Core properties priority order: Accuracy > Protection from error > Intelligence.** Accuracy is the highest priority, not intelligence. When a design choice trades accuracy for cleverness, choose accuracy. When uncertain about a content decision, flag for human review rather than proceeding with a best guess. This is a reordering from the current CLAUDE.md (which lists precision and intelligence as co-equal); under KR, accuracy is strictly first.

**2. Entries are a primary knowledge product, not an external afterthought.** The current CLAUDE.md says synthesis is "external to this repo." Under KR, the synthesis engine is an integral component. You do not need to build the synthesis engine now (its specification is not ready), but you DO need to ensure that everything you build is compatible with entry generation. Specifically: self-contained excerpt files must carry all metadata that a synthesis engine would need (author identity, scholarly context, مذهب, school, source reference, taxonomy path). Design excerpt file formats with synthesis consumption in mind.

**3. Two-tier content model: verified knowledge vs. flagged knowledge.** Every excerpt in the library belongs to exactly one tier. Verified knowledge is what the owner studies from. Flagged knowledge is structurally separated — stored separately, displayed separately, excluded from entry generation and coverage metrics. The tier is determined by source trustworthiness evaluation (performed during intake). You do not need to build the trustworthiness evaluation system now, but the excerpt file format and the assembly/distribution system must accommodate a `tier` field (value: `verified` or `flagged`) and the folder distribution must be able to separate tiers in storage.

**4. Entry cardinality: per-school entries within leaves.** At a leaf where the science has scholarly schools (مذاهب), each school with excerpts at the leaf gets its own entry. There is no cross-school entry. The tree is structured by topic; schools organize content within each topic. This means: school metadata on excerpts is not optional — it is architecturally required for any science that has schools. The extraction engine must reliably produce school classifications. The assembly system must organize excerpts by school within each leaf.

**5. The normalization boundary is absolute.** The engine (extraction, evolution, assembly, validation) must never contain source-format-specific logic. No references to Shamela, HTML, KetabOnline, or any source format below the normalization boundary. This is already the intended design, but verify it holds in all code you write or modify. If you find violations in existing code, note them in BUGS.md but do not fix them in the current work session unless the fix is trivial — the source pipeline restructuring will address them comprehensively.

**6. Taxonomy trees are versioned and rollback-capable.** Every modification to a tree creates a new version. Previous versions are retained indefinitely. Rollback must be possible: if an evolution proves incorrect, the tree reverts to a previous version and excerpts are redistributed accordingly.

**7. Excerpt self-containment is the defining property.** An excerpt must carry everything needed to understand it independently: full Arabic text, author identity and scholarly context (مذهب, school, era), source reference, topic context (taxonomy path), and content type metadata. A reader of an excerpt must never need another excerpt or external context to understand what it teaches, who said it, and which scholarly tradition it comes from.

**8. Science-specific metadata is an extension of the universal excerpt definition.** All excerpts share the same core schema. Sciences with schools (فقه, عقيدة, نحو) add a `school` metadata field. Sciences referencing Quran add آية references. Sciences referencing hadith add hadith references. These are additive fields on top of the universal schema, not separate schemas per science. The extraction engine needs to know which science it is processing so it can extract the appropriate metadata, but the core extraction logic (atomize → group → place) is identical.

---

## What You Should Build Now (Priority Order)

These items are science-agnostic, architecture-stable, and will carry directly into KR without modification. Build them in the order listed. Each item includes acceptance criteria — the work is not done until every criterion is met.

### Priority 1: Fix BUG-001 — Taxonomy Format Divergence

**What:** `extract_taxonomy_leaves()` in `tools/extract_passages.py` uses line-by-line text matching and only handles the dict-nested `_leaf: true` format. It returns 0 leaves for بلاغة (which uses list-of-nodes with `leaf: true`). This completely breaks extraction for any science using the list-based format.

**Why it blocks everything:** You cannot test cross-science extraction if the taxonomy parser breaks on half the taxonomy files.

**Fix:** Parse taxonomy YAML properly (not line scanning). Handle both `_leaf: true` (dict-nested) and `leaf: true` (list-of-nodes) formats. Unify on one canonical internal representation. Every function that reads taxonomy data must use this unified parser.

**Acceptance criteria:**
- `extract_taxonomy_leaves()` returns correct leaves for ALL taxonomy files in `taxonomy/`: imlaa, sarf, nahw, balagha, aqidah.
- A test exists that loads each taxonomy file and verifies the expected leaf count.
- Any other functions that parse taxonomy YAML (in `assemble_excerpts.py`, `evolve_taxonomy.py`, or elsewhere) also use the unified parser.
- Existing tests still pass (zero regressions).

### Priority 2: Taxonomy Evolution Phase B — Apply, Version Control, Rollback

**What:** Phase A (signal detection + LLM proposal + review artifacts) is built in `tools/evolve_taxonomy.py`. Phase B is the completion: applying approved proposals, versioning the taxonomy YAML, and rollback capability.

**Build these capabilities:**

**Apply step.** Given an approved evolution proposal (the JSON output of Phase A), apply the changes to the taxonomy YAML: convert the affected leaf to a branch, add new sub-leaves, update the YAML file. The apply step writes a new version of the taxonomy file (e.g., `imlaa_v1_1.yaml` from `imlaa_v1_0.yaml`). It never modifies the original file. It updates `taxonomy_registry.yaml` with the new version.

**Excerpt redistribution.** After applying a tree evolution, existing assembled excerpt files at the old leaf must be redistributed to the new sub-leaves. Redistribution is an LLM-driven decision: the system reads each excerpt's Arabic text and the new sub-leaf definitions, and assigns each excerpt to its correct new home. Multi-model consensus applies to redistribution decisions (same consensus mechanism as extraction). Every excerpt must have a home after redistribution (zero orphans). If any excerpt cannot be confidently placed, it is flagged for human review rather than guessed.

**Rollback.** Given a taxonomy version, revert to the previous version. This means: restore the previous YAML file as the active version, move redistributed excerpt files back to the original leaf, and update the registry. Rollback must be lossless — no excerpt files are deleted during redistribution, they are moved. Rollback moves them back.

**Multi-model consensus for proposals.** Phase A currently uses a single LLM for proposals. Extend it to use multi-model consensus (the same mechanism in `tools/consensus.py`): multiple models independently propose sub-leaves for the same evolution signal, and the consensus engine compares their proposals. Where they agree: high confidence. Where they disagree: an arbiter resolves or the proposal is flagged.

**Acceptance criteria:**
- Apply step creates a new taxonomy YAML version without modifying the original.
- `taxonomy_registry.yaml` is updated with the new version entry.
- Excerpt redistribution moves files correctly, with zero orphans after redistribution.
- Rollback restores the previous taxonomy version and moves excerpt files back.
- Multi-model consensus works for evolution proposals.
- All of the above have tests.
- The evolution pipeline works end-to-end: detect signal → propose (consensus) → human reviews JSON/MD artifacts → approve → apply → redistribute → verify zero orphans. And: rollback reverses the entire operation.

### Priority 3: Human Gate Infrastructure

**What:** The feedback persistence and correction learning system described in CLAUDE.md's "Human gates and feedback learning" section. Currently, human gates are a concept described in documentation but not implemented as infrastructure in code.

**Build these capabilities:**

**Correction cycle persistence.** When a human corrects an extraction result (moves an excerpt to a different leaf, adjusts excerpt boundaries, changes مذهب attribution, rejects an excerpt entirely), the full correction cycle is saved as a structured JSON record: what the system produced, what the human corrected it to, and optionally why. These records accumulate in a persistent store (a JSONL file per science or per book — choose the organization that makes querying easiest).

**Correction replay.** Given a saved correction, the system can re-extract the affected passage incorporating the correction as additional context in the extraction prompt. This is not automatic — it is triggered by the human at review time.

**Pattern detection.** A tool that reads all saved corrections and identifies patterns: recurring error types (e.g., "مذهب misattribution"), recurring affected taxonomy nodes, recurring error sources (specific models, specific passage characteristics). The tool produces a structured report. It does NOT automatically modify system rules — it produces a report that the human reviews.

**Gate checkpoints.** A lightweight checkpoint mechanism that marks which extraction results have been human-reviewed and which are pending. The checkpoint state lives alongside the extraction output (not in a separate database). When the human resumes review, they can see what they have already approved.

**Acceptance criteria:**
- Correction records are saved as structured JSON with: original system output, human correction, timestamp, affected excerpt IDs, correction type (placement, boundary, attribution, rejection).
- A correction replay function exists that re-extracts a passage with the correction as context.
- A pattern detection tool reads all corrections and produces a structured report of recurring patterns.
- Gate checkpoints track reviewed/pending status per extraction result.
- All of the above have tests.

### Priority 4: Cross-Validation Layers

**What:** Validation mechanisms that catch content errors requiring understanding, as opposed to the existing algorithmic checks (schema validation, character counts, etc.).

**Build these capabilities:**

**Placement cross-validation.** After extraction assigns an excerpt to a leaf, a separate LLM call (not the extraction model) reads the excerpt text and the taxonomy tree structure and independently determines which leaf the excerpt belongs at. If the independent placement disagrees with the extraction placement, the disagreement is flagged. This is the same principle as multi-model consensus but applied specifically to placement decisions post-extraction.

**Self-containment validation.** A validation pass that reads each assembled excerpt file and verifies that it is independently understandable: does it contain the full text, is the author identified, is the scholarly context present (school/مذهب where applicable), is there a source reference, is the topic context clear from the taxonomy path? This can be partially algorithmic (check that required fields are non-empty) and partially LLM-driven (does the text actually make sense as a standalone teaching unit?).

**Cross-book consistency at a leaf.** When multiple books contribute excerpts to the same leaf, verify that they are actually about the same topic. If book A's excerpt at leaf X discusses وضوء and book B's excerpt at the same leaf discusses غسل, one of them is probably misplaced. This requires LLM reasoning: read all excerpts at a leaf and verify topic coherence. Flag outliers.

**Acceptance criteria:**
- Placement cross-validation runs as a separate step after extraction, produces a report of disagreements.
- Self-containment validation runs on assembled excerpt files, flags incomplete or non-self-contained excerpts.
- Cross-book consistency runs per leaf (for leaves with 2+ excerpts from different books), flags topic-incoherent excerpts.
- All validations produce structured output (not just print statements) that can be consumed by the human gate.
- All of the above have tests with synthetic data.

---

## What You Must NOT Build Now

The following items depend on KR specification sections that are not yet finalized. Building them now would require guessing at requirements, and the no-inference rule (from the KR specification) prohibits that. Do not build any of these, even partially, even as stubs, even as "infrastructure that could be extended later."

**New taxonomy trees.** Do not create taxonomy trees for any science beyond the five already in `taxonomy/` (imlaa, sarf, nahw, balagha, aqidah). The science inventory, tree structure, and organizational principles for each science require dedicated research that has not been done.

**Source pipeline changes.** Do not add support for non-Shamela source formats. The source pipeline restructuring depends on KR spec sections (§7) that are being rewritten.

**Synthesis engine.** Do not build entry generation. The synthesis specification is being designed.

**Renaming or restructuring.** Do not rename ABD to KR. Do not reorganize the directory structure from numbered stages to Source Pipeline / Engine / Library. This will be a clean, comprehensive operation after the full KR spec is committed.

**Trustworthiness evaluation.** Do not build the source trustworthiness assessment system. The two-tier model is defined but the evaluation criteria and mechanism are not specified.

**Autonomous source discovery.** Do not build any part of the autonomous discovery system.

**Coverage tracking.** Do not build the coverage metrics system. The coverage model depends on decisions about how sciences, schools, and tiers interact in metrics calculations that are not yet finalized.

---

## Science-Agnosticism Checklist

When writing or modifying any code, verify the following. If any check fails, the code needs to be redesigned before proceeding.

**No hardcoded science names.** The code must not contain `if science == "imlaa"` or `if science in ["imlaa", "sarf", "nahw", "balagha"]`. Science names are parameters, never conditions. Exception: test files may use specific science names as test fixtures.

**No hardcoded taxonomy structure assumptions.** The code must not assume a specific depth, a specific number of leaves, or a specific branching pattern. Taxonomy trees vary enormously across sciences (إملاء has 105 leaves; a complete فقه tree might have thousands).

**No hardcoded school lists.** The code must not contain `["الحنفية", "المالكية", "الشافعية", "الحنبلية"]` or equivalent. Schools are metadata on excerpts and are discovered from the content, not assumed from a fixed list. Different sciences have different schools (grammatical schools in نحو, theological schools in عقيدة, legal schools in فقه). Some sciences have no schools at all.

**No Arabic-language-science-specific logic in the engine.** The engine handles نحو disputes and فقه rulings identically: both are excerpts placed at leaves with school metadata. If you find yourself writing logic that only makes sense for grammatical analysis, it does not belong in the engine.

**Taxonomy YAML format is unified.** All code that reads taxonomy files must handle both the dict-nested and list-of-nodes formats through a single unified parser. After BUG-001 is fixed, this parser is the only way to read taxonomy data.

---

## Available Test Material for Cross-Science Validation

The repo contains test material for sciences beyond the original four Arabic language sciences. Use this material to verify that your implementations work across science boundaries.

**عقيدة (creed):**
- Taxonomy: `taxonomy/aqidah/aqidah_v0_1.yaml` (21 leaves)
- Book: `books/wasitiyyah/` (العقيدة الواسطية, 32 pages) — has Stage 1+2 outputs
- E2E verified: 10 passages extracted with full pipeline

**Additional books in `books/Other Books/`:**
- `كتب العقيدة/` — additional عقيدة texts (raw Shamela exports)
- `كتب الفقه الحنبلي/` — Hanbali فقه texts (raw Shamela exports)
- `كتب البلاغة/` — additional بلاغة texts
- `كتب اللغة/` — language science texts
- `كتب النحو والصرف/` — additional نحو and صرف texts

The عقيدة and فقه books are particularly valuable for testing school-based metadata extraction (theological schools in عقيدة, legal مذاهب in فقه). Use them in tests to verify that the extraction engine correctly produces school classifications for non-Arabic-language sciences.

---

## Relationship to CLAUDE.md

CLAUDE.md remains the operational reference for running the pipeline, understanding the directory structure, and knowing the code conventions. This document adds to it, it does not replace it.

Specific overrides (this document governs where CLAUDE.md says otherwise):

- CLAUDE.md's "What needs to be built" list: follow this document's priority ordering instead.
- CLAUDE.md says "Do NOT spend time on building synthesis tooling": confirmed, but now the reason is "the synthesis specification is not yet ready," not "synthesis is external to this repo." Synthesis will be internal to this repo under KR.
- CLAUDE.md's "Core Design Principles" section: the property ordering under KR is Accuracy > Protection from error > Intelligence. Precision (accuracy) is strictly first priority, not co-equal with intelligence.

Everything else in CLAUDE.md (running commands, code conventions, architecture patterns, gotchas, test book descriptions) remains current and authoritative.

---

## When This Document Expires

This document expires when the full KR specification is committed to the repo and a new CLAUDE.md is written for the KR codebase. At that point, the KR specification becomes the top-level design authority and this transitional brief is archived. Until that happens, this document governs the scope and priorities of all implementation work.
