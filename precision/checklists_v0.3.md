# Gold Standard Checklists v0.3

> **DEPRECATED:** Use `checklists_v0.4.md` as the canonical checklist. This v0.3 file remains for historical baseline reproducibility only.



**Canonical location:** `ABD/2_atoms_and_excerpts/checklists_v0.3.md`.
Baseline packages may include snapshot copies for reproducibility; the canonical checklist is the reference for interpreting checklist IDs.
**Purpose:** Stable, referenceable rule items for decision traceability. Every atomization, excerpting, and placement decision must cite the checklist items it satisfies.

**Who uses this:** The human annotator (now) and the future AI extraction app (later). Every decision record in `passage*_decisions.jsonl` references checklist IDs from this file.

**Versioning:** Checklist IDs are immutable once assigned. New rules get new IDs (never reuse). If a rule is deprecated, mark it `[DEPRECATED vX.Y]` but keep the ID.

**Source authority:** Rules here are derived from `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.10.md`, `project_glossary.md`, `2_atoms_and_excerpts/extraction_protocol_v2.md`, and `schemas/gold_standard_schema_v0.3.1.json`. When documents disagree, follow the precedence order in Binding Decisions §1.

---

## 1. Atomization Checklists

### ATOM.A — Atom Boundary Rules

| ID | Rule | Pass condition | Source |
|----|------|----------------|--------|
| ATOM.A1 | **Terminal punctuation ends atoms.** `.` `؟` `?` `!` and paragraph breaks are atom boundaries. | Atom ends at one of these, or at a paragraph break. | Glossary §3 "prose_sentence" |
| ATOM.A2 | **Non-terminal punctuation does NOT end atoms.** `،` `,` `؛` `;` `:` and em-dashes are never atom boundaries on their own. | No atom boundary was placed at one of these marks alone. | Glossary §3 "prose_sentence" |
| ATOM.A3 | **Text is verbatim.** Atom text is copied character-for-character from the canonical parsed source. No spelling corrections, diacritic changes, editorial insertions, or reordering. | `atom.text == canonical_text[start:end]` (validator-enforced). | Glossary §3 "Source Anchor", Protocol §1 |
| ATOM.A4 | **Every atom has exactly one type.** One of: `prose_sentence`, `bonded_cluster`, `heading`, `verse_evidence`, `quran_quote_standalone`, `list_item`. | `atom_type` is set and matches the atom's structural form. | Schema atom_record.atom_type enum |
| ATOM.A5 | **Sequence is reading order.** Atoms within a layer are numbered in the order they appear in the source, globally sequential within the book (never reset between passages). | Sequence numbers continue from previous passage's `continuation` block. | Glossary §14 "Multi-Passage Composition" |
| ATOM.A6 | **One atom per layer boundary.** A single atom never spans two source layers (matn + footnote). | All text in the atom belongs to a single source_layer. | Glossary §3 "Source Layer" |
| ATOM.A7 | **Footnote markers stripped, recorded.** Footnote reference markers (e.g., "(1)") are stripped from atom text and recorded in `footnote_refs` with marker_text and linked footnote_atom_ids or orphan status. | If source text had a footnote marker, the atom has a corresponding footnote_ref entry. | Glossary §3 "Footnote Reference" |
| ATOM.A8 | **No empty atoms.** Every atom has non-empty text. | `len(atom.text) > 0` | Validator check |
| ATOM.A9 | **Conservative merge principle.** When unsure whether to merge consecutive sentences into a bonded_cluster or keep them as separate prose_sentence atoms: prefer merging. A wrongly-split atom is worse than a slightly large one. | If doubt existed, the merge direction was chosen and documented. | Glossary §3 "bonded_cluster", Lesson 12 |

### ATOM.B — Bonded Cluster Triggers

Every `bonded_cluster` atom must have a non-null `bonded_cluster_trigger` with one of these trigger_ids plus a `reason` citing concrete textual evidence. Non-bonded atoms must have null trigger.

| ID | Trigger | Pattern | Pass condition |
|----|---------|---------|----------------|
| ATOM.B1 | **T1: failed_independent_predication** | One sentence has no independent subject/predicate without the other. | The reason cites which sentence lacks independent predication and why. |
| ATOM.B2 | **T2: unmatched_quotation_brackets** | Quote opens in one sentence, closes in the next. | The reason identifies the quotation marks/brackets and their positions. |
| ATOM.B3 | **T3: colon_definition_leadin** | Sentence ends with colon, next completes the definition. | The reason identifies the colon and the definition that follows. |
| ATOM.B4 | **T4: short_fragment** | Fragment under 15 characters — cannot stand alone. | The reason states the character count and why the fragment is not self-standing. |
| ATOM.B5 | **T5: verse_coupling** | Two hemistichs of the same bayt. | The reason identifies the verse and confirms both hemistichs belong to one bayt. |
| ATOM.B6 | **T6: attribution_then_quote** | Attribution formula ("قال الشاعر") followed by the quoted content. | The reason identifies the attribution formula and what it introduces. |

