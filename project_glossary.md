# Arabic Book Digester — Project Glossary

This document defines ABD’s project-specific terminology.

**Normative rules** (including conflict resolution) live in `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md`. When documents disagree, follow the binding precedence order; use this glossary to interpret terms, not to override binding rules.

**Who reads this:** The AI software builder that will implement the extraction application, any LLM performing extraction or synthesis, and human annotators creating gold standard passages.

**What this is NOT:** This is not the excerpting rulebook (that is `4_excerpting/EXCERPT_DEFINITION.md`, the single source of truth for what an excerpt IS). This is not the step-by-step procedure (that is `2_atoms_and_excerpts/extraction_protocol_v2.4.md`). This document defines **what things are**, not how to do them.

---

## 1. The Project

### Arabic Book Digester
The application being built. It takes Arabic books as input, decomposes them into excerpts, and places each excerpt at the correct leaf node in a taxonomy folder tree (one tree per science). The pipeline stages are: **intake** → **enrichment** → **normalization** → **structure discovery** → **extraction (atomization + excerpting + placement)** → **taxonomy trees** → **taxonomy evolution** → **assembly + distribution**. An external synthesis LLM (outside this repo) reads all excerpt files at each leaf folder and produces encyclopedia articles — ABD's job ends at producing well-structured, accurately placed excerpts. See the Pipeline Stages section below for details and status of each stage.

### The Four Sciences
The project covers four classical Arabic linguistic sciences. Each science has its own taxonomy tree. A book typically belongs to one science but may contain content relevant to others.

| ID | Arabic | English | Scope |
|----|--------|---------|-------|
| `balagha` | علم البلاغة | Rhetoric | المعاني، البيان، البديع |
| `nahw` | علم النحو | Syntax | إعراب، تراكيب، عوامل |
| `sarf` | علم الصرف | Morphology | أوزان، تصريف، أبنية |
| `imlaa` | علم الإملاء | Orthography | رسم، همزة، تاء |

When an excerpt involves a science outside these four, the `related_science` field uses:

| ID | Arabic | English |
|----|--------|---------|
| `3arud` | علم العروض | Prosody (meter and rhyme) |
| `lughah` | لغة | Lexicography / general linguistics |
| `other` | — | Any science outside the above |

### Pipeline Stages

**Intake (Stage 0):** Registers a new book into the project. Freezes the source HTML, creates `intake_metadata.json`, assigns `book_id`, and records scholarly context placeholders. Tool: `tools/intake.py`. ✅ Complete.

**Enrichment (Stage 0.5):** Researches and fills the author's scholarly context — death date, فقه madhab, grammatical school, geographic origin. Tool: `tools/enrich.py`. 🟡 Basic — needs extension into intelligent research.

**Normalization (Stage 1):** Transforms raw Shamela HTML into a clean, page-per-line JSONL file (`pages.jsonl`). Handles HTML stripping, Unicode normalization, whitespace normalization, footnote separation, and structural marker detection. Deterministic — no LLM. Tool: `tools/normalize_shamela.py` (~1120 lines). ✅ Complete.

**Structure Discovery (Stage 2):** Discovers the book's internal structural divisions and defines passage boundaries. Uses a three-pass algorithm: Pass 1 extracts HTML-tagged headings (deterministic), Pass 2 applies keyword heuristics (deterministic), Pass 3 uses LLM for gap detection, hierarchy assignment, and digestibility classification. Produces `divisions.json` and `passages.jsonl`. Tool: `tools/discover_structure.py` (~2856 lines). ✅ Complete.

**Extraction (Stages 3+4 combined):** The core operation. For each passage, an LLM atomizes the text (breaks it into typed atoms), groups atoms into self-contained excerpts, assigns taxonomy placement per excerpt, and generates exclusion records. Includes 17-check validation with automatic correction retries. Combines what were originally separate atomization and excerpting stages. Tool: `tools/extract_passages.py` (~1389 lines). 🟡 Single-model complete; multi-model consensus not yet built.

**Taxonomy Trees (Stage 5):** Build and maintain the base taxonomy YAML trees for each science. Each science needs a tree before extraction can place excerpts into it. Trees are stored in `taxonomy/`. 🟡 إملاء exists (`imlaa_v0.1.yaml`, 44 leaves); بلاغة exists (`balagha_v0_4.yaml`, 143 leaves); صرف and نحو not yet created.

**Taxonomy Evolution (Stage 6):** Detects when the taxonomy tree needs finer granularity, proposes new sub-nodes, redistributes existing excerpts, and applies changes with human approval. ❌ Not yet built.

**Assembly + Distribution (Stage 7):** Assembles self-contained excerpt files (inline text + embedded metadata) and places them in the taxonomy folder tree (one file per excerpt per leaf). ❌ Not yet built.

**Synthesis (external):** Handled by an external LLM outside this repo. It reads all excerpt files at each taxonomy leaf folder and produces a single comprehensive encyclopedic entry per leaf, aimed at Arabic-language students. When authors disagree, it presents all scholarly positions and attributes each to its author. Synthesis is NOT a stage of ABD — but every design decision within ABD (excerpt boundaries, metadata richness, roles, relation chains, author context) is made to serve the downstream synthesis LLM.

