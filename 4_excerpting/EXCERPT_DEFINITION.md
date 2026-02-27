# Definition and Rules of Excerpting

> ## STATUS: Single Source of Truth (needs comprehensive update)
> This file is the **single source of truth** for what an excerpt IS. However, it was written before the current vision was fully developed and needs updating to reflect:
> - **Self-containment**: every excerpt must be independently understandable by the synthesis LLM
> - **Taxonomy evolution**: excerpts drive tree growth, not the other way around
> - **Multi-model consensus**: planned for extraction validation
> - **Human gates**: feedback loops and self-improving system
>
> Until this file is fully rewritten, conflicts are resolved by:
> `00_BINDING_DECISIONS_v0.3.16.md` → schema v0.3.3 → glossary → checklists → protocol → baselines.
>
> **Binding corrections already in effect:**
> - Heading atoms are **metadata-only** and are never included in excerpts as core or context atoms.
> - Parent/general content uses the `__overview` leaf convention exclusively.
> - Each excerpt file must be **self-contained** — the synthesis LLM must understand it without needing other files.

This section defines with precision what an "excerpt" is within this project, how excerpt boundaries are determined, how edge cases are handled, and what metadata accompanies each excerpt. These rules govern the most critical operation in the entire pipeline: the intelligent decomposition of a book into atomic, accurately-placed fragments within the taxonomy tree.

**The stakes:** an error in excerpting — a wrong boundary, a lost passage, a misplaced fragment — propagates through every downstream step. The future LLM synthesis (step B) can only be as good as the excerpts it receives. Every rule below exists to maximize the quality, accuracy, and contextual richness of excerpts for that synthesis.

### Prerequisite: Input Preparation (Addressed Separately)

This section defines the rules for excerpting — what a correct excerpt looks like and how edge cases are handled. It does **not** address the upstream question of how raw source material (Shamela HTML exports, ketab-online-sdk output, or other sources) is transformed into clean, structured text ready for excerpting. That transformation — source format analysis, HTML parsing, text cleanup, normalization, detection of structural markers (باب، فصل، مسألة, etc.), separation of multi-layer content (متن/شرح/حاشية), handling of encoding issues — is a prerequisite problem that must be addressed in its own dedicated section before the excerpting pipeline can operate.

The rules below assume that the excerpting engine receives **clean, correctly-parsed, layer-separated text** with accurate structural markers. If the input is garbled, mis-parsed, or incorrectly layered, no amount of intelligent excerpting will compensate. Input preparation is therefore at least as critical as the excerpting logic itself and will be specified with equal rigor in its own section.

### What "Verbatim" Means: The Canonical Text Representation Contract

Throughout this document, the requirement that excerpt text be "verbatim" and "faithful" means: **verbatim relative to the canonical parsed layer output of the input preparation stage, not relative to the raw source file (HTML, PDF, etc.).**

The input preparation stage is permitted to apply the following **allowed canonicalizations** (transformations that produce the clean text that the excerpting engine receives):

- HTML entity decoding and tag stripping.
- Unicode normalization (NFC or NFKC — to be specified in the input preparation section).
- Whitespace normalization (collapsing multiple spaces, standardizing line breaks).
- Removal of rendering artifacts (page numbers, headers/footers, footnote markers when the footnote content is preserved separately).

The following are **forbidden changes** — they must never be applied, not even during input preparation:

- Spelling correction or modernization of any kind.
- Adding, removing, or altering diacritics (التشكيل).
- Editorial insertions, clarifications, or rewording.
- Changing the order of any content.
- Removing or altering scholarly content (even if it appears to be a printing error — preserve it, flag it in metadata).

After input preparation produces its canonical output, the excerpting engine treats that output as sacred. Excerpt text is copied character-for-character from the canonical output. No further transformations are permitted. The `normalized_text` metadata field (with diacritics stripped, character variants unified) exists alongside the verbatim text for search and matching purposes, but is never the primary representation.

---

## 1. Atoms: The Indivisible Units of Excerpting

### 1a. The Concept of an Atom

An **atom** is the smallest indivisible unit of text in the excerpting pipeline. Once a text has been atomized (see §1b), atoms are never split. All excerpting logic operates on atoms — combining them into excerpts, duplicating them across nodes, tagging them as core or context — but never breaking them apart.

An atom can be any of the following types:

- **Sentence atom:** a single sentence terminated by terminal punctuation (`.`, `؟`, `?`, `!`) or by a paragraph/section break. This is the most common atom type.
- **Bonded cluster atom:** two or more consecutive sentences that are semantically inseparable (see §1c for the full catalog of bonding patterns). Once recognized as bonded, the cluster becomes a single atom.
- **Heading atom:** a structural marker line (باب، فصل، مسألة، تنبيه، فائدة, chapter/section titles, etc.) that serves as explicit author labeling. Headings are structural metadata: they are always **excluded** from excerpts but **referenced** in `heading_path` for placement/review.
- **Verse/poetry atom:** a line of Quranic text, a line of poetry (بيت شعر), or a hadith citation that functions as a self-contained unit.
- **Table/paradigm atom:** a non-prose block such as a conjugation table, paradigm chart, or structured list. These are indivisible as blocks (see §10 on dual representation).

Every atom receives a unique, stable identifier (`atom_id`) during atomization. This identifier is the primary reference used throughout the excerpting pipeline.

### 1b. Atomization: An Explicit Upstream Pipeline Stage

Atomization is the process of converting clean, parsed source text (output of the input preparation stage) into an ordered sequence of atoms. **Atomization happens once per source text, before any excerpting logic runs, and its output is reviewed at Checkpoint 1 (§18a).**

This resolves what would otherwise be a circularity: the rule "atoms are never split" is meaningful only because what counts as an atom is determined upstream, in a dedicated stage with its own review checkpoint. The excerpting engine receives a finalized, human-reviewed sequence of atoms and operates on that sequence. It never needs to decide what is or isn't an atom — that decision has already been made and verified.

Atomization must handle the following challenges:

**Punctuation-based segmentation** for well-punctuated texts: terminal punctuation (`.`, `؟`, `?`, `!`) and paragraph breaks define sentence atom boundaries. The following are NOT atom boundaries: Arabic comma `،`, Latin comma `,`, Arabic semicolon `؛`, Latin semicolon `;`, colon `:`, em-dashes, and hyphens.

**LLM-assisted segmentation** for poorly-punctuated or unpunctuated texts: when a source uses minimal or no terminal punctuation (common in unedited classical texts), paragraph breaks become the primary boundaries, and LLM-level judgment is applied to identify logical sentence divisions within unpunctuated blocks. The resulting atoms are provisional until reviewed at Checkpoint 1.

**Bonded cluster detection** (see §1c): consecutive sentences that are semantically inseparable are merged into a single bonded cluster atom. This detection runs as part of atomization, before the excerpting stage.

**Structural marker detection:** heading lines, section titles, and labeled markers (باب، فصل، مسألة, etc.) are identified and tagged as heading atoms.

**Non-prose block detection:** tables, paradigm charts, and verse/poetry blocks are identified and tagged with their respective atom types.

After atomization, the result is a flat, ordered sequence of atoms, each with a unique ID, a type tag, and exact source anchors (character offsets, page/paragraph references). This sequence is the input to the excerpting engine.

### 1c. Semantically Bonded Clusters

There are cases where two or more consecutive sentences, each with their own terminal punctuation, are semantically bonded to the degree that separating them would render one or both meaningless or misleading. During atomization, these are merged into a single bonded cluster atom.

The most common bonding patterns in Arabic scholarly texts are:

- **Question-and-answer pairs:** "فإن قيل: لماذا قدّم المبتدأ؟ قلنا: لأنّه الأصل في الرتبة." — the question alone has no content; the answer alone lacks context. Together they form a single semantic unit.
- **Rhetorical question sequences:** "أهو غبيّ؟ أهو أحمق؟" — consecutive questions serving the same rhetorical purpose, where splitting between them would fragment a unified argument.
- **Assertion-then-evidence pairs:** "والقاعدة مطّردة. دليل ذلك قوله تعالى: ..." — the evidence sentence's entire purpose is to support the preceding assertion; it is incomplete without it.
- **Condition-then-consequence pairs** that span sentence boundaries: an author may put a period after the condition and begin the consequence as a new sentence, but the consequence is meaningless without the condition.

The system must recognize these clusters and merge them during atomization. This recognition requires LLM-level understanding of Classical Arabic discourse patterns, not pattern matching on surface cues.

### 1d. Atom Boundaries Define the Floor, Not Forced Split Points

A critical clarification: atom boundaries define the **minimum** unit — the smallest fragment the system will ever produce. They do **not** mean the system must split at every atom boundary. An excerpt consists of one or more atoms. Multiple consecutive atoms about the same topic naturally form a single excerpt. The system only splits between atoms when the topic changes.

### 1e. Heading Atoms

Heading atoms (باب، فصل، مسألة, chapter titles, section titles, labeled markers like فائدة and تنبيه) serve a dual purpose:

**As metadata:** every excerpt carries a `heading_path` field that records the nearest ancestor heading hierarchy (e.g., `باب الفاعل > فصل في أحكام الفاعل > مسألة تقديم الفاعل`). This is among the most reliable signals for taxonomy placement and is invaluable for human reviewers.

**Heading atoms are metadata-only (binding):** heading atoms are never included in excerpts (neither `core_atoms` nor `context_atoms`). Headings must be excluded (e.g., `heading_structural`) and referenced only via `heading_path` / breadcrumb metadata. If any downstream consumer (e.g., excerpt `.md` renderer or synthesis LLM) needs the heading text, it must be provided out-of-band as derived metadata (e.g., a breadcrumb string), not as an included atom.

Heading atoms are **never** standalone excerpts (a heading line alone has no scholarly content). They always serve as context for or metadata about the atoms that follow them.

### 1f. Rationale