### ATOM.H — Heading Recognition Rules

| ID | Rule | Pass condition | Source |
|----|------|----------------|--------|
| ATOM.H1 | **Short text, no verb, no predication.** Headings are structural markers, not prose. They are typically under ~50 characters, lack a main verb, and make no complete predication. | The text is short, has no main verb, and does not form a complete sentence. | Glossary §3 "heading" |
| ATOM.H2 | **Section keyword context.** Text contains or implies a section marker: باب، فصل، مسألة، تنبيه، فائدة, chapter/section titles, topic labels, numbered section headers. | At least one of: explicit keyword, numbering pattern, or structural position confirms heading status. | Glossary §3 "heading" |
| ATOM.H3 | **Dual-state is mandatory.** Heading atoms are always excluded as `heading_structural` AND referenced in `heading_path` of relevant excerpts. This is intentional. | Both the exclusion record and at least one heading_path reference exist (unless the heading precedes no excerpts in this passage). | Glossary §11 "Heading Dual-State", Lesson 15 |
| ATOM.H4 | **Headings are never core or context.** A heading atom must never appear in any excerpt's core_atoms or context_atoms arrays. | Validator enforces: no heading atom_id in core or context. | Lesson 8, Validator check |

### ATOM.V — Verse and Quotation Rules

| ID | Rule | Pass condition | Source |
|----|------|----------------|--------|
| ATOM.V1 | **Standalone verse gets atom_type=verse_evidence.** Poetry cited by the author as evidence/illustration, appearing as its own textual unit (not embedded in prose), gets this type. | The atom contains verse text standing alone (not within a prose sentence). | Glossary §3 "verse_evidence" |
| ATOM.V2 | **Embedded verse/Quran/hadith gets internal_tag.** When Quran, hadith, or verse fragments are woven into prose, the prose atom gets an internal_tag (quran_embedded, hadith_embedded, verse_fragment_embedded) with text_fragment identifying the embedded portion. | Every recognizable embedded citation has a corresponding internal_tag. | Glossary §3 "Internal Tag" |
| ATOM.V3 | **Standalone Quran quote gets atom_type=quran_quote_standalone.** Quranic text appearing as its own atom (not embedded in prose). | Used only when Quranic text is a standalone quotation block, not woven into prose. | Glossary §3 "quran_quote_standalone" |
| ATOM.V4 | **Atom type captures form; role captures function.** atom_type (verse_evidence, prose_sentence) and role (evidence, author_prose, exercise_content) are orthogonal. A prose_sentence can have role=evidence; a verse_evidence can have role=exercise_content. | Type and role are assigned independently based on form and function respectively. | Lesson 20, Lesson 6 |

### ATOM.L — List Item Rules

| ID | Rule | Pass condition | Source |
|----|------|----------------|--------|
| ATOM.L1 | **Numbered/bulleted items are list_item.** When the author presents a numbered or bulleted enumeration, each item (with its inline explanation) is a single list_item atom. | The atom contains a numbered/labeled item with its inline content. | Glossary §3 "list_item" |

### ATOM.E — Exclusion Rules

| ID | Rule | Pass condition | Source |
|----|------|----------------|--------|
| ATOM.E1 | **Coverage invariant.** Every atom is accounted for: core in one excerpt (normally), context in one or more, heading_path reference, or explicitly excluded. No orphans. Core-duplication is forbidden by default and must satisfy the binding exceptions when it occurs. | Validator-enforced: zero coverage gaps. | Glossary §11 "Coverage Invariant" |
| ATOM.E2 | **Exclusion reason must be valid.** The exclusion_reason is from the closed enum in the schema. | Validator-enforced against schema enum. | Schema exclusion_record |
| ATOM.E3 | **Footnote apparatus vs scholarly content.** A footnote is excluded as `footnote_apparatus` only if it merely glosses words, parses إعراب, or explains meanings without substantive scholarly analysis. If it provides scholarly judgment, it becomes a teaching or answer excerpt. | The dependency test was applied: does the footnote teach something about the science, or merely aid reading? | Lesson 9, Lesson 22 |
| ATOM.E4 | **No teaching content excluded.** If an atom contains substantive scholarly content about a taxonomy topic, it must not be excluded. Exclusion is for structural, devotional, and apparatus content only. | Review confirms the excluded atom has no teaching value. | Protocol §5 Checkpoint 4 |