---

## 2. Source Material

### Book (كتاب)
An Arabic text to be processed. Identified by a short lowercase **book_id** (e.g., `jawahir` for جواهر البلاغة). A book belongs to one primary science but may contain cross-science content.

### Source Layer (طبقة المصدر)
Arabic scholarly texts often have multiple textual layers stacked on the same page. Each layer is a separate voice with its own author:

| ID | Arabic | Meaning |
|----|--------|---------|
| `matn` | متن | The primary authored text — the book itself |
| `footnote` | حاشية المحقق | Editor/publisher footnotes in modern editions (the common case of تحقيق) |
| `sharh` | شرح | A classical commentary written by a different scholar on the متن |
| `hashiya` | حاشية | A super-commentary on the شرح (a third scholarly layer) |
| `tahqiq_3ilmi` | تحقيق علمي | Substantive editorial commentary that goes beyond apparatus footnotes |

**Critical rule:** each excerpt draws from exactly one layer. All its core atoms and context atoms must share that layer. Cross-layer relationships (e.g., a footnote supporting the متن) are expressed through **relations** connecting separate excerpts, never by mixing layers within one excerpt.

### Passage (مقطع)
A contiguous section of a book selected for processing (e.g., pages 19–25). Passages are processed sequentially. Atom IDs and excerpt IDs are globally sequential within a book — they never reset between passages. A passage is the unit of work: one extraction session produces one passage's worth of atoms, excerpts, and exclusions.

### Canonical Text (النص القياسي)
A plain text file constructed by joining all atoms in a single layer with newline separators. The canonical text is a **derived artifact** — it is built FROM the atoms, not independently. It exists solely so that character offsets (`source_anchor`) can be validated: the invariant `atom.text == canonical_text[char_offset_start:char_offset_end]` must always hold.

There is one canonical text file per source layer per passage (e.g., `passage1_matn_canonical.txt` for the متن layer, `passage1_fn_canonical.txt` for the footnote layer).

---

## 3. Atoms

### Atom (ذرّة)
The smallest indivisible unit of text in the pipeline. Once created during atomization, an atom is never split. All downstream operations (excerpting, exclusion, synthesis) work with atoms as their fundamental building blocks.

Every atom has a unique, immutable **atom_id** in the format `{book_id}:{layer_token}:{six_digit_sequence}` (e.g., `jawahir:matn:000004`). Sequence numbers are assigned in reading order within each layer, globally sequential within a book.

**Layer token mapping:** The `layer_token` in atom IDs is an abbreviation of the `source_layer` value. The two are not always identical:

| `source_layer` | `layer_token` in atom_id | Canonical filename key |
|-----------------|--------------------------|----------------------|
| `matn` | `matn` | `matn` |
| `footnote` | `fn` | `footnote` |
| `sharh` | `sharh` | `sharh` |
| `hashiya` | `hashiya` | `hashiya` |
| `tahqiq_3ilmi` | `tahqiq` | `tahqiq_3ilmi` |

When the AI builder parses an atom_id like `jawahir:fn:000003`, the `fn` token maps to `source_layer=footnote`. This table is the authoritative mapping.

### Atom Types

**prose_sentence** — The default and most common type. A single complete Arabic sentence, terminated by terminal punctuation (`.` `؟` `?` `!`) or a paragraph break. The following are NOT sentence boundaries: `،` `,` `؛` `;` `:` and em-dashes.

**bonded_cluster** — Two or more consecutive sentences merged into a single atom because separating them would make one or both meaningless. Every bonded cluster must have a **bonded_cluster_trigger** explaining the bond (see below). The conservative rule: when unsure whether to merge, prefer merging — a wrongly-split atom creates fragments that violate comprehensibility and cannot be undone, whereas a slightly too-large atom only reduces granularity. Use bonded_cluster sparingly and always justify the trigger.

**heading** — A section or chapter marker (باب، فصل، مسألة، تنبيه، فائدة, numbered headings, etc.). Short, typically no verb, no predication. Headings are structural metadata: they are always **excluded** from excerpts but **referenced** in heading_path. See *Heading Dual-State Principle*.