Splitting an atom risks severing syntactic dependencies: a pronoun from its referent, a predicate from its subject, a conjunction from its first conjunct, an answer from its question, evidence from its claim. The resulting fragments may lose meaning entirely or, worse, convey a distorted meaning. The cost of occasionally including a few words about an unrelated topic within an excerpt is far lower than the cost of producing a meaningless or misleading fragment.

---

## 2. What Is an Excerpt (Formal Definition)

An excerpt is a canonical selection of source text that serves as evidence for exactly one taxonomy leaf node.

Formally, an excerpt is:

1. **Drawn from exactly one source layer** (متن / شرح / حاشية / تحقيق-علمي) of one book.
2. **Represented as an ordered list of one or more contiguous spans.** Each span is a consecutive sequence of atoms with no omissions inside the span. An excerpt may have multiple spans only when required to preserve atomicity AND topical purity (e.g., a shared شاهد followed by a gap where sibling observations were omitted, followed by the observation relevant to this node — see §6).
3. **Assigned to exactly one leaf node** as its "core node."
4. **Composed of two categories of atoms:**
   - **Core atoms:** atoms that substantively teach, explain, define, argue about, or demonstrate the core node's topic. These are the atoms that the synthesis LLM should treat as authoritative content for this node.
   - **Context atoms** (optional): atoms included solely to satisfy the comprehensibility principle (§2e). They do not teach the core node's topic — they provide necessary framing, a preceding question whose answer is a core atom, a heading that identifies the section, or a transitional sentence that anchors the excerpt in its source context. The synthesis LLM must know these are context, not doctrine.
5. **Text-faithful:** every atom is copied verbatim from the authoritative source representation. No edits, rewrites, or normalizations are applied to the excerpt text. Normalization exists only as a separate metadata field.
6. **Fully traceable:** every span carries source anchors (file, character offsets, atom IDs, context hash) that allow the excerpt to be located and re-verified in the source at any time.

### 2-blueprint. The Anatomy of an Excerpt (Data Object Blueprint)

Every excerpt in the system is a structured data object with the following components. This blueprint is the canonical reference for what an excerpt contains. Fields marked **(required)** must always be present; fields marked **(conditional)** are present only when applicable; fields marked **(computed)** are generated by the system rather than the excerpting logic.

```
EXCERPT OBJECT
├── Identity & Traceability
│   ├── excerpt_id                  (required) UUID, globally unique, immutable once assigned
│   ├── extraction_version          (required) ruleset version / git commit that produced this excerpt
│   ├── extraction_timestamp        (required) when this excerpt was created
│   └── extraction_method           (required) llm_auto | human_manual | llm_assisted_human_reviewed
│
├── Source Identification
│   ├── source_book_id              (required) unique identifier for the book
│   ├── source_book_title           (required) full title of the book
│   ├── source_layer                (required) متن | شرح | حاشية | تحقيق-علمي
│   ├── source_author               (required) author of this specific layer
│   ├── source_era                  (conditional) approximate era/century, when known
│   ├── source_edition              (conditional) edition, publisher, print information
│   └── book_science_scope          (required) single | multi, with list of declared sciences
│
├── Spans (the actual text)
│   ├── span_list                   (required) ordered list of spans, each containing:
│   │   ├── span_index              (required) position in the span list (0, 1, 2...)
│   │   ├── atom_ids                (required) ordered list of atom IDs in this span
│   │   ├── text                    (required) verbatim text of this span (faithful copy)
│   │   ├── anchor_start            (required) {file, char_offset, page, paragraph_index}
│   │   ├── anchor_end              (required) {file, char_offset, page, paragraph_index}
│   │   └── context_hash            (required) hash of span text + surrounding context for verification
│   │
│   ├── core_atom_ids               (required) list of atom IDs that are core atoms (teach the node)
│   ├── context_atom_ids            (conditional) list of atom IDs that are context-only atoms
│   ├── context_atom_reasons        (conditional) for each context atom: why it was included
│   │                                            (e.g., "heading", "comprehensibility", "leading transition")
│   └── context_source_nodes        (conditional) for context atoms that clearly belong to neighbor nodes:
│                                                 which node they substantively belong to
│
├── Taxonomy Placement
│   ├── taxonomy_node_path          (required) full path (e.g., علم_النحو/المرفوعات/الفاعل/تعريف_الفاعل)
│   ├── taxonomy_science            (required) which of the four sciences
│   ├── placement_confidence        (required) confidence score for placement correctness
│   ├── placement_reviewed          (required) boolean: human-reviewed and approved?
│   └── heading_path                (required) nearest ancestor heading hierarchy from source
│                                              (e.g., باب الفاعل > فصل أحكام الفاعل)
│
├── Structural Context
│   ├── boundary_atoms              (conditional) atom IDs that are transitional, with:
│   │   ├── direction               trailing | leading
│   │   └── connected_nodes         which node(s) the transition connects to
│   ├── shared_atoms                (conditional) atom IDs duplicated in excerpts at other nodes,
│   │                                             with references to those nodes
│   ├── gap_markers                 (conditional) between-span gaps, each containing:
│   │   ├── after_span_index        which span the gap follows
│   │   ├── omitted_content_desc    brief description of what was omitted
│   │   └── sibling_excerpt_refs    references to sibling excerpt(s) that contain the omitted content
│   ├── interwoven_multi_topic      (conditional) boolean: inseparable multi-topic content?
│   ├── interwoven_nodes            (conditional) list of all nodes touched if interwoven
│   ├── interwoven_group_id         (conditional) shared UUID across all duplicated excerpts of the
│   │                                             same inseparable passage; synthesis LLM must treat
│   │                                             the group as ONE evidence block, not count separately
│   ├── contextual_note             (required) 1-3 sentence description of context in source
│   └── internal_structure          (conditional) for long excerpts: paragraph breaks, sub-sections
│
├── Content Type & Flags
│   ├── content_type                (required) prose | table | paradigm_chart | poetry |
│   │                                          example_list | تمارين | mixed
│   ├── evidence_items              (conditional) list of شواهد, each with role: شاهد | محل_الدراسة
│   ├── contains_example_list       (conditional) boolean
│   ├── example_count               (conditional) number of examples
│   ├── discourse_pattern           (conditional) identified pattern from §4b
│   ├── digression_atoms            (conditional) atom IDs that are digressions, with digression topic
│   └── non_prose_representations   (conditional) for non-prose atoms, dual storage:
│       ├── raw_block               the faithful verbatim text/HTML as extracted
│       └── structured_block        parsed JSON (table rows/cols, list items, etc.)
│
├── Source Integrity & Normalization
│   ├── diacritization_level        (required) full | partial | minimal | none
│   ├── text_integrity              (required) complete | partially_illegible | lacuna
│   ├── has_editorial_brackets      (conditional) boolean
│   ├── meaning_altering_variant    (conditional) boolean: variant reading changes scholarly meaning?
│   ├── variant_readings            (conditional) list of variants with manuscript sources
│   └── normalized_text             (computed) diacritics stripped, chars unified, for search/matching
│
├── Cross-References & Links
│   ├── cross_references            (conditional) list of {type: forward|backward,
│   │                                              target_node, source_text}
│   └── same_source_links           (conditional) list of links to related excerpts from same book:
│       ├── linked_excerpt_id
│       ├── relationship_strength   continuation | elaboration | recap | revision
│       └── reading_order           which excerpt should be read first
│
├── Revision & Contradiction
│   ├── revision_relationship       (required, default: none) none | original | revised
│   ├── linked_revision_id          (conditional) ID of related original/revised excerpt
│   ├── revision_signal             (conditional) exact author phrase signaling revision
│   └── potential_contradiction     (conditional) boolean: unresolved contradiction detected?
│
├── Cross-Science
│   ├── primary_science             (required) science the source book is classified under
│   ├── cross_science_placement     (conditional) science this excerpt was routed to, if different
│   └── cross_science_confidence    (conditional) confidence score for cross-science assignment
│
├── Multi-Judge Consensus (§18e)
│   ├── judge_count                 (required) number of judges used
│   ├── judge_agreement             (required) full | majority | none
│   ├── judge_model_ids             (required) list of model identifiers used
│   ├── judge_prompts_hash          (required) hash of the prompt(s) used for judging
│   ├── dissenting_opinions         (conditional) alternative proposals with reasoning
│   └── consensus_decisions         (required) which decisions used multi-judge vs single
│
└── Review & Quality
    ├── review_status               (required) pending_review | approved | flagged_for_revision |
    │                                          pending_classification
    ├── review_notes                (conditional) notes from human review
    └── review_history              (conditional) log of all review actions: who, when, what changed
```

### 2-rendering. How an Excerpt Is Displayed

When an excerpt is rendered for human review or for LLM synthesis, it should be presented in a clear structure that makes the core/context distinction visible:

```
┌─ EXCERPT [excerpt_id] ──────────────────────────────────────────────┐
│                                                                      │
│  SOURCE: [book_title] — [source_author] ([source_era])              │
│  LAYER:  [source_layer]                                              │
│  PAGES:  [page_start]–[page_end]                                    │
│  NODE:   [taxonomy_node_path]                                        │
│  HEADING PATH: [heading_path]                                        │
│  CONFIDENCE: [placement_confidence] | REVIEWED: [yes/no]            │
│                                                                      │
│  ── TEXT ──────────────────────────────────────────────────────────  │
│  [CONTEXT] باب الفاعل                                                │
│  [CONTEXT] وأمّا الفاعل فهو ما تقدّمه فعله.                          │
│  [CORE]    الفاعل هو الاسم المرفوع المسند إليه فعل ...              │
│  [CORE]    ويجب أن يكون بعد الفعل ...                                │
│  [CONTEXT] وسيأتي بيان أحكامه في الفصل التالي.                       │
│                                                                      │
│  ── NOTES ─────────────────────────────────────────────────────────  │
│  CONTEXTUAL NOTE: Definition appears at the opening of باب الفاعل,  │
│  after the author completes the discussion of نائب الفاعل.           │
│  [any gap markers, cross-references, flags...]                       │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

This rendering format is illustrative — the actual review interface may differ — but the principle is fixed: **core and context must always be visually distinguishable**, and all critical metadata must be visible alongside the text.

An excerpt is always:
- Drawn from a single source layer (one book, one layer — see §7 on multi-layer sources).
- Represented as one or more contiguous spans, each internally gap-free.
- Assigned to exactly one leaf node in the taxonomy tree (though the same atom(s) may appear in multiple excerpts assigned to different nodes — see §3).
- Accompanied by the full metadata schema above.

### 2a. Excerpt Depth: How Deep Does Granularity Go?

The granularity of an excerpt is determined by the granularity of the taxonomy tree's leaf nodes, and the taxonomy tree's granularity is determined by the content itself. **There is no predetermined limit to depth.** The goal is to reach the deepest level at which a topic can be meaningfully subdivided.

To illustrate: the node `تعريف_الصرف_اصطالحا` might appear to be a leaf node. But if the books reveal that scholars offer genuinely distinct definitions — for instance, a definition focused on the practical/applied scope of الصرف versus a definition focused on the theoretical/scientific scope — then `تعريف_الصرف_اصطالحا` is not a leaf node. It becomes a parent node with children such as `التعريف_الاصطلاحي_العملي` and `التعريف_الاصطلاحي_العلمي`. Each child is then a leaf node, and excerpts are placed at the leaf level.

This means the taxonomy tree is **not static**. It grows and deepens as the system processes more books and discovers finer distinctions. Step A4 in the pipeline explicitly anticipates this: "if an excerpt introduces a not-before-seen topic, the taxonomy tree expands; or if it introduces a further granulation of an already existing node, the topic tree adapts."

### 2b. The Leaf Node Test: When Is a Node Truly Atomic?

A node is a true leaf node (and thus the correct target for an excerpt) when the topic it represents **cannot be meaningfully further subdivided into sub-topics that would each have their own independent content in the source books.**

The key word is "meaningfully." The test is not whether you can theoretically imagine a finer distinction, but whether the books themselves contain content that treats the finer distinctions as separate topics with separate explanations. In practice:

- If Book A defines الصرف اصطلاحًا in one unified way, and Book B defines it in the same unified way using different words, then `تعريف_الصرف_اصطالحا` is a leaf node. Both books' definitions are separate excerpts at the same node. The node has two excerpts, each from a different source, both addressing the same atomic topic.

- If Book A defines الصرف اصطلاحًا one way, and Book C defines it in a genuinely different way (different scope, different conditions, different scholarly tradition), then the system should consider whether this constitutes a scholarly disagreement that warrants either (a) two excerpts at the same node, with metadata noting the disagreement, or (b) expansion of the node into sub-nodes representing each position. The deciding factor is whether the disagreement is about the same atomic concept (→ same node, metadata notes the خلاف) or about genuinely different concepts that happen to share a name (→ sub-nodes).

- **The distinction between "different phrasing" and "genuinely different concept" is critical.** Two scholars saying the same thing in different words → same node, two excerpts. Two scholars defining a term with genuinely different scope or content → sub-nodes. Two scholars disagreeing about a rule → same node, with the disagreement captured as a خلاف marker in metadata (and potentially a dedicated خلاف sibling node, as the taxonomy trees already anticipate).

### 2c. The Relationship Between Excerpts and Taxonomy Expansion

The initial taxonomy trees (provided in this document for each of the four sciences) represent the **starting structure** — a comprehensive but not necessarily complete mapping of each science based on well-known topics. As books are processed:

1. **Most excerpts will map to existing leaf nodes.** This is the normal case.
2. **Some excerpts will reveal that an existing leaf node is not actually atomic** — the content shows it can be further subdivided. In this case, the leaf node becomes a parent, new child leaf nodes are created, and the excerpt is placed at the appropriate new leaf.
3. **Some excerpts will introduce entirely new topics** not present in the initial taxonomy. In this case, new nodes are created at the appropriate location in the tree.
4. **Some excerpts will challenge the tree's structure** — suggesting that a topic has been placed under the wrong parent, or that a branch should be reorganized. These cases must be flagged for human review rather than acted upon automatically, as restructuring has cascading effects on all previously placed excerpts.

The system must track all taxonomy changes with full audit history: what changed, when, why, and which excerpt triggered the change.

**There is no maximum nesting depth.** The depth of the taxonomy tree is determined entirely by the content of the books. If a topic genuinely subdivides to 10 levels of specificity, then the tree goes 10 levels deep at that point. Imposing an artificial ceiling (e.g., "no deeper than 6 levels") would force the system to either merge distinct concepts into a single node or violate its own rule — both are unacceptable outcomes that compromise precision.

However, as a practical safeguard: if the system proposes creating a node deeper than a configurable threshold (e.g., level 8), it should flag this for human review. This is not because deep nesting is inherently wrong, but because very deep nesting *might* indicate over-granulation, and a human should verify that the proposed sub-nodes represent genuinely distinct concepts rather than minor variations that belong at the same node. The flag is a safety net, not a prohibition.

### 2d. The Sovereignty of Excerpts Over the Taxonomy

This principle is absolute and non-negotiable:

**The excerpting process has one and only one goal: to identify, with maximum accuracy, every meaningful fragment of content in a book and correctly characterize what topic it addresses.** The taxonomy tree exists to *receive* those fragments. If a fragment does not fit the current tree, the tree changes. The fragment is never distorted, trimmed, re-characterized, or forced to fit an existing node.

To be explicit about what this means in practice:

- The system must **never** skip an excerpt because "there's no node for it." Instead, the system creates a node or flags for human review.
- The system must **never** assign an excerpt to a "close enough" node because the correct node doesn't exist yet. If the correct node doesn't exist, the system proposes a new node.
- The system must **never** merge two excerpts that address genuinely different sub-topics into a single excerpt because the taxonomy doesn't yet have separate nodes for them. Instead, the system proposes splitting the node.
- The system must **never** alter the text of an excerpt to make it "fit better" into a node. The excerpt text is a faithful copy of the source. Period.

At the same time, the taxonomy must not change frivolously. Every structural change — every new node, every reclassification, every split of an existing node — must be justified by genuine content that demands it. Cosmetic reorganizations, speculative sub-nodes created "in case future books need them," and restructuring for aesthetic symmetry are all prohibited. The tree evolves in response to real content, not in anticipation of hypothetical content.

**In summary: the content is the master. The taxonomy is the servant. The servant adapts to the master. The master never bends for the servant.**

### 2d-i. System Nodes (Operational Safety Nets)

The taxonomy tree's primary purpose is scholarly organization — mapping the landscape of a science into its constituent topics. However, the tree also needs **operational infrastructure** to ensure that the system functions reliably and that no excerpt is ever lost, silently misplaced, or guess-assigned.

The taxonomy therefore contains two categories of nodes:

**Scholarly nodes** — the actual taxonomy of the science. These are the nodes described throughout this document: topics, sub-topics, and leaf nodes representing specific concepts, rules, definitions, and distinctions. Scholarly nodes are the target of all excerpting activity.

**System nodes** — operational safety nets that exist to handle cases where the system cannot confidently place an excerpt into a scholarly node. System nodes include:

- `_unmapped`: excerpts that could not be matched to any existing scholarly node and for which the system could not confidently propose a new node. These await human classification.
- `_pending_review`: excerpts that have been tentatively placed but are queued for human verification (e.g., medium-confidence placements, or excerpts flagged by the multi-judge system — see §18e).
- `_uncertain_placement`: excerpts where the system identified two or more equally plausible scholarly nodes and could not decide between them. These await human disambiguation.
- `_cross_science_candidates`: excerpts from single-science books that the system suspects may contain content relevant to another science, queued for human evaluation.

System nodes are **not** part of the scholarly taxonomy. They are invisible to the synthesis LLM and play no role in the encyclopedic output. They exist solely as holding areas during the processing pipeline. Every excerpt in a system node must eventually be either moved to a scholarly node (through human review) or explicitly marked as non-relevant content (e.g., a printer's colophon, a table of contents, or purely administrative text in the source book).

The goal is that system nodes are empty after each book is fully processed and reviewed. A non-empty system node means there is unfinished work.

### 2e. The Comprehensibility Principle: Excerpt Independence

An excerpt must be **comprehensible in isolation**. A reader (or a future synthesis LLM) who sees only this excerpt and its metadata — without access to the rest of the book, without having read the preceding or following excerpts — should be able to understand:

- What topic is being discussed.
- What the author is saying about that topic.
- Enough context to make sense of the author's argument, even if the full depth of that argument requires reading more.

This is the driving motivation behind many of the rules in this document. The atom non-splitting rule (§1), the boundary atom duplication (§5), the شاهد inclusion (§6a), and the gap markers (§6c) all serve this principle.

**Practical implication:** if strict topic-boundary cutting would produce an excerpt that begins mid-thought, ends with an unresolved question, or contains a pronoun whose referent has been cut away, then the excerpt must be expanded to include the atoms needed for comprehensibility — even if those atoms technically belong to an adjacent topic. Their inclusion is recorded in the metadata (as context atoms with reasons), but they are present in the excerpt text because without them the excerpt fails the comprehensibility test.

The test is simple: **read the excerpt cold. Does it make sense? Can you understand what is being said and about what topic? If not, it needs more context, and that context must be included.**

This principle takes priority over minimizing topical overlap. A slightly broader excerpt that is fully comprehensible is always preferable to a tightly scoped excerpt that is confusing or incomplete.

---

## 3. Multi-Topic Atoms: The Duplication Rule

When a single atom substantively discusses two or more leaf node topics, that atom is **duplicated in full** into an excerpt for each relevant node. No attempt is made to split the atom.

**Example:** The atom "المبتدأ هو الاسم المرفوع العاري عن العوامل اللفظية، والخبر هو الجزء المتمّ للفائدة مع المبتدأ" covers both the definition of المبتدأ and the definition of الخبر. It is duplicated: one excerpt containing this atom is placed at the node `تعريف_المبتدأ`, and an identical excerpt containing the same atom is placed at the node `تعريف_الخبر`.

Each such excerpt's metadata must record that the atom is shared with other nodes (via `shared_atoms` in the blueprint), listing which nodes share it and the shared atom IDs.

---

## 4. Incidental Mentions vs. Substantive Discussion: The Dependency Test

Not every mention of a topic warrants duplication. The system must distinguish between:

- **Substantive discussion:** the passage actively explains, defines, argues about, or teaches the other topic. → The passage (or its relevant sentences) should appear as an excerpt under that other topic's node.
- **Incidental mention:** the passage references the other topic in service of explaining the current topic, without independently teaching anything new about the referenced topic. → No duplication needed; the mention is tolerated within the current topic's excerpt.

### The Dependency Test (Critical)

To determine which case applies, apply this test:

> **"Does this passage make sense as a contribution to the other topic if you strip away all reference to the current topic?"**

- If **yes** — the passage stands on its own as an explanation of the other topic — it is a substantive discussion and warrants its own excerpt under the other node.
- If **no** — the passage is syntactically or semantically anchored to the current topic, and the other topic is merely invoked as supporting context — it is an incidental mention and stays only in the current topic's excerpt.

**Example of incidental mention (no duplication):** "والمضاف إليه مجرور دائمًا، وعلامة جرّه الكسرة إن كان مفردًا أو جمع تكسير أو جمع مؤنث سالمًا" — the case-marking rules are invoked here, but the passage is anchored to الإضافة (note the pronoun جرّه referring to المضاف إليه). Strip away الإضافة and the sentence has no subject. This is an incidental mention.

**Example of substantive discussion (duplication needed):** If the same book later has a passage that says "علامات الجرّ: الكسرة في المفرد وجمع التكسير وجمع المؤنث السالم، والياء في المثنّى وجمع المذكر السالم، والفتحة نيابة عن الكسرة في الممنوع من الصرف" — this is an independent, self-contained explanation of case-marking rules. It stands on its own. It warrants an excerpt under the case-marking node(s).

### Implementation Requirement

**This test must not be implemented as a simple heuristic or static rule** (e.g., "check for personal pronouns"). It requires genuine language understanding — the ability to parse semantic dependencies, identify the true subject of a passage, and assess whether a passage is anchored to its surrounding context or is self-sufficient. This means the dependency test must be performed by an LLM capable of understanding Classical Arabic at a high level, not by a pattern-matching algorithm. The LLM must be prompted to reason carefully about the semantic structure of the passage before making a classification.

The gravity of getting this test wrong cannot be overstated. A false positive (classifying an incidental mention as a substantive discussion) produces unnecessary duplication — annoying but not catastrophic. A false negative (classifying a substantive discussion as an incidental mention) causes content to be **lost** from the node where it belongs — a silent, potentially undetectable error that degrades the encyclopedic completeness of that node. The system must be biased toward caution: when uncertain, classify as substantive (err on the side of duplication rather than loss).

### 4b. Discourse Patterns in Classical Arabic Scholarly Texts

Classical Arabic books — particularly in the sciences of النحو, الصرف, البلاغة, and الإملاء — employ a set of recurring discourse patterns that a naive excerpting system would misinterpret as topic switches. The system must recognize these patterns and handle them correctly. Failure to do so would result in excerpts with wrong boundaries, misplaced fragments, or artificially fragmented arguments.

The following is a non-exhaustive catalog of these patterns. The system's LLM component must be trained or prompted to recognize all of them, and the catalog should be expanded as new patterns are encountered during processing.

#### Pattern 1: The False Transition (العودة بعد الاستطراد)

The author appears to switch to a new topic — perhaps even using language that suggests a transition — but after several sentences returns to the original topic. The intervening sentences were a digression (استطراد), not a true topic change.

**How to recognize it:** the author often signals the return with phrases like "والمقصود أنّ...", "فنعود إلى ما كنّا فيه...", "وبالجملة فإنّ...", or simply resumes the original subject without explicit signaling. The key indicator is that the passage before and after the digression are about the same topic and form a coherent argument when read together (with the digression removed).

**How to handle it:** the entire passage — including the digression — belongs to the original topic's excerpt. The digression sentences are tagged in metadata as `digression: true` with a note about what topic the digression touched on. If the digression itself substantively discusses another topic (apply the dependency test), it is additionally duplicated as an excerpt at the other topic's node. But the original excerpt is never broken apart.

#### Pattern 2: The Contrastive Introduction (التعريف بالمقابلة)

The author introduces a topic by extensively describing what it is *not* — often by explaining a contrasting or adjacent topic at length. For example, a section on المفعول المطلق might begin with several sentences about المفعول به, explaining how المفعول المطلق differs from it.

**How to recognize it:** the contrastive topic is introduced in service of defining the current topic. The author's purpose is not to teach المفعول به but to use it as a foil. Structural cues include phrases like "وهو يخالف...", "وال ينبغي أن يُخلط بـ...", "والفرق بينه وبين...", and the overall section heading or context making clear that the current topic is what the author is explaining.

**How to handle it:** the contrastive sentences belong to the current topic's excerpt. They are *about* the current topic — they define it by contrast. They are not excerpts for the contrasting topic's node, unless they independently teach something about that topic that passes the dependency test.

#### Pattern 3: The Supplementary Aside (الفائدة / التنبيه)

The author inserts a labeled aside — typically marked with words like "فائدة", "تنبيه", "تتمة", "فرع", "مسألة" — that provides supplementary information related to the current topic. This looks like a mini topic switch because it has its own label, but it is actually a note within the current discussion.

**How to handle it:** this depends on the content of the aside. If the فائدة discusses a genuinely different leaf node topic, it is a separate excerpt placed at that topic's node (with metadata noting it was a فائدة within a discussion of the parent topic). If the فائدة is a supplementary detail about the current topic (e.g., a special case, a common mistake, a historical note), it stays within the current topic's excerpt, or becomes its own excerpt at a sub-node if the taxonomy warrants it. The label itself (فائدة, تنبيه, etc.) is preserved in the excerpt text and recorded in metadata as an indicator of the passage's role.

#### Pattern 4: The Build-Up Argument (التدرج في الاستدلال)

The author makes a general statement, then spends several sentences on what appears to be an unrelated tangent, and then reveals that the tangent was actually building evidence for the main point. The "tangent" sentences are integral to the argument and must not be separated from the main statement.

**How to recognize it:** this pattern often ends with a conclusion phrase like "فثبت بذلك أنّ...", "فتبيّن ممّا سبق أنّ...", "فعُلم من هذا أنّ...". The conclusion connects the seemingly tangential sentences back to the main topic. Without the conclusion, the tangential sentences look like they belong to a different topic; with it, they are clearly part of the current argument.

**How to handle it:** the entire argument — general statement, supporting sentences, conclusion — is one excerpt. The system must look ahead to the conclusion before deciding that the "tangent" sentences belong to a different topic. This is a case where sentence-by-sentence processing would fail; the system must analyze passages as discourse-level units.

#### Pattern 5: The Enumeration with Inline Explanations (التعداد مع الشرح)

The author lists several items (e.g., conditions for a rule, types of a construction) and provides a brief inline explanation for each. Each item might look like a separate topic, but the entire enumeration is a single coherent unit discussing one topic (the rule, the construction, the classification).

**How to recognize it:** the items share a common grammatical structure, often introduced by a framing sentence like "ويشترط فيه ثلاثة شروط:..." or "وهو على ثلاثة أقسام:...". Each item's explanation is brief and exists only to support the enumeration, not to independently teach its sub-topic.

**How to handle it:** if each item's explanation is brief (a sentence or two that merely identifies or labels the item), the entire enumeration stays as one excerpt at the parent topic's node. If any item's explanation is extensive enough to constitute standalone content about a sub-topic, that explanation may be separated into its own excerpt at a sub-node — but the framing sentence and the item's label are included in both the parent excerpt and the sub-node excerpt for comprehensibility.

#### Pattern 6: The Scholarly Dispute Block (ذكر الخلاف)

The author presents a scholarly disagreement: "قال البصريون كذا، وقال الكوفيون كذا، والراجح عندي كذا." This might look like it should be split into three excerpts (one per position), but the entire block is a single coherent discussion of a خلاف.

**How to handle it:** the entire dispute block is one excerpt, placed at the node that represents the topic being disputed. If the taxonomy has a dedicated خلاف sub-node for this topic, the excerpt goes there. Each position within the excerpt is tagged in metadata with its attribution (which scholarly school or individual holds it). The block is never split into separate excerpts for each position, because each position's explanation is typically incomprehensible without the others — the author is comparing and contrasting them as a unit.

#### General Principle for All Patterns

The common thread across all these patterns is that **the unit of analysis for excerpting is the author's discourse-level intention, not the surface-level topic of individual atoms.** The system must ask: "What is the author *doing* in this passage as a whole?" not "What topic does this atom mention?" An atom that mentions المفعول به might be *about* المفعول المطلق (Pattern 2). An atom that appears to start a new topic might be a digression that returns (Pattern 1). An atom that looks tangential might be evidence for the main argument (Pattern 4).

This is why the excerpting system cannot be an atom-level classifier. It must operate at the passage level, with awareness of discourse structure, authorial intent, and the conventions of Classical Arabic scholarly writing. This categorically requires LLM-level intelligence.

---

## 5. Transitional and Boundary Atoms

When a passage transitions from one topic to another, the transitional atom(s) — those that bridge the two topics — are included in the excerpts for **both** the preceding and the following topic.

**However, the transitional nature of these atoms must be recorded structurally in the metadata**, not by modifying the excerpt text itself. The excerpt text must remain a faithful, unmodified copy of the source.

Each excerpt carries a `boundary_atoms` metadata field that records:
- Which atom(s) within the excerpt are transitional (by atom ID).
- The direction of the transition: `trailing` (this atom transitions out of the current topic into a different one) or `leading` (this atom transitions into the current topic from a different one).
- The node(s) that the transition connects to.

**What does NOT happen:** the entire passage is not duplicated wholesale into both nodes. Only the boundary atom(s) are shared. The atoms that clearly and exclusively belong to topic A stay in topic A's excerpt; the atoms that clearly belong to topic B stay in topic B's excerpt; and the transitional atom(s) appear in both.

---

## 6. Shared Evidence (شواهد) and Multi-Observation Passages

Classical Arabic books frequently use a single شاهد (Quranic verse, poetry line, hadith, or example sentence) to illustrate multiple rules or observations. The handling depends on the structure of the explanation that follows the شاهد:

### 6a. Cleanly Separated Observations

If the author treats each observation independently (e.g., first explains the استعارة in the verse, then separately explains the طباق, then separately explains the إيجاز), then each observation becomes its own excerpt containing:

1. **The شاهد itself** — always included. An excerpt explaining a rule via a specific verse is incomplete without the verse.
2. **The general/introductory observation block** (if any) — included if it constitutes only incidental mentions of the other observations (brief listing, no detailed explanation). If the general block itself substantively explains any observation, apply the dependency test.
3. **The specific explanation for this observation's topic.**
4. **Gap metadata** (see below) noting that other explanations from the same passage exist as sibling excerpts at specified nodes.

### 6b. Interwoven Observations

If the author's explanations of multiple observations are interwoven at the atom level — meaning individual atoms discuss multiple observations and cannot be cleanly separated without splitting atoms — then the **entire block** (شاهد + general observations + all interwoven explanations) is kept intact and duplicated as a single excerpt into all relevant nodes.

Each such excerpt's metadata must include a flag: `interwoven_multi_topic: true`, along with a list of all nodes the interwoven content touches (`interwoven_nodes`). Additionally, all excerpts that are duplicates of the same inseparable passage must share an `interwoven_group_id` — a unique identifier for this group of duplicated excerpts. This alerts the future synthesis LLM that the excerpt contains substantive content about multiple topics that could not be separated without violating the atom non-splitting rule, and instructs it to treat the group as one canonical evidence block referenced from multiple nodes, **not** as independent evidence to be counted separately at each node.

### 6c. Gap Markers

When an excerpt's spans omit atoms from the middle of a source passage (because those atoms belong to a sibling excerpt for a different node), the excerpt's metadata must record:

- The exact position of the gap (between which spans — see `gap_markers` in the blueprint).
- What was omitted: a reference to the sibling excerpt(s) and their node(s).
- A brief contextual note describing what the omitted content covers (e.g., "3 atoms explaining the طباق in this verse; see excerpt at node X").

This ensures that the future synthesis LLM understands why there is a contextual jump within the excerpt and knows where to find the missing context if needed.

---

## 7. Multi-Layer Sources (متن، شرح، حاشية، تحقيق)

Many books in the classical Arabic tradition consist of multiple layers of scholarship:

- **المتن (core text):** the original author's work.
- **الشرح (commentary):** a later scholar's explanation of the متن.
- **الحاشية (marginal notes):** further commentary, often by yet another scholar.
- **تحقيق (editor's work):** the modern editor's contributions — which must be split into two sub-categories (see §7b).

### 7a. Rule: Each layer is a separate source for excerpting purposes.

If the متن contains a one-line definition and the شارح spends a paragraph expanding on that definition, these produce **two separate excerpts** at the same node: one attributed to the original author (المتن) and one attributed to the commentator (الشرح).

**Rationale:** the authority level, historical context, writing style, and scholarly perspective differ between layers. When the future synthesis LLM creates the encyclopedic entry for a node, it must know whether a claim comes from سيبويه (8th century, foundational authority) or from a 19th-century commentator (potentially representing a later scholarly consensus or a minority opinion). This granularity is essential for producing an output that captures scholarly agreement, disagreement, and the evolution of thought.

### 7b. The Critical Split: تحقيق-علمي vs. جهاز التحقيق

Modern editors (المحققون) produce two fundamentally different types of content, and the system must distinguish them sharply:

**تحقيق-علمي (scholarly editorial commentary):** the editor explains a grammatical rule, provides additional context, corrects a misunderstanding, or offers their own scholarly analysis. This is genuine scholarly content — it teaches something about the topic. It is treated as a full excerpting layer (`source_layer: تحقيق-علمي`), produces real excerpts at scholarly nodes, and is attributed to the editor as a scholar.

**جهاز التحقيق (textual apparatus):** variant readings (اختلاف النسخ), manuscript notes, bracketed clarifications [كذا في الأصل], bibliographic references, and observations about the physical manuscript. This is information about the *text itself*, not about the *topic*. It never produces excerpts and never gets a taxonomy node. It is captured purely as metadata attached to the relevant excerpt (see §15).

**Why this split matters:** without it, the system will either suppress valuable scholarly analysis by the editor (by treating all تحقيق as "just apparatus"), or pollute taxonomy nodes with manuscript trivia (by treating all تحقيق as scholarly content). Neither is acceptable.

### 7c. Exceptions:
- **Author's own footnotes:** if a footnote is clearly by the same author as the main text (not a later commentator), it is treated as part of the same layer (المتن) and incorporated into the same excerpt.
- **Pure references and bibliographic notes** by editors (e.g., "see also volume 3, page 42") are captured as cross-reference metadata rather than as standalone excerpts, since they contain no substantive scholarly content.

### 7d. Required metadata for multi-layer excerpts:
- `source_layer`: one of `متن`, `شرح`, `حاشية`, `تحقيق-علمي` — note: `جهاز التحقيق` content never becomes an excerpt and therefore never appears as a source_layer value.
- `source_author`: the author of this specific layer.
- `source_era`: approximate era/century of the author (when known), for historical contextualization.

---

## 8. Cross-References (إحالات)

When an author explicitly references another location in the same book or another topic ("وسيأتي بيان ذلك في باب الإضافة", "وقد تقدّم في باب المرفوعات أنّ..."), the excerpting system must capture these as structured metadata:

- `cross_reference_type`: `forward` (topic not yet encountered in this book) or `backward` (topic already discussed earlier in this book).
- `cross_reference_target`: the taxonomy node that the reference points to (if identifiable), or a textual description of the referenced topic if the exact node is not yet clear.
- `cross_reference_source_text`: the exact phrase used by the author (e.g., "وسيأتي بيان ذلك في باب الإضافة").

**These cross-references are not merely bookkeeping.** They reveal the author's own understanding of how topics relate to each other, which is valuable input for the synthesis LLM when it needs to understand inter-topic dependencies and the pedagogical ordering of concepts.

The system does **not** need to retrieve and paste the referenced text into the current excerpt. That would create redundancy and complexity. The cross-reference metadata is sufficient — it creates a navigable link that the synthesis LLM (or a human reviewer) can follow if needed.

---

## 9. Excerpt Length: Upper and Lower Bounds

### 9a. Lower Bound

The minimum possible excerpt is a single atom (a single sentence atom or a single bonded cluster atom, per §1). Single-atom excerpts are valid — a terse definition like "المفعول المطلق هو المصدر المنتصب توكيدًا لعامله أو بيانًا لنوعه أو عدده." is a complete, self-contained excerpt for the node `تعريف_المفعول_المطلق`.

However, single-atom excerpts frequently trigger the comprehensibility principle (§2e). If the atom refers to something established in a prior atom (e.g., begins with "وهو..." or "فإنّه...") or leaves a thought unresolved, it must be expanded to include enough context to be standalone. The system should be especially vigilant with short excerpts — a short excerpt that fails the comprehensibility test is worse than a slightly longer one that passes it.

### 9b. Upper Bound

There is no hard maximum length for an excerpt. If an author devotes 8 pages to a single leaf node topic with no topic change, no digression, and no transition — that is one excerpt. The length of an excerpt is determined by the content, not by an arbitrary page or word limit.

However, very long excerpts (exceeding approximately 2-3 pages of source text) should trigger a review flag, because they *may* indicate one of the following situations that the system should check:

- The node might not actually be a leaf node — the long passage might contain sub-topics that warrant splitting into child nodes. The system should re-examine the passage for internal structure.
- The passage might contain digressions or asides that were not detected as such. The system should re-examine for discourse patterns (§4b).
- The passage might be a multi-topic interwoven section that the system failed to detect. The system should re-examine for topic shifts.

If after re-examination the passage is genuinely one long, unified discussion of a single leaf node topic, the excerpt stands as-is. Its length is not a problem — it is simply a thorough treatment of the topic.

### 9c. Internal Navigation for Long Excerpts

For excerpts exceeding approximately 1 page of source text, the metadata should include an `internal_structure` field that captures any sub-structure within the excerpt: paragraph breaks, labeled sub-sections, enumerated points, etc. This helps the future synthesis LLM navigate the excerpt without requiring the LLM to re-analyze its structure from scratch. This is purely navigational metadata — it does not affect the excerpt's boundaries or placement.

---

## 10. Non-Prose Content (Tables, Charts, Paradigms, Lists)

Arabic grammar and morphology books frequently contain content that is not prose: conjugation tables (جداول التصريف), morphological paradigm charts, enumerated lists of examples, tree-like diagrams, and occasionally visual representations.

### 10a. Tables and Paradigm Charts

A conjugation table or paradigm chart is a valid excerpt. It is assigned to the taxonomy node it illustrates (e.g., a conjugation table for the pattern فَعَلَ يَفْعُلُ goes to the node for that specific باب).

**Dual representation (critical):** the "faithful copy" constraint (§2, point 5) requires that excerpt text is never modified. But tables need to be parsed into structured form for the synthesis LLM to process them. The resolution is dual storage, defined in the excerpt blueprint under `non_prose_representations`:

- `raw_block`: the exact text or HTML fragment as extracted from the source — this is the authoritative "faithful copy." It may contain formatting characters, alignment spaces, or HTML table tags. It is never altered.
- `structured_block`: a parsed JSON representation (rows, columns, headers, cell values) suitable for downstream computation and LLM consumption. This is a derived representation and is explicitly labeled as such.

The `raw_block` is authoritative. If there is any discrepancy between `raw_block` and `structured_block`, the `raw_block` is correct and the `structured_block` must be regenerated.

If a table is preceded or followed by explanatory prose atoms, those atoms and the table atom together form one excerpt. The table should not be separated from its explanatory context.

### 10b. Enumerated Lists

When an author provides a numbered or bulleted list (e.g., "شروط المفعول لأجله ثلاثة: 1. أن يكون مصدرًا 2. أن يكون قلبيًا 3. أن يتّحد فاعله مع فاعل الفعل"), the list and its introductory framing sentence form one excerpt at the parent topic's node.

If any individual list item receives extensive, standalone explanation (more than a brief identifying phrase), that item's explanation may be separated into its own excerpt at a sub-node — but the framing sentence and the item's label are included in both excerpts for comprehensibility (§2e).

### 10c. Poetry Lines and Quranic Verses as Content vs. as Evidence

A distinction must be maintained between a verse or poetry line that is the *subject* of analysis (the topic being discussed) versus one that serves as *evidence* (شاهد) for a rule. In a book on بلاغة, a Quranic verse being analyzed for its rhetorical devices is the topic — the excerpt is the analysis of that verse. In a book on نحو, the same verse cited to prove a grammatical rule is a شاهد — it belongs within the excerpt about the rule (per §6).

Metadata should record the role: `evidence_type: شاهد` (verse serving as evidence) or `evidence_type: محل_الدراسة` (verse being analyzed as the topic itself).

---

## 11. Examples (أمثلة), Exercises (تمارين), and Rules (قواعد)

Classical Arabic texts typically state a rule and then provide one or more examples. Some books also include exercises. The handling depends on the nature and extent of the content.

### 11a. Examples That Merely Illustrate

If an author states a rule and follows it with a few examples that simply demonstrate the rule without adding new information (e.g., "ومثال ذلك: كَتَبَ يَكْتُبُ، نَصَرَ يَنْصُرُ، ذَهَبَ يَذْهَبُ"), the examples are part of the rule's excerpt. They are not separated, because they have no independent content — they are evidence that the rule works.

### 11b. Examples That Contain Analysis

If an author provides examples with individual analysis — explaining *why* each example follows the rule, or noting edge cases for specific examples — then each analyzed example is potentially a separate excerpt at a more granular sub-node, if the taxonomy warrants it. The rule statement itself remains in the parent excerpt.

### 11c. Long Example Lists

If an author provides a very long list of examples (e.g., 30 examples of a specific morphological pattern), the list as a whole is one excerpt at the pattern's node. The list is not split into 30 individual excerpts unless individual items receive independent analysis. Long example lists should be flagged in metadata (`contains_example_list: true`, `example_count: 30`) so the synthesis LLM knows to treat them as illustrative inventories rather than analytical content.

### 11d. An Example That Reveals an Edge Case

If one of the author's examples actually illustrates a special case or exception (and the author notes this), that example and its discussion may warrant a separate excerpt at an exception/edge-case sub-node. The key test is: does the author treat this example as illustrating a *different rule or condition* than the main examples? If yes, it is a separate excerpt. If the author treats it as simply one more illustration of the same rule, it stays in the main excerpt.

### 11e. An Example That Introduces a New Concept (Critical Distinction)

Sometimes an author uses what appears to be an example as the vehicle for introducing and explaining an entirely new concept. The passage begins as an example of rule A, but the author's treatment of this example evolves into a substantive explanation of concept B — a concept that has its own identity, its own scope, and would warrant its own node in the taxonomy.

**This is NOT an example anymore.** It is substantive content that happens to have been introduced through the lens of an example. The system must recognize this and create an excerpt at a proper concept node for B — not file it under an "أمثلة" companion node for A.

The test: if the author's treatment of this "example" teaches something that a reader could not learn from the rule statement alone, and that teaching constitutes a genuinely new concept (not just an edge case of the existing rule), then it is a new concept node.

### 11f. Exercises (تمارين) and Practice Sections

Some books include explicit exercise or practice sections. These are structurally similar to example lists but serve a different pedagogical purpose (reader practice rather than rule demonstration).

Exercises are placed at a companion node alongside the topic they relate to (e.g., a تمارين node at the same level as the concept it practices). They are not placed inside the concept node itself, because they are not explanatory content — they are practice material. Their metadata records `content_type: تمارين` so the synthesis LLM can distinguish practice material from analytical content.

However, if an exercise section contains explanatory notes, hints, or solutions that substantively explain a concept, those explanatory portions are excerpted separately and placed at the appropriate concept node. The mere exercises (problems without analysis) stay at the تمارين companion node.

### 11g. Taxonomy Structure for أمثلة and تمارين

Companion nodes for examples and exercises sit at the same level as (or close to) the concept they illustrate — they are siblings, not children. This reflects their role: they support the concept, they don't subdivide it. The taxonomy structure for a given topic might look like:

- `شروط_المفعول_لأجله` (the concept node — receives rule statements and analysis excerpts)
  - `أمثلة_شروط_المفعول_لأجله` (companion node — receives illustrative examples)
  - `تمارين_شروط_المفعول_لأجله` (companion node — receives exercises)

Note: companion nodes are created only when the source books actually contain distinct example or exercise content. They are not speculatively pre-created for every concept node.

---

## 12. Repeated Content Within the Same Book

Authors of classical Arabic texts frequently revisit topics. An author might give a brief definition in chapter 1, a fuller treatment in chapter 5, and a passing reference in chapter 12. Each occurrence produces a separate excerpt at the same node, each with its own source location metadata.

### 12a. Linking Related Excerpts from the Same Source (Critical for Synthesis)

When the system detects multiple excerpts from the same book landing at the same node (or at closely related nodes), it must record linking metadata that conveys the **strength** of the relationship between these excerpts. This is not merely a convenience link — it is critical for preventing the synthesis LLM from producing an incomplete or distorted encyclopedic entry.

The danger is concrete: if an author explains half of a concept in chapter 3 and the other half in chapter 7, and the synthesis LLM encounters the chapter 3 excerpt without knowing that the chapter 7 excerpt exists and completes it, the LLM will treat the chapter 3 excerpt as a complete explanation and produce an entry that tells only half the story. This is a silent, severe error — the output *looks* correct but is fundamentally incomplete.

Each related excerpt from the same source carries a `same_source_links` metadata field with the following information for each linked excerpt:

- `linked_excerpt_id`: the ID of the related excerpt.
- `relationship_strength`: one of the following:
  - `continuation` — the two excerpts form a single intellectual unit that was physically separated in the book. Neither is complete without the other. **The synthesis LLM must read both together before producing output for this node.**
  - `elaboration` — one excerpt elaborates on, extends, or adds nuance to the other, but the first excerpt is comprehensible on its own. The synthesis LLM should incorporate both but can treat the first as the primary statement.
  - `recap` — one excerpt briefly recaps the other without adding substantive new content. The recap's value is primarily as evidence of the author's emphasis, not as independent content.
  - `revision` — one excerpt revises or corrects the other (see §14).
- `reading_order`: which excerpt should be read first (based on the book's order).

### 12b. Brief Recap vs. Substantive Revisit

Not every mention of a previously discussed topic warrants a new excerpt. If the author briefly recaps a topic ("وقد ذكرنا أنّ المبتدأ مرفوع") purely as a bridge to a new topic, this is not a new excerpt at المبتدأ's node — it is an incidental mention within the new topic's excerpt. The dependency test (§4) applies: does this recap independently teach anything about المبتدأ? A one-sentence recap almost certainly does not. A multi-sentence revisit that adds nuance or new conditions probably does.

---

## 13. Diacritics (التشكيل) and Text Normalization

### 13a. Preservation of Original Diacritics

The excerpt text must faithfully preserve whatever diacritization the source provides. If the source has full تشكيل, the excerpt has full تشكيل. If the source has none, the excerpt has none. The system must **never** add, remove, or alter diacritics in the excerpt text. The excerpt is a faithful copy of the source.

### 13b. Normalization for Matching and Search

For the purposes of matching content to taxonomy nodes, identifying duplicates, and searching across excerpts, the system should maintain a **normalized** version of the text alongside the original. The normalized version would strip diacritics, normalize ة/ه variants, normalize ي/ى variants, and handle other encoding inconsistencies (see the taxonomy tree section on يونيكود واشكال الحروف). This normalized version is stored in metadata; the excerpt text itself is never altered.

### 13c. Metadata on Diacritization Level

Each excerpt should record the diacritization level of its source: `full` (every word vowelized), `partial` (some words vowelized, typically ambiguous words), `minimal` (only occasional diacritics), or `none`. This helps the synthesis LLM calibrate how much to trust the source's morphological precision and may affect which source is preferred when multiple excerpts cover the same content at different diacritization levels.

---

## 14. Contradictions and Self-Corrections Within a Source

### 14a. Explicit Self-Corrections

When an author explicitly corrects or revises an earlier statement (signaled by phrases like "وقد كنت ذكرت... والصواب أنّ...", "والأولى أن يقال...", "وأعدل عمّا ذكرته سابقًا..."), both the original statement and the correction become excerpts at the same node, and the metadata of each records:

- `revision_relationship`: `original` or `revised`.
- `linked_excerpt_id`: pointing to the other excerpt.
- `revision_signal`: the exact phrase the author used to signal the revision.

The synthesis LLM must know which statement the author ultimately endorses.

### 14b. Implicit Contradictions

When the same author says something in chapter 3 that appears to contradict what they said in chapter 7, without any explicit acknowledgment of the change, both excerpts are recorded at the same node, and the metadata includes a `potential_contradiction` flag. This is flagged for human review, because the contradiction might be apparent rather than real (the two passages might address slightly different conditions, or the apparent contradiction might resolve with careful reading).

The system must **never** silently discard one of two contradictory statements. Both are preserved; the contradiction is flagged; a human decides.

---

## 15. Editorial Interventions and Scholarly Apparatus (جهاز التحقيق)

This section specifies the handling of **جهاز التحقيق** — the textual apparatus produced by modern editors. This is distinct from **تحقيق-علمي** (the editor's scholarly commentary), which is treated as a full excerpting layer in §7b.

جهاز التحقيق includes:

- **Bracketed clarifications:** text in square brackets [كذا في الأصل] or [أي: كذا] inserted by the editor to clarify or correct the manuscript text.
- **Variant readings (اختلاف النسخ):** notes listing how different manuscripts read a particular passage (e.g., "في نسخة أخرى: كذا").
- **Manuscript notes:** observations about the physical manuscript (lacunae, illegibility, damage).
- **Editor's scholarly footnotes:** the editor's own analysis, corrections, or contextualizations — these overlap with تعليقات المحقق in §7 and are treated as a separate source layer.

### Core Rule: Editorial apparatus never gets its own taxonomy node.

These are extreme details of the text's transmission history, not scholarly content about the science being discussed. They are captured purely as metadata on the excerpt they relate to. Variant readings, manuscript notes, and bracketed clarifications exist to support the integrity and reliability of the excerpt text — they are not topics in the taxonomy.

### Exception: Meaning-Altering Variants

The sole exception is when a variant reading would **change the meaning** of the scholarly content in a way that affects how the topic is understood. For example, if one manuscript reads "يجب" (obligatory) and another reads "يجوز" (permissible), the difference is not a trivial scribal variation — it represents a substantive disagreement about the rule. In such cases, the variant is noted prominently in the excerpt metadata (`meaning_altering_variant: true`) and flagged for human review, because the choice of reading may affect which node the excerpt belongs to or how the synthesis LLM should treat the excerpt's content. But even in this case, the variant does not become a separate taxonomy node — it remains metadata, albeit metadata with a high-priority review flag.

### Handling:

Bracketed clarifications within the text are preserved in the excerpt as-is (they are part of the published text the reader encounters). Their presence is noted in metadata (`has_editorial_brackets: true`).

Variant readings are captured as metadata on the excerpt (`variant_readings`: list of alternatives and their manuscript sources). They are not separate excerpts because they are not scholarly content about the topic — they are information about the text itself.

Manuscript notes about damage or illegibility trigger a `text_integrity` flag in metadata: `complete`, `partially_illegible`, or `lacuna`. If a passage is partially illegible, the excerpt includes whatever is legible, and the metadata records what is missing or uncertain.

---

## 16. Cross-Science Content Handling

Books may contain content that touches on sciences other than their declared primary science. The handling depends critically on whether the book is classified as covering one science or multiple sciences.

### 16a. Single-Science Books

When a book is tagged as being about **one** science (e.g., a book about علم النحو), the system uses **only that science's taxonomy** for excerpting. All excerpts go to nodes within that science's tree.

If the author mentions a concept from another science (e.g., a morphological rule from الصرف while explaining a grammatical construction), that mention stays within the current science's excerpt. It is treated as background knowledge or necessary context — not as content that should be routed to the other science's taxonomy.

**Rationale:** a single-science book's treatment of another science is inherently limited. It is a reminder, a prerequisite, a bridge — not a full, authoritative treatment on the level that a dedicated book about that other science would provide. Routing such incidental cross-science mentions to the other science's taxonomy would pollute that taxonomy with shallow, contextual fragments that lack the depth and completeness expected of excerpts in their home science. The dependency test (§4) still applies within the excerpt for the current science — the system determines whether the cross-science mention is incidental or substantive *for purposes of the current science's excerpting* — but even a "substantive" mention in a single-science book does not cross taxonomic boundaries.

However, if the system detects content that appears to be a genuinely extensive, standalone explanation of another science's topic — unusual for a single-science book but not impossible — the excerpt is placed in the `_cross_science_candidates` system node (§2d-i) and flagged for human review. The human decides whether the content truly warrants placement in another science's taxonomy.

**Mandatory resolution for `_cross_science_candidates`:** every item in this system node must be resolved into exactly one of the following outcomes before the book is considered fully processed:

1. **Duplicate into other science:** the content genuinely warrants placement in the other science's taxonomy. A copy of the excerpt is created with the other science's taxonomy node as its core node, with `cross_science_placement` metadata. The original excerpt remains in its home science.
2. **Retain in home science only:** the content is contextual/background, not a full treatment. It stays only in the home science's excerpt, with a `cross_science_note` metadata field recording that the content was evaluated and deemed insufficient for cross-science placement.
3. **Discard as non-scholarly:** the content is administrative, transitional, or otherwise not scholarly content at all (e.g., a table of contents entry, a printer's note). It is removed from the `_cross_science_candidates` node and not placed in any scholarly node.

### 16b. Multi-Science Books

When a book is tagged as covering **multiple** sciences (e.g., كتاب المنهاج المختصر في علمي النحو والصرف), the system must use the taxonomy trees of all declared sciences. The system must be able to recognize when the author transitions from genuinely teaching one science to genuinely teaching another, and route excerpts to the appropriate taxonomy.

**This is the critical intelligence requirement:** the system must distinguish between:

- **Full explanation as a dedicated topic:** the author is now teaching صرف as a primary subject. The content is substantive, complete, and at the level of depth expected in a dedicated صرف book. → Route to the صرف taxonomy.
- **Background mention / repetition of necessary knowledge:** the author is still teaching نحو but briefly reviews a صرف concept because the reader needs it as prerequisite context. → Keep in the نحو excerpt. Do not route to the صرف taxonomy.

This distinction is fundamentally the same intelligence the system needs for detecting topic transitions within a single science (§4, §4b), applied at the inter-science level. The dependency test applies: does this passage function as an independent, self-sufficient explanation of the other science's topic? If yes, it is a full explanation and goes to that science's taxonomy. If no, it is background context and stays where it is.

### 16c. The Importance of This Distinction

This cannot be overstated: **the system must be extremely reliable at distinguishing "this is now a new topic being taught as a first-class subject" from "this is a brief mention of necessary background knowledge."** Getting this wrong in either direction has serious consequences.

False positive (routing background knowledge to another science's taxonomy): the other science's taxonomy gets polluted with shallow, incomplete fragments that don't meet the quality standard of dedicated treatment. The synthesis LLM for that science encounters these shallow fragments alongside deep, authoritative excerpts and may produce a confused or diluted encyclopedic entry.

False negative (failing to route a full explanation to its science's taxonomy): substantive scholarly content about a topic is lost — it exists only as an aside within another science's excerpt, where the synthesis LLM for the topic's actual science will never see it.

This distinction must be implemented with LLM-level intelligence and the multi-judge consensus approach (§18e), and all cross-science routing decisions in multi-science books should be flagged for human review at Checkpoint 2 (§18b).

---

## 17. Ambiguous and Unclassifiable Passages

### 17a. When the System Cannot Determine the Topic

If the system encounters a passage and cannot determine with adequate confidence which taxonomy node it belongs to — either because the topic is genuinely ambiguous, because the passage could plausibly belong to two unrelated nodes with equal justification, or because the topic does not appear in any current taxonomy tree — the passage must be:

1. Excerpted normally (boundaries determined, text preserved, metadata populated to the extent possible).
2. Placed in the appropriate **system node** (§2d-i) based on the nature of the uncertainty:
   - `_unmapped`: the topic does not match any existing scholarly node and no new node can be confidently proposed.
   - `_uncertain_placement`: two or more scholarly nodes are equally plausible and the system cannot decide.
   - `_pending_review`: the system has a tentative placement but confidence is below the auto-place threshold.
3. The `review_status` field is set to `pending_classification` or `pending_review` accordingly.

**There is no separate "pending classification queue."** The system nodes ARE the queuing mechanism. All uncertainty routing, status tracking, and resolution happens through system node placement combined with the `review_status` field. This ensures a single authoritative location for every excerpt — it is either at a scholarly node or at a system node, never in both and never in an additional side queue.

The system must **never silently guess**. A confidently wrong placement is far more dangerous than an honestly flagged uncertainty, because wrong placements are invisible — they look like normal excerpts — while system node placements are explicitly queued for human attention.

### 17b. Confidence Thresholds

Every taxonomy placement must have a confidence score. The system should define configurable thresholds:

- **High confidence** (above threshold A): auto-place at scholarly node, `review_status: pending_review` (still subject to human review at Checkpoint 2).
- **Medium confidence** (between threshold A and B): auto-place at scholarly node tentatively, `review_status: pending_review` with elevated priority flag.
- **Low confidence** (below threshold B): place at appropriate system node. Do not assign to a scholarly node.

The exact threshold values should be calibrated during the gold-standard testing phase (§19) and adjusted as the system processes more books and its accuracy can be measured.

### 17c. Invariant: System Nodes Must Be Empty Post-Review

After a book has been fully processed and reviewed at all checkpoints, every system node must be empty. Every excerpt must have been resolved into either a scholarly node placement (approved by human) or an explicit exclusion (marked as non-scholarly content with reason). A non-empty system node means there is unfinished work, and the book is not considered complete.

---

## 18. Human Review Checkpoints

Given the zero-tolerance standard for errors in this project, the system must include mandatory human review stages. Fully automated end-to-end processing is not acceptable for this project. The system is a precision tool that maximizes human reviewer efficiency — it does the heavy lifting of proposing excerpts and placements, but a human confirms the critical decisions.

### 18a. Checkpoint 1: Input Parsing and Atomization Verification

**When:** after the system parses a book's raw source (HTML, text, etc.) into structured text segments AND atomizes the text into a sequence of atoms (§1b), before any excerpting logic runs.

**What the reviewer checks:** that the text was parsed correctly — nothing was lost, garbled, or misattributed. That multi-layer content (متن, شرح, حاشية, تحقيق-علمي vs جهاز التحقيق) was correctly separated. That tables, poetry, and non-prose content were correctly identified as their respective atom types. That the book's overall structure (chapters, sections) was correctly detected and heading atoms were properly tagged. That sentence boundaries were correctly identified and semantically bonded clusters were properly merged into single atoms. That the resulting atom sequence is complete (no content lost between atoms) and correct (no atom contains content from two different source layers).

**Interface requirements:** a side-by-side view of the original source and the atomized output, with color-coding for atom types (sentence, bonded cluster, heading, verse/poetry, table/paradigm). The reviewer can flag and correct parsing errors, split incorrectly-merged atoms, merge incorrectly-split atoms, and reclassify atom types.

### 18b. Checkpoint 2: Excerpt Boundary and Placement Review

**When:** after the system proposes excerpt boundaries and taxonomy placements for a book (or a section of a book).

**What the reviewer checks:** that excerpt boundaries are correct (no atom was split, no atom is orphaned between excerpts, no excerpt fails the comprehensibility test). That taxonomy placements are correct (each excerpt is at the right node). That duplication decisions are correct (shared atoms are properly duplicated, incidental mentions are not over-duplicated). That the core/context distinction is accurate (context atoms are genuinely contextual, not misclassified core content). That metadata is accurate (boundary atoms, cross-references, contextual notes).

**Interface requirements:** each proposed excerpt is displayed with its assigned node, its confidence score, its metadata, and the surrounding context from the source. The reviewer can adjust boundaries (merge, split, expand, shrink), reassign nodes, edit metadata, and flag issues. The system must be able to learn from corrections — if the reviewer consistently adjusts a particular type of boundary or reclassifies a particular type of passage, the system should adapt its behavior for future books.

**This is the most critical checkpoint.** It is where the reviewer spends the most time, and where the most value is created. The system should be optimized to make this review as efficient as possible — for example, by ordering excerpts by confidence (lowest first), by highlighting uncertain decisions, and by allowing batch approval of high-confidence excerpts.

### 18c. Checkpoint 3: Taxonomy Change Review

**When:** whenever the system proposes a structural change to the taxonomy tree — a new node, a node split, a reclassification, a reorganization.

**What the reviewer checks:** that the proposed change is justified by genuine content (not cosmetic or speculative). That the proposed node name and position are correct. That existing excerpts at affected nodes are still correctly placed after the change. That the change is consistent with the overall taxonomy structure and naming conventions.

**Interface requirements:** a visualization of the affected portion of the taxonomy tree, showing the proposed change, the excerpt(s) that triggered it, and any existing excerpts that would be affected. The reviewer can approve, modify, or reject the proposed change.

### 18d. Learning from Corrections

The system should maintain a log of all human corrections made at each checkpoint, categorized by error type:

- Boundary errors: where the system drew an excerpt boundary wrong.
- Placement errors: where the system assigned an excerpt to the wrong node.
- Duplication errors: where the system over-duplicated or under-duplicated.
- Discourse pattern errors: where the system misidentified a discourse pattern (e.g., treated a digression as a topic switch, or vice versa).
- Taxonomy errors: where the system proposed an unjustified tree change, or failed to propose a needed one.

Over time, this correction log should be analyzed to identify systematic weaknesses and used to refine the system's prompts, thresholds, and heuristics. The goal is that the system improves with each book processed, requiring less and less human correction — but human review is never fully removed.

### 18e. Multi-Judge Consensus Approach (Extraction Methodology)

Given the zero-tolerance standard for errors, the system must not rely on a single LLM's judgment for critical decisions. Instead, the system employs a **multi-judge consensus approach**: for each excerpting decision (boundary determination, taxonomy placement, dependency test, discourse pattern identification), multiple independent judges evaluate the same passage and their outputs are compared.

**How it works:**

For each passage being excerpted, the system submits the passage to multiple independent judges. These judges may be different LLMs (e.g., Claude and GPT), the same LLM with different prompts or system instructions emphasizing different aspects of the rules, or the same LLM at different temperatures to capture the range of plausible interpretations. Each judge independently proposes excerpt boundaries, taxonomy placements, and metadata.

The system then compares the judges' outputs:

**Full agreement** across all judges → high confidence. The decision is likely correct. Auto-place, subject to routine human review at Checkpoint 2.

**Majority agreement** (e.g., 3 out of 4 judges agree) → medium confidence. The decision is probably correct but the disagreement indicates ambiguity. Auto-place tentatively, but flag for priority human review with the dissenting judge's reasoning attached.

**No majority agreement** → low confidence. The passage is genuinely ambiguous or the rules are insufficient to determine the correct answer. Send to `_pending_review` system node. Do not guess. Include all judges' proposals and reasoning so the human reviewer can see the full picture.

**Which decisions use multi-judge consensus:**

Not every decision needs the full multi-judge treatment — that would be prohibitively expensive. The system should use multi-judge consensus for:

- Excerpt boundary decisions where the passage contains any of the discourse patterns from §4b (false transitions, contrastive introductions, etc.) — these are the decisions most prone to error.
- Taxonomy placements where the system's primary judge assigns a confidence below a configurable threshold.
- The dependency test (§4) whenever the outcome is not immediately obvious — this test is the single highest-stakes decision in the entire pipeline.
- Cross-science routing decisions in multi-science books (§16b).
- Proposed taxonomy tree changes (new nodes, splits, reorganizations).

Straightforward cases — clear single-topic paragraphs with obvious taxonomy placements — can use a single judge to keep costs manageable. The system should learn over time which types of passages benefit from multi-judge consensus and which do not, adjusting its strategy based on the correction log from §18d.

---

## 19. Gold-Standard Examples and Calibration

### 19a. Purpose

Before the system processes its first book, it must be calibrated against manually-produced gold-standard examples. These examples serve three purposes: they define the expected output concretely (removing any remaining ambiguity in the rules), they provide a test suite for measuring the system's accuracy, and they provide training signal for refining the system's LLM prompts and parameters.

### 19b. What a Gold-Standard Example Contains

A gold-standard example consists of:

1. **A source passage** — a 10-20 page section from a real Arabic book in one of the four sciences. The passage should be chosen to include a variety of situations: straightforward single-topic content, multi-topic atoms, transitional passages, at least one shared شاهد, at least one discourse pattern from §4b (e.g., a false transition, a contrastive introduction), and ideally a cross-science mention.

2. **The manually-produced excerpts** — every excerpt that should be extracted from the passage, with exact text, exact boundaries (atom IDs), and the target taxonomy node.

3. **The full metadata for each excerpt** — every field from the excerpt blueprint (§2-blueprint), filled in by hand. This includes boundary atoms, gap markers, cross-references, contextual notes, and all flags.

4. **A decision log** — for each non-obvious excerpting decision (boundary placement, duplication choice, discourse pattern handling), a brief explanation of *why* the decision was made, referencing the specific rule from this document that governed it. This makes the gold standard not just a test case but a teaching tool — the system (and future human reviewers) can learn from the reasoning, not just the outcome.

### 19c. How Many Gold-Standard Examples Are Needed

At minimum, one gold-standard passage per science (4 total), covering the most common content patterns in that science. Ideally, additional examples covering specific edge cases: a heavily multi-layered text (متن + شرح + حاشية), a text with minimal punctuation, a text with extensive cross-science content, and a text with many scholarly disputes. A realistic target is 8-12 gold-standard passages before development begins, with additional passages added as new edge cases are discovered during development.

### 19d. When to Create Gold-Standard Examples

The first gold-standard example should be created **before any code is written**, as soon as the excerpting rules are finalized. It serves as the specification's ultimate test: if the author of the rules (Rayane) cannot consistently apply them to produce a clean result, the rules themselves need refinement. Subsequent gold-standard examples can be created in parallel with early development, providing an expanding test suite as the system matures.

### 19e. Ongoing Calibration

After the system begins processing books, its output on each gold-standard passage should be compared to the manually-produced version. Discrepancies are categorized as either system errors (the system violated the rules) or rule gaps (the rules don't cover this situation). System errors lead to technical fixes; rule gaps lead to updates to this document. The gold-standard suite grows over time as new edge cases are encountered.

---

## 20. Excerpt Metadata Schema

The complete metadata schema is defined in the Excerpt Object Blueprint in §2-blueprint. That blueprint is the single authoritative reference for all metadata fields, their types, and whether they are required, conditional, or computed.

This section is retained as a section number placeholder for cross-referencing purposes. All metadata details live in §2-blueprint.

---

## Appendix A: Open Items Deferred to Problem 2 (Data Model)

The following items were identified during spec review as valid concerns that belong to the data model and system architecture specification, not the excerpt definition. They are recorded here to ensure they are not forgotten.

**A1. Taxonomy versioning and migration semantics.** When a leaf node is split into children (§2c), existing excerpts sit on a now-non-leaf path. The data model must define: taxonomy version tracking, what happens to existing excerpts on node split (migration vs. flagging), and how the "exactly one leaf node" requirement interacts with taxonomy evolution over time.

**A2. Excerpt revision lineage.** The excerpt_id is immutable (§2-blueprint), but Checkpoint 2 allows humans to change boundaries, merge, split, expand, shrink, and reassign excerpts. The data model must define whether modifications create new excerpt objects (immutable model with `supersedes_excerpt_id`) or version existing ones (versioned model with `revision_id`), and how the audit trail preserves history without overwriting it.

**A3. context_hash specification.** The exact window (how many atoms before/after), the exact payload (atom IDs + raw text + anchors?), and the canonicalization rules for hashing must be specified during implementation. The excerpt definition requires that verification be possible; the exact algorithm is an engineering decision.

**A4. Coverage invariant and automated checking.** A formal, machine-checkable coverage invariant should be defined: every atom in a source layer must be either core-covered (appears as a core atom in exactly one excerpt), explicitly excluded (marked non-scholarly with reason), or pending (in a system node). Context duplication does not count toward core coverage. An automated coverage report should be produced after each book is processed.