---

## 2. Excerpting Checklists

### EXC.C — Core vs Context Assignment

| ID | Rule | Pass condition | Source |
|----|------|----------------|--------|
| EXC.C1 | **Node-teaching vs framing test (dependency-aware).** If an atom is part of the author's teaching/evidence **about the excerpt's taxonomy_node_id**, it is core. If it exists only to make that teaching understandable (setup, classification frame, back-reference, prerequisite mini-background about another topic), it is context. Evidence is always core. | Each atom assignment was justified in boundary_reasoning as either node-teaching (core) or framing/prereq (context). | Binding Decisions §8, Glossary §4 |
| EXC.C2 | **Evidence is ALWAYS core.** Verses, hadith, and quotations cited as proof/illustration are core with role=evidence, never context. | No evidence atom appears in context_atoms. | Glossary §4 "The evidence rule", Lesson 1 |
| EXC.C3 | **Context is synthesis-safe framing.** Context atoms may include minimal prerequisite/background about another topic when needed (Supportive Dependency). Context atoms must not be the primary vehicle for teaching the excerpt's target node. | Any supportive dependency background is in context (not core) and is explicitly acknowledged in boundary_reasoning. | Binding Decisions §8.1(B) |
| EXC.C4 | **Wrong context is worse than missing context.** If unsure whether an atom should be context, leave it out. A missing context atom is recoverable; a wrong one creates false mental models. | Doubt cases are omitted from context (documented in boundary_reasoning). | Lesson 13 |
| EXC.C5 | **Core-uniqueness invariant.** Each atom is core in at most ONE excerpt, except for explicit duplication cases (interwoven_group_id groups or shared_shahid evidence). | Validator-enforced. | Glossary §11 "Core-Uniqueness" |

### EXC.B — Excerpt Boundary Rules

| ID | Rule | Pass condition | Source |
|----|------|----------------|--------|
| EXC.B1 | **One excerpt = one topic leaf.** An excerpt teaches exactly one granulated subtopic and maps to exactly one taxonomy leaf node. | taxonomy_node_id is one leaf; boundary_reasoning explains the single-topic scope. | Binding Decisions §7, §8 |
| EXC.B2 | **No heading atoms in excerpts.** Heading atoms must never appear as core or context; they are metadata-only via heading_path. | Validator-enforced: no heading atom_id in core/context. | Binding Decisions §5 |
| EXC.B3 | **Start at the first teaching atom for the topic.** Do not include earlier unrelated prose as core. Use context_atoms only if needed for comprehensibility. | The first core atom is the first meaningful teaching/evidence atom for the node. | Protocol §4 |
| EXC.B4 | **End before the next topic begins.** When a new topic begins (or the author changes aim), close the excerpt. | Boundary_reasoning cites the exact transition. | Protocol §4 |
| EXC.B5 | **Comprehensibility: standalone readable.** An excerpt must be understandable in isolation. Use context atoms (setup / frames / supportive dependency background) only when needed. | A reader/LLM can grasp the excerpt without reading surrounding text. | Glossary §11 "Comprehensibility Principle" |
| EXC.B6 | **No artificial merges.** Do not merge two independent discussions into one excerpt just because they are adjacent. | Adjacent but distinct topics are separated. | Lesson 10 |
| EXC.B7 | **Topic scope guard (dependency-aware).** When an excerpt at node X contains material about topic Y: incidental mention/bridge is allowed; supportive dependency mini-background is allowed only as context; sovereign teaching of Y requires a split (or interwoven handling). | All other-topic material is classified as (A)/(B)/(C) and handled accordingly; boundary_reasoning makes the classification explicit. | Binding Decisions §8 |
| EXC.B8 | **Split discussions: multiple excerpts, not merged spans.** When the same topic resumes later in the book (separated by intervening content), create multiple excerpts at the same leaf node connected via `split_continues_in` / `split_continued_from` relations. Do NOT merge distant spans into one excerpt. | Separated discussions of the same topic are in distinct excerpts with split relations. | Binding Decisions §9, Glossary: "Split Discussion" |
| EXC.B9 | **Semantic granularity over author packaging.** Excerpt boundaries follow semantic granularity, not the author's surface packaging. If the author treats two distinct subtopics in one paragraph (e.g., تعريف لغة and تعريف اصطلاحا), they become two excerpts at two leaves — unless the text is truly inseparable at atom boundaries (rare). | Distinct subtopics are in distinct excerpts even if the author presents them together. | Binding Decisions §7 |
| EXC.B10 | **Supportive dependency boundedness and explicit note.** If category (B) supportive dependency background exceeds the default boundedness (more than 2 prose atoms or 1 bonded_cluster), it must include `SUPPORTIVE_DEPENDENCY_EXCEPTION:` in boundary_reasoning explaining why it is still subordinate and necessary. | Any oversize supportive dependency includes the exception line and justification. | Binding Decisions §8.3 |