**verse_evidence** — Poetry cited by the author as evidence or illustration. Covers any verse unit as quoted: full bayt (بيت كامل), single hemistich (مصراع واحد), or verse fragment. The atom type captures the *form* (it's verse); the *role* within an excerpt captures the function (evidence, exercise content, etc.).

**quran_quote_standalone** — Quranic text appearing as its own atom (not embedded within a prose sentence). When Quran text is woven into prose, it is tagged with an `internal_tag` on the prose atom instead.

**list_item** — A numbered or bulleted item in the author's own enumeration, with its inline explanation (e.g., `1. خلوصها من تنافر الحروف`).

### Bonded Cluster Trigger
A structured record required on every bonded_cluster atom, explaining why the sentences were merged. Contains a `trigger_id` (T1–T6) classifying the bond type and a `reason` string citing concrete textual evidence.

| Trigger | Name | Pattern |
|---------|------|---------|
| T1 | failed_independent_predication | One sentence has no independent subject/predicate without the other |
| T2 | unmatched_quotation_brackets | Quote opens in one sentence, closes in the next |
| T3 | colon_definition_leadin | Sentence ends with colon, next completes the definition |
| T4 | short_fragment | Fragment under 15 characters — cannot stand alone |
| T5 | verse_coupling | Two hemistichs of the same bayt |
| T6 | attribution_then_quote | Attribution formula ("قال الشاعر") followed by the quoted content |

### Internal Tag
A marker on a prose atom flagging embedded content or anomalies within its text. Used when Quran, hadith, or verse fragments appear inside a prose sentence (rather than as standalone atoms).

| Tag Type | Meaning |
|----------|---------|
| `quran_embedded` | Quran text embedded within prose (requires `text_fragment`) |
| `hadith_embedded` | Hadith text embedded within prose (requires `text_fragment`) |
| `verse_fragment_embedded` | Poetry fragment within prose (requires `text_fragment`) |
| `source_inconsistency` | Documents an inconsistency in the author's text (requires `note`). The synthesis LLM must be aware of these to avoid propagating errors. |

### Footnote Reference (footnote_ref)
A link from a متن atom to its associated footnote atoms. Carries the original marker text (e.g., `(1)`) which was stripped from the atom text during atomization. Supports `orphan` status for markers that have no corresponding footnote text in the source (printing errors, missing pages).

### Source Anchor (مرساة المصدر)
The character-level position of an atom within its layer's canonical text file. Expressed as `{char_offset_start, char_offset_end}` in Unicode codepoints (Python `len()`, not bytes). The invariant `atom.text == canonical_text[start:end]` is enforced by the validator.

---

## 4. Excerpts

### Excerpt (مقتطف)
The primary output of the pipeline. A selection of atoms from one source layer, assigned to exactly one taxonomy leaf node, representing everything that passage of the book says about that specific topic.

**Canonical vs derived:** the authoritative excerpt representation is the structured JSONL record (atoms + excerpt record + metadata). Any excerpt `.md` file is a deterministic, regeneratable *derived view* for human review; it must never be treated as canonical or hand-edited as the source of truth.

Every excerpt has a unique, immutable **excerpt_id** in the format `{book_id}:exc:{six_digit_sequence}` (e.g., `jawahir:exc:000003`).

From schema v0.3.2+, an excerpt may also carry a human-readable **excerpt_title** plus **excerpt_title_reason**. The title is a stable display label for reviewers and future automation. It must remain unique among siblings under the same taxonomy node by appending a source-anchored disambiguator (page range + layer + core atom span/list).

From schema v0.3.3+, an excerpt may also carry **content_anomalies**: a structured list of source anomalies (e.g., summary mismatch, author inconsistency, typographical corruption) that must be preserved while explicitly warning downstream synthesis. Each anomaly records a `type`, `details`, and `evidence_atom_ids` (and optionally a `synthesis_instruction`). This is distinct from atom-level `internal_tags.source_inconsistency`: excerpt-level anomalies are preferred when the inconsistency affects *topic synthesis*, not just a local atom note.


An excerpt is NOT just "text about topic X." It is a carefully bounded, annotated, traceable scholarly unit with metadata that tells the synthesis LLM exactly what each atom does, where the excerpt sits in the book's structure, and how it relates to other excerpts.

### Source Spans (مدى المصدر)
Multi-span traceability for an excerpt (`source_spans` in the schema). Each span is a contiguous run of atoms in the canonical text, typed as either `core` or `context`. A simple excerpt (all atoms consecutive) has one span. An excerpt with non-contiguous atoms (e.g., an overview condition pulled from earlier in the text as context) has multiple spans. Source spans carry char offsets and atom IDs, enabling any consumer to locate the exact text in the canonical file.

### Split Discussion (مناقشة مجزأة)
When a single topic's discussion is split across non-adjacent locations in the source (e.g., author discusses topic X, digresses for pages, then returns to X), the discussion is represented as multiple excerpts at the same taxonomy leaf.

**Authoritative encoding:** split continuity is stored in the excerpt-level `relations` list using `split_continues_in` / `split_continued_from`.
The `split_discussion` object is allowed only as a redundant mirror for human readability; if present, it MUST match the split relations exactly (same targets, same types).

The synthesis LLM must merge split excerpts at the same node to present a complete treatment.

### Cross-Science Context
`cross_science_context` is an **excerpt-level** label indicating that the excerpt’s teaching about its current node **depends on technical content** from another linguistic science (صرف/نحو/عروض/لغة).

**Threshold:** set `cross_science_context=true` when the excerpt includes an explicit technical claim/rule/analysis from another science that functions as a premise or explanation (e.g., صرف: وزن/صيغة/مادة/اشتقاق; نحو: إعراب/عامل/تقدير). Do **not** set it for mere mentions (e.g., “النحوي” as a title) with no technical content.

**Required companions:**
- When `cross_science_context=true`, `related_science` must be set (sarf/nahw/3arud/lughah/other).
- `rhetorical_treatment_of_cross_science` distinguishes technical prerequisite vs rhetorical illustration, but is meaningful only when `cross_science_context=true`.
- **Training consistency:** when `cross_science_context=true`, the excerpt’s `case_types` must include `D4_cross_science`.

**Relation to context roles:** if the prerequisite other-science material is kept as context atoms, use the context role `cross_science_background` for those atoms — but keep `cross_science_context=true` for the excerpt as a whole.

### Interwoven Content (محتوى متشابك)
 (محتوى متشابك)
When the author discusses multiple taxonomy topics in a way that cannot be separated at atom boundaries, the same **non-heading** atoms may need to appear as **core** in more than one excerpt. In that case, all such excerpts share the same non-null `interwoven_group_id` and must be explicitly linked via `interwoven_sibling` relations.

**Controlled exception:** core atom duplication is forbidden by default. It is permitted only within a single interwoven group (and only when the group is explicitly marked as `B3_interwoven`). The validator enforces: (1) same group_id across all duplicates, (2) connectivity via `interwoven_sibling`, (3) identical core role for any duplicated atom across group members, and (4) no leakage of the duplicated atom_id outside the group.

Downstream synthesis must treat the entire interwoven group as ONE evidence block and must not double-count duplicated text.

### Excerpt Kind

**teaching** — Scholarly content that teaches, defines, explains, or argues about the taxonomy node's topic. This is the main kind. Includes definitions, rules, evidence, commentary, and scholarly disputes.

**exercise** — Practice material for the reader (تمارين / تطبيقات). Has additional structure: exercise_role, tests_nodes, primary_test_node. See *Exercise Structure*.

**apparatus** — Reserved for future use. Editorial or structural content that doesn't fit teaching or exercise.

### Core Atoms vs Context Atoms

This is the most critical distinction in the entire system. Getting it wrong corrupts synthesis.

**Core atoms** (`core_atoms`) are the author's teaching/evidence that belongs to the excerpt's target topic (its `taxonomy_node_id`). This includes the author's own prose AND any evidence the author embeds (cited verses, hadith, quotations). Core atoms are what the synthesis LLM should treat as authoritative content for that node.

**Context atoms** (`context_atoms`) provide framing needed for comprehension without becoming authoritative node-content. They may include: a classification frame from an overview list, a preceding setup sentence, a back-reference, or minimal prerequisite mini-background about another topic (Supportive Dependency). Context atoms do NOT constitute the excerpt's core teaching at the node. The synthesis LLM must treat them as framing.

**The assignment test (synthesis-safe):**
1) If the atom teaches/proves something *about the excerpt's taxonomy node*, it is core.
2) If the atom is present only to make that teaching understandable (setup/frame/prereq about another topic), it is context.

This is stricter than a pure "flow" heuristic: sometimes a prerequisite atom is needed for understanding but should still be context so it is not treated as authoritative content for the node.



**Core atom duplication (policy):** A non-heading atom may be core in at most one excerpt, except for two explicit cases: (1) interwoven groups (`interwoven_group_id` + `B3_interwoven` + `interwoven_sibling`), and (2) shared evidence (`shared_shahid`) for role=`evidence` only. Context atoms can be reused freely.

**The evidence rule:** Verses, hadith, and quotations cited by the author as proof or illustration are ALWAYS core (with `role=evidence`), never context. Evidence is part of the author's discourse flow — the author deliberately placed it there. Context is reserved for genuinely external material: a condition from an overview list, a setup sentence from a prior section, a back-reference.

---

## 5. Roles

Every atom within an excerpt carries a **role** that tells the synthesis LLM what function it serves. Core atoms and context atoms have separate role vocabularies.

### Core Atom Roles

**author_prose** — The author's own teaching text. Definitions, explanations, classifications, transitions, attribution formulas, analytical commentary. These are the author's own words expressing the author's own ideas (or the author's presentation of others' ideas in the author's own language).

**evidence** — Material cited by the author as proof or illustration. Verse شواهد, hadith, prose quotations from other scholars. The key test: are these the current author's own words, or someone else's words that the author is citing? If cited → evidence. The atom_type captures the form (verse_evidence, prose_sentence); the role captures the function. These are orthogonal: a prose_sentence atom can have role=evidence (when it's a quoted passage from another scholar).

**exercise_content** — Material presented as exercise items for the reader to analyze. In exercise excerpts, the verse or passage IS the exercise — it's not evidence supporting a teaching point, it's the thing being analyzed. The same verse appearing in a teaching excerpt would be role=evidence; in an exercise excerpt it's role=exercise_content.

**exercise_answer_content** — Scholarly judgment in a footnote identifying the answer to an exercise item (e.g., identifying which عيب applies to a specific word or passage). These are answer keys, not apparatus.

### Context Atom Roles

**classification_frame** — An item from an overview enumeration that identifies which category this excerpt falls under. Example: an excerpt about غرابة الاستعمال includes, as context, the line "2. خلوصها من الغرابة" from the overview list of conditions for فصاحة المفرد. This frames the excerpt within the larger structure without teaching about غرابة itself.

**preceding_setup** — Earlier prose that establishes the broader topic, needed for the excerpt to be comprehensible. Typically a transitional sentence whose pronoun the first core atom refers back to.

**back_reference** — The author's explicit reference to a prior discussion (e.g., "كما تقدم في باب...").

**cross_science_background** — A prerequisite concept from another science needed to understand this excerpt (e.g., a صرف definition needed to understand a بلاغة rule).

### Heading Path (مسار العناوين)

An ordered list of heading atom IDs that records where in the book an excerpt is located (e.g., `[مقدمة, الفصاحة, فصاحة الكلمة المفردة]`). The heading_path is navigational metadata — it answers "under which section headings does this excerpt appear?" — not teaching content.

**Construction rule:** heading_path contains all heading atoms from the outermost section heading down to the most recent heading atom that precedes the excerpt's first core atom, in reading order. If a new heading at the same or higher level resets the hierarchy, the path resets accordingly.

**Footnote excerpts:** heading_path is always an empty array `[]` for footnote-layer excerpts. Footnotes exist outside the متن heading hierarchy. Do NOT inject متن headings into footnote excerpts — this would violate layer isolation. A footnote excerpt's location is tracked through its `footnote_supports` or `answers_exercise_item` relation back to the relevant متن excerpt.

**Heading atoms referenced in heading_path are also excluded** as `heading_structural`. This dual-state is intentional (see *Heading Dual-State Principle*).

---

## 6. Taxonomy

### Taxonomy Tree (شجرة التصنيف)
A hierarchical structure mapping every topic, subtopic, and sub-subtopic within one science. Each science has its own tree. The tree is stored as a YAML file (e.g., `balagha_v0_2.yaml`).

The tree is maximally granular: every leaf node addresses exactly one atomic topic that cannot be further subdivided. When content reveals that a node can be further subdivided, the tree evolves.

### Taxonomy Node (عقدة)
A single point in the taxonomy tree. Every node has a unique **node_id** (e.g., `3uyub_alfard_tanafur`), a human-readable Arabic **title**, and a flag indicating whether it is a **leaf** (endpoint) or a **branch** (has children).

### Leaf Node (عقدة طرفية)
A node with `leaf: true` — the lowest level of granularity. Excerpts are always assigned to leaf nodes, never to branch nodes. If content addresses a concept at a branch level, either a dedicated overview leaf is created, or the tree is restructured.

### Taxonomy Path (مسار التصنيف)
A human-readable breadcrumb from root to leaf using Arabic titles. Example: `مقدمات > الفصاحة > فصاحة المفرد > عيوب المفرد: التنافر`. Informational only — the authoritative placement is the node_id.

### Taxonomy Version (إصدار التصنيف)
An identifier tracking the tree's evolution: `{science}_v{major}_{minor}` (e.g., `balagha_v0_2`). When the tree changes (node added, split, renamed, moved), the version bumps and a **taxonomy_change record** documents what changed, why, and which excerpt triggered it.

### Content Sovereignty (سيادة المحتوى)
A core project principle: the taxonomy adapts to content, never the reverse. If an excerpt doesn't fit the current tree, the tree changes (via a taxonomy_change record with reasoning). Content is never forced into an ill-fitting node, and nodes are never left empty by design — their existence is justified by content that demanded them.

### Taxonomy Change (تغيير التصنيف)
A record documenting a modification to the taxonomy tree. Every change type has specific semantics:

| Type | Meaning |
|------|---------|
| `node_added` | A new leaf node was created because content demanded a node that didn't exist |
| `leaf_granulated` | An existing leaf was split into multiple child leaves because content revealed sub-topics |
| `node_renamed` | An existing node's title or ID was changed for accuracy |
| `node_moved` | An existing node was relocated to a different parent in the tree |

Each change record includes the taxonomy version before and after, the reasoning, and (when applicable) which excerpt triggered it. The `triggered_by_excerpt_id` field creates a bidirectional link with the excerpt's `taxonomy_change_triggered` field — the validator enforces both sides.

### Taxonomy Node ID Policy
Node IDs follow frozen formation rules to prevent drift across annotators and models. The rules are documented in the taxonomy YAML's `id_policy` header. Key points: lowercase ASCII + digits + underscores only; Franco-Arabic transliteration (ع→3, ة dropped at end, ال→al prefix); IDs are immutable once assigned — renames go through taxonomy_change records.

---

## 7. Relations

### Relation
A typed directional link from one excerpt (the source) to another (the target). Relations express structural, evidential, and content relationships between excerpts. They are intentionally unidirectional — the reverse is always computable at query time.

When the target excerpt does not yet exist (expected in a future passage), `target_excerpt_id` is null and `target_hint` describes where to find it. These are **unresolved relations** that must be resolved in a later processing pass.

**Cross-passage note:** A single-passage package may contain relations whose `target_excerpt_id` points to an excerpt in an earlier passage of the same book (already exists globally, but not present in this package). The validator can treat such targets as acceptable externals when run with `--allow-external-relations` (warning instead of error).

### Relation Types

| Type | Direction | Meaning |
|------|-----------|---------|
| `footnote_supports` | footnote → matn | Footnote provides additional evidence reinforcing the matn excerpt's claim |
| `footnote_explains` | footnote → matn | Footnote clarifies, glosses, or analyzes something in the matn excerpt |
| `footnote_citation_only` | footnote → matn | Footnote provides only a bibliographic reference |
| `footnote_source` | footnote → matn | Footnote identifies the original source of a citation in the matn |
| `has_overview` | detail → overview | This excerpt's topic is covered by a broader overview/enumeration excerpt |
| `shared_shahid` | excerpt → excerpt | Both excerpts use the same verse/hadith as evidence |
| `exercise_tests` | exercise → teaching | This exercise tests comprehension of the target teaching excerpt |
| `belongs_to_exercise_set` | item/answer → set | This exercise item or answer belongs to the target exercise set |
| `answers_exercise_item` | answer → item | This answer provides the scholarly judgment for the target exercise item |
| `split_continues_in` | earlier → later | This excerpt's discussion continues in the target (same topic, separated by intervening content) |
| `split_continued_from` | later → earlier | This excerpt continues a discussion started in the target |
| `interwoven_sibling` | excerpt → excerpt | Both excerpts share inseparable text (same atoms in both, due to interwoven multi-topic content) |
| `cross_layer` | excerpt → excerpt | Generic cross-layer reference when none of the footnote_* types apply |

---

## 8. Exercise Structure

Arabic textbooks often include exercise sections (تمارين / تطبيقات). These have a specific hierarchical structure:

### Exercise Set (exercise_role = "set")
The framing prompt for a group of exercises. Example: "ما الذي أخلّ بفصاحة ما يأتي" (What impairs the فصاحة of the following?). `tests_nodes` is the union of all child items' test nodes. `primary_test_node` is null.

### Exercise Item (exercise_role = "item")
An individual exercise specimen — a word, phrase, verse, or passage the reader must analyze. Core atoms use `role=exercise_content`. `tests_nodes` lists all taxonomy nodes this item tests. `primary_test_node` identifies the single most prominent one. Each item must have exactly one `belongs_to_exercise_set` relation.

### Exercise Answer (exercise_role = "answer")
A footnote-layer excerpt containing the scholarly judgment for an exercise item (the answer key). Core atoms use `role=exercise_answer_content`. Linked to its item via `answers_exercise_item` and to the set via `belongs_to_exercise_set`.

**Distinguishing answers from apparatus:** if the footnote merely glosses a word (e.g., "الاسفنط = الخمر"), it is excluded as `footnote_apparatus`. If it provides a scholarly judgment identifying which عيب applies, it becomes an answer excerpt.

---

## 9. Exclusions

### Exclusion (استبعاد)
An atom explicitly excluded from excerpting. The **coverage invariant** requires that every atom in the dataset must be accounted for: either as a core atom in one (normally) excerpt, as a context atom, as a heading_path reference, or as an exclusion. Core duplication is forbidden by default and allowed only via explicit exceptions (interwoven groups or shared_shahid evidence). Exclusions are not deletions — the atom record still exists, and the exclusion can be reversed if the decision was wrong.

### Exclusion Reasons

| Reason | Meaning |
|--------|---------|
| `heading_structural` | Heading atom — navigational metadata, not teaching content. Referenced in heading_path. |
| `footnote_apparatus` | Word glosses, verse parsing (إعراب), meaning explanations — reading aids with no substantive scholarly content about the science itself |
| `khutba_devotional_apparatus` | Opening prayers, بسملة, حمدلة, devotional formulas |
| `non_scholarly_apparatus` | Any other non-teaching content (transitional formulas, section labels) |
| `page_header_artifact` | Running headers, page numbers, or other artifacts from the print/digital source |
| `decorative_separator` | Ornamental dividers between sections |
| `publishing_metadata` | Publisher information, edition notes, copyright text |
| `duplicate_content` | Exact or near-exact duplicate of another atom (linked via `duplicate_of_atom_id`) |
| `exercise_prompt_only` | Exercise framing text fully handled by the exercise set excerpt |

---

## 10. The Gold Standard Process

### Gold Standard (المعيار الذهبي)
A manually annotated, fully validated decomposition of a passage into atoms, excerpts, and taxonomy placements. Gold standards serve three purposes: (1) they are the training data and specification for the automated extraction app, (2) they are the test suite against which the app's output is compared, and (3) they are the concrete examples that resolve ambiguities in the excerpting rules.

### Gold Standard Package
A zip file containing all data, tools, and documentation for one passage. Includes: atom files (JSONL), excerpt/exclusion file (JSONL), canonical text files, metadata, taxonomy tree (YAML), taxonomy changes (JSONL), validator, report generator, lessons learned, manifest, and README. Every file is checksummed in the manifest.

### Passage Status

**gold** — Manually created and validated. The authoritative version.

**gold_migrated** — Was gold, then automatically migrated due to a taxonomy change (node split/rename). Needs human re-validation.

**superseded** — Replaced by a newer version. The replacement's `supersedes_excerpt_id` points to this one. Retained for audit trail only.

### Lessons Learned
Each gold standard passage produces a lessons_learned file documenting every edge case, design decision, and pattern discovery. These accumulate across passages and eventually feed back into the excerpting rules and extraction protocol. They are a critical part of the specification — not disposable notes.

---

## 11. Key Principles

### Core-Uniqueness Invariant
Each atom may be a core atom in at most one excerpt. This prevents the same content from being counted multiple times during synthesis. An atom CAN appear as context in multiple excerpts (it provides framing in each) and can be referenced in multiple heading_paths, but it is core in exactly one.

### Coverage Invariant
Every atom in the dataset must be accounted for: core in one excerpt, context in one or more excerpts, referenced in heading_path, OR explicitly excluded. No atom may be orphaned. The validator enforces this.

### Comprehensibility Principle
An excerpt must be standalone readable. A reader (or LLM) encountering the excerpt in isolation should be able to understand what it says without needing to read surrounding text. This is why context atoms exist — they provide just enough external framing to make the excerpt comprehensible. But comprehensibility does not mean self-sufficiency: the excerpt doesn't need to teach the entire subject, just present its own content coherently.

### Dependency Test
The test for whether content about topic Y within a discussion of topic X should be in X's excerpt or Y's excerpt: "If I removed the Y-content, would the X-discussion be broken? And could a reader learn anything meaningful about Y from this content alone?" If the Y-content is just an incidental mention, a comparison point, or a brief aside that serves X's argument, it stays in X's excerpt. Only if the content substantively teaches Y does it warrant its own excerpt at Y's node.

**Supportive Dependency (mini-background):** If the X-discussion would become materially unclear without a *brief* reminder/definition about Y, and that Y-content does not stand as meaningful teaching about Y on its own, it may remain inside the X-excerpt — but it must be recorded as **context** (not core) so synthesis treats it as framing.

### Supportive Dependency
Short, subordinate prerequisite content about another topic (Y) that is included inside an excerpt whose node is X **only to make X understandable**.

**Key properties (strict):**
- Subordinate: it serves X; it is not the excerpt's main claim.
- Bounded: it stays small and local.
- Synthesis-safe: it is recorded in `context_atoms` (never as core).
- Not node-justifying: it must not trigger taxonomy changes about Y.

If the Y-content grows into meaningful teaching about Y, it is no longer a supportive dependency; it becomes a separate excerpt at Y (or an interwoven group if inseparable).

**Documentation requirement:** whenever supportive dependency is used, the excerpt MUST include a structured `SUPPORTIVE_DEPENDENCIES:` block inside `boundary_reasoning` (Binding Decisions §8.5).

### Layer Isolation
Each excerpt draws from exactly one source layer. Cross-layer relationships are expressed through typed relations connecting separate excerpts. You never mix متن atoms and footnote atoms in the same excerpt's core or context.

### Heading Dual-State Principle
Heading atoms are simultaneously excluded (as `heading_structural`) AND referenced in `heading_path` on excerpts. This is intentional, not a bug. Headings carry navigational metadata (where in the book?) but not teaching content (what does the author say?). The validator treats heading_path references as structural metadata, not as "usage" for coverage purposes.

### Self-Containment
Every excerpt must be independently understandable. When the synthesis LLM receives an excerpt, it must be able to extract everything it needs from that single file — the Arabic text, author identity, scholarly tradition, topic context — without requesting additional files or cross-referencing. This is why context atoms exist and why metadata fields are rich. Self-containment is non-negotiable.

### Content-Driven Excerpting
Excerpt boundaries come from the text — what atoms naturally form a self-contained teaching unit. The taxonomy tree has **zero influence** on how excerpting happens. You excerpt first (what is a coherent teaching unit?), place second (where does this belong?), evolve third (is the tree granular enough?). These are three distinct operations that must never be conflated.

### Living Taxonomy
Taxonomy trees are not fixed containers — they evolve as new books reveal finer topic distinctions. A tree grows across books (Book A may add 5 leaves, Book B may add 3 more) and is never pruned automatically. Evolution is LLM-driven with human approval. Full version history is maintained for rollback capability. See also Content Sovereignty (§6).

### One Excerpt Per Book Per Node (Quality Preference)
If extraction produces two excerpts from the same book at the same taxonomy node, that's a signal: either merge them (they're about the same thing) or evolve the node (they cover different sub-aspects). This is a quality preference that drives proper granularity, **not** a hard constraint on excerpting itself.