### EXC.L — Layer Isolation

| ID | Rule | Pass condition | Source |
|----|------|----------------|--------|
| EXC.L1 | **Single layer per excerpt.** All core and context atoms share the excerpt's source_layer. | No cross-layer atoms in core or context. | Glossary §4 "Layer Isolation", Lesson 16 |
| EXC.L2 | **Cross-layer relationships use relations.** Footnote→matn connections use footnote_supports, footnote_explains, etc. Never mix layers within one excerpt. | Any cross-layer dependency is expressed as a relation, not a context atom. | Lesson 16 |
| EXC.L3 | **Footnote heading_path is empty.** Footnote-layer excerpts have heading_path=[] since footnotes exist outside the متن hierarchy. | Validator-enforced for footnote-layer excerpts. | Glossary §5 "Heading Path" |

### EXC.X — Exercise Structure

| ID | Rule | Pass condition | Source |
|----|------|----------------|--------|
| EXC.X1 | **Exercise set→item→answer hierarchy.** Set = framing prompt, items = individual specimens, answers = scholarly judgments. | Structure follows the three-level hierarchy. | Glossary §8 |
| EXC.X2 | **Every item/answer has belongs_to_exercise_set.** Exactly one such relation per item or answer. | Validator-enforced. | Lesson 21 |
| EXC.X3 | **tests_nodes on items.** Each exercise item lists all taxonomy nodes it tests. primary_test_node identifies the most prominent one. | tests_nodes is non-empty; primary_test_node is in tests_nodes. | Glossary §8, Lesson 11 |
| EXC.X4 | **Answer distinguishes from apparatus.** If footnote provides scholarly judgment → answer excerpt. If footnote merely glosses a word → excluded as footnote_apparatus. | The dependency test was applied. | Lesson 22 |

---

## 3. Taxonomy Placement Checklists

### PLACE.P — Non-Negotiable Placement Rules (ALL must pass)

| ID | Rule | Pass condition | Source |
|----|------|----------------|--------|
| PLACE.P1 | **Subject alignment.** The excerpt's teaching content addresses the same topic as the target node's title/scope. The match is semantic (an LLM-level judgment), not string matching — titles may use different wording for the same concept. | The excerpt teaches about the node's topic, and a reasonable reader would agree. | Glossary §6 "Taxonomy Node" |
| PLACE.P2 | **Leaf enforcement.** The target node has `leaf: true`. Excerpts are never placed at branch nodes. | The node is confirmed leaf in the current taxonomy YAML. | Glossary §6 "Leaf Node" |
| PLACE.P3 | **Granularity match.** The excerpt addresses this specific subtopic, not a parent-level overview. If the content is general/introductory to a branch, it belongs at the branch's `__overview` leaf, not at a child detail leaf. | The specificity level of the excerpt matches the node's position in the tree. | Glossary: "Taxonomy Node" / "Leaf Node", EXC.B5, Binding Decisions §6 |
| PLACE.P4 | **No better fit.** No other existing leaf in the current taxonomy more precisely captures the excerpt's subject. | Alternatives were considered and documented as rejected (with reasons) in boundary_reasoning ALTS block. | Content Sovereignty principle |
| PLACE.P5 | **Tree evolution if needed.** If no existing leaf fits, a taxonomy_change record is created (node_added, leaf_granulated, etc.) rather than forcing the excerpt into an ill-fitting node. | Either a fitting leaf exists, or a TC record was created. | Glossary §6 "Content Sovereignty" |
| PLACE.P6 | **Single node per excerpt.** Each excerpt has exactly one taxonomy_node_id. | Exactly one leaf assigned. | Schema excerpt_record.taxonomy_node_id |
| PLACE.P7 | **Dependency test for new nodes.** A taxonomy node is justified ONLY when an excerpt substantively addresses that topic. Nodes are not created for topics merely mentioned in passing. | If a TC was triggered, the excerpt genuinely teaches the new node's topic. | Binding Decisions §8.4, Glossary §11 "Dependency Test" |
| PLACE.P8 | **Human approval gate for taxonomy evolution.** Any taxonomy_change (node_added, leaf_granulated, node_renamed, node_moved) must be produced as a proposal and human-approved before being applied to the taxonomy tree. During gold standard work, this means flagging each TC for reviewer sign-off. | The TC record exists as a proposal; the taxonomy YAML is only updated after approval. | Binding Decisions §11 |