### Versioned Vocabularies
All enumerations (atom types, roles, relation types, exclusion reasons, case_types) are closed within a schema version. New values require a schema version bump with documented justification. This gives strict correctness checking within a version and controlled evolution across versions.

---

## 12. File and ID Conventions

### ID Formats

| Entity | Format | Example |
|--------|--------|---------|
| Atom | `{book_id}:{layer}:{6-digit seq}` | `jawahir:matn:000004` |
| Excerpt | `{book_id}:exc:{6-digit seq}` | `jawahir:exc:000003` |
| Taxonomy Change | `TC-{3-digit seq}` | `TC-002` |
| Taxonomy Version | `{science}_v{major}_{minor}` | `balagha_v0_2` |

All sequence numbers are globally sequential within their scope (book for atoms/excerpts, project for taxonomy changes). They never reset between passages.

### Filename Convention
Data files use the pattern `{passage_id}_{layer}_{content}_v{record_format}.{ext}`. The `_v02` suffix refers to the data record format version (the internal structure of JSONL records). The schema version (e.g., `v0.3.1`) is a separate axis tracking validation rules and documentation. They version different things.

### Schema Version
The JSON Schema file (`gold_standard_schema_v{version}.json`) is the authoritative data contract. It defines every record type, every field, every enum value, and — as of v0.3.1 — comprehensive descriptions for all of them. The schema is self-documenting: an AI builder can read the schema alone and understand the purpose and semantics of every field.

---

## 13. Data File Format

### JSONL (JSON Lines)
All data files use JSONL format: one JSON object per line, each line is a complete, self-contained record. There is no wrapping array — each line can be parsed independently.

### Record Type Discriminator
Every record has a `record_type` field that identifies what kind of record it is. This is the primary dispatch mechanism for parsing mixed JSONL files:

| `record_type` | Found in | Purpose |
|----------------|----------|---------|
| `"atom"` | `{passage}_matn_atoms_v02.jsonl`, `{passage}_fn_atoms_v02.jsonl` | One record per atom |
| `"excerpt"` | `{passage}_excerpts_v02.jsonl` | Excerpt records |
| `"exclusion"` | `{passage}_excerpts_v02.jsonl` | Exclusion records |
| `"taxonomy_change"` | `taxonomy_changes.jsonl` | Taxonomy change records |

**Critical:** Excerpts and exclusions share the same file. When reading `{passage}_excerpts_v02.jsonl`, filter on `record_type` to separate them. Atom files contain only atoms (one file per source layer).

### Schema Dispatch
The JSON Schema uses a `oneOf` mechanism at root level, with each definition constrained by a `record_type` const value. A validator reads `record_type` first, then applies the matching definition. The schema is the authoritative source for which fields are required, optional, and what values they accept.