### PLACE.S — Solidifying Indicators (nice-to-have, strengthen confidence)

| ID | Indicator | When applicable | Source |
|----|-----------|-----------------|--------|
| PLACE.S1 | **Author's heading matches node.** The book's own section heading corresponds to or closely parallels the taxonomy node title. | When the excerpt falls under a clear heading in the source. | Heading_path alignment |
| PLACE.S2 | **Sibling clustering.** Other excerpts from the same author's section cluster at this node's siblings, confirming the correct branch of the tree. | When multiple excerpts from adjacent text map to sibling nodes. | Structural consistency |
| PLACE.S3 | **Canonical evidence.** The excerpt's شواهد are well-known examples for this topic in the scholarly tradition. | When the evidence is recognizable as standard for the topic. | Domain knowledge |
| PLACE.S4 | **Cross-layer alignment.** Footnote/exercise excerpts linked to this excerpt via relations also align with this node's scope. | When related excerpts exist. | Relation consistency |
| PLACE.S5 | **Cross-book convergence.** Excerpts from other books at this same node discuss the same concept. | Only applicable when multiple books have been processed. | Future use |

### PLACE.X — Cross-Science and Special Cases

| ID | Rule | Pass condition | Source |
|----|------|----------------|--------|
| PLACE.X1 | **Cross-science content stays in primary science.** If a بلاغة excerpt uses صرف concepts, the excerpt stays in the بلاغة tree with cross_science_context=true and related_science set. It does NOT get placed in the صرف tree. | The excerpt is in the correct science's tree; cross-science flag is set if needed. | Glossary §4 "Cross-Science Context" |
| PLACE.X2 | **Incidental mentions stay in current excerpt.** The dependency test: if content about topic Y is just an aside within topic X's discussion, it stays in X's excerpt. Only if Y-content substantively teaches Y does it warrant its own excerpt. | The dependency test was applied for any multi-topic atoms. | Binding Decisions §8, Glossary §11 "Dependency Test" |
| PLACE.X3 | **Exercise excerpts at tatbiq_ nodes.** Exercise items/sets/answers are placed at the appropriate tatbiq_ leaf, not at the concept leaf they test. The `exercise_tests` relation links to the concept. | Exercise excerpts are at tatbiq_ nodes; relations link to concept excerpts. | Passage 1 pattern, Lesson 22 |
| PLACE.X4 | **Author inconsistencies preserved.** If the author contradicts themselves, both versions are preserved (source_inconsistency internal_tag). Do NOT create taxonomy nodes from terms that appear only in drive-by mentions without substantive treatment. | Inconsistencies are documented, not silently corrected. No nodes from summary-only mentions. | Lesson 23 |

---

## 4. Relation Checklists

### REL.R — Relation Assignment

| ID | Rule | Pass condition | Source |
|----|------|----------------|--------|
| REL.R1 | **Relations are unidirectional.** Store one direction; reverse is computable at query time. No redundant back-links. | Each relation is stored once in the source excerpt. | Lesson 24, Glossary §7 |
| REL.R2 | **Relation type matches semantics.** footnote_supports (adds evidence), footnote_explains (clarifies), footnote_source (identifies origin), footnote_citation_only (bibliographic ref). | The type accurately describes the relationship function. | Glossary §7 "Relation Types" |
| REL.R3 | **Cross-passage references use IDs when available.** If the target excerpt exists (e.g., from Passage 1), reference its ID directly. If not yet passaged, use target_hint with null target_excerpt_id. | Existing excerpts are referenced by ID; future ones by hint. | Glossary §7, §14 "Cross-Passage References" |
| REL.R4 | **Taxonomy change bidirectionality.** excerpt.taxonomy_change_triggered ↔ change.triggered_by_excerpt_id must both be set. | Validator-enforced. | Glossary §6 "Taxonomy Change" |

---

*Checklist version: 0.3 — Introduces a dependency-aware topic scope guard and makes supportive dependency mini-background explicitly synthesis-safe by requiring it to be context (not core). IDs are stable; new rule IDs were appended (EXC.B10).*