---

## 14. Multi-Passage Composition

### How Passages Relate
A book is processed passage by passage. Each passage produces its own set of data files (atoms, excerpts, canonical texts, metadata). Passages within the same book share:

- **Book ID** — all atoms/excerpts use the same `book_id`
- **Atom/excerpt sequence numbering** — globally sequential within a book, never reset between passages
- **Taxonomy tree** — the current version at the end of one passage is the starting version for the next
- **Taxonomy changes file** — append-only across passages within a project; new changes are appended, never overwriting earlier entries
- **Schema and glossary** — shared across all passages and all books

### Continuation State
Each passage's `metadata.json` includes a `continuation` block with machine-readable starting values for the next passage:

```
continuation.next_matn_atom_seq      → first matn atom ID for next passage
continuation.next_fn_atom_seq        → first footnote atom ID for next passage
continuation.next_excerpt_seq        → first excerpt ID for next passage
continuation.next_taxonomy_change_seq → first TC- ID for next passage
continuation.current_taxonomy_version → taxonomy tree version to start from
```

The AI builder processing passage N reads passage (N-1)'s metadata to get these values. For the first passage of a new book, all sequences start at 1.

### Passage Packaging
Each passage is a self-contained zip file. It includes a copy of the current taxonomy tree and schema at the time of packaging, plus the project glossary. The passage zip is the unit of delivery — an AI builder can validate a single passage without needing other passages' data.

### Cross-Passage References
Relations with `target_excerpt_id = null` and a `target_hint` are **unresolved cross-passage references** — they point to excerpts expected in a future (or previous) passage. These must be resolved in a post-processing pass after all passages of a book are complete.

---

## 15. Terminology Cross-Reference

Some terms appear under multiple names in earlier documents or in Arabic scholarly tradition. This table maps variants to the canonical project term:

| You might see | Canonical term | Notes |
|---------------|---------------|-------|
| fragment, مقطع نصي | excerpt | "Fragment" was used in early project docs |
| node, leaf node, endpoint, عقدة | taxonomy node / leaf node | "Leaf node" specifically means leaf=true |
| topic tree, science tree | taxonomy tree | |
| sentence atom | prose_sentence | The atom_type value |
| verse atom, poetry atom, بيت | verse_evidence | Covers bayt, hemistich, and verse fragment |
| bonded pair, merged sentences | bonded_cluster | |
| footnote layer | source_layer=footnote | Not to be confused with footnote_apparatus (an exclusion reason) |
| حاشية (as source layer) | hashiya | Classical super-commentary. Distinct from حاشية المحقق = footnote |
| gold passage, baseline | gold standard passage | |
| tag, marker | internal_tag | Tags on atoms for embedded content |
| role | core atom role or context atom role | Two separate vocabularies |

---

*Version: 1.2.0 — See version history at end of file.*


---

*Glossary version: 1.2.0 — Pipeline Stages rewritten to match implemented 7-stage pipeline. Added Key Principles: Self-Containment, Content-Driven Excerpting, Living Taxonomy, One Excerpt Per Book Per Node. Science ID `imla` corrected to `imlaa`. Previous: 1.1.1 (interwoven core-duplication, split-discussion, relation target integrity).*
