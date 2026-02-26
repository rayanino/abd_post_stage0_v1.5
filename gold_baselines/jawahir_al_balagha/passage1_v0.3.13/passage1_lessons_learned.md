# Lessons from Passage 1 Gold Standard
# For incorporation into excerpt_definition_draft.md revision

## Lesson 1: Core vs Context — discourse flow vs external orientation

Core atoms form the excerpt's discourse flow — the continuous stream of text
the author presented as a unit. This includes the author's own analytical
prose AND any material he embedded in that flow (cited verses, hadith, prose
quotations). Each core atom carries a **role** that tells the synthesis LLM
what function it serves:

- **author_prose**: The author's own words — definitions, explanations,
  classifications, transitions, attribution formulas.
- **evidence**: Material cited by the author as proof or illustration — verse,
  hadith, prose from other sources. This is part of the discourse flow (the
  author deliberately placed it there), but it is not the author's own words.
- **exercise_content**: Material presented as exercise items for the reader.

Context atoms provide **external orientation** — text imported from elsewhere
in the book (or from cross-science sources) that helps the reader understand
WHERE the excerpt sits within the broader structure. Examples:

- **classification_frame**: A condition from an overview list that frames
  the current detailed discussion.
- **preceding_setup**: Earlier text establishing the broader topic.

The test: "if you removed this atom, would the excerpt's discourse flow
be broken?" If yes → core (with appropriate role). If no → context.

Why this matters: during synthesis, the LLM needs to distinguish between
"الهاشمي defines تنافر as..." (author_prose), "...citing the verse ترعى
الهمخع" (evidence), and "this discussion falls under condition 2: خلوصها من
التنافر" (classification_frame). All three are important, but they serve
fundamentally different functions. The role system captures this.

## Lesson 2: Exercise items use role=exercise_content, not evidence

In an exercise excerpt, the verse/quote IS the exercise content itself. It's
not evidence supporting a teaching point — it IS the thing being analyzed.
Rule: verse atoms in exercise excerpts get role=exercise_content (they are the
material the reader must work on), while the same verse in a teaching excerpt
would get role=evidence (the author cites it as proof of a principle).

## Lesson 3: Overview excerpts must exist independently

When an author presents a numbered list of conditions (شروط), the list itself
is a teaching unit that belongs at a dedicated overview node, NOT duplicated
as context in every child node. Individual child excerpts can reference the
overview via `has_overview` relation and optionally include a single relevant
condition line as `context_atoms` with `role=classification_frame`.

## Lesson 4: Prefer contiguous core atoms — split non-contiguous spans into linked excerpts

When the same topic appears in separated locations (e.g., an enumeration
followed later by a recap), prefer splitting into multiple excerpts at the
same taxonomy leaf and connecting them via `split_discussion` relations.
This avoids "stitching" distant spans into artificial excerpts, which is
high-risk for automation. Canonical example: atoms 012-015 (initial
enumeration of شروط فصاحة الكلمة) and atoms 051-052 (the ملخص القول recap)
were split into `exc:000003` and `exc:000021`, both placed at the
`shuroot_fasahat_alfard__overview` leaf and linked via
`split_continues_in` / `split_continued_from`.

## Lesson 5: Source traceability is required

Every excerpt must carry `source_spans` — a multi-span traceability structure
containing `canonical_text_file`, `canonical_text_sha256`, and an array of
`spans`, each with `span_type` (core/context), `char_start`, `char_end`, and
`atom_ids`. Character offsets are Python string indices (unicode codepoints,
NOT byte offsets). Split excerpts at the same leaf produce one span each.

Structured decision traceability (labeled `boundary_reasoning` blocks,
structured `atomization_notes`, and decision log JSONL) is required for the
**active gold** set. Passage 1 was upgraded in package v0.3.3 and no longer
uses `--skip-traceability` in active-gold validation.

## Lesson 6: verse_evidence vs verse_bayt semantics

The type name `verse_evidence` was chosen because what matters is the author's
intent (citing a verse as evidence), not the prosodic completeness (full bayt
vs hemistich). A hemistich quoted as evidence serves the same function as a
full bayt. The atom type captures the role, not the meter.

## Lesson 7: Taxonomy sovereignty is real and needs records

Passage 1 triggered 3 taxonomy changes in a 7-page span. This will scale:
expect ~1 change per 10-20 pages as books present different organizational
choices. Every change needs a taxonomy_change record for replayability.

## Lesson 8: Headings are structural metadata, never core

Heading atoms (chapter titles, section markers) are always excluded as
`heading_structural` but USED in `heading_path` arrays. They provide
navigational context for the LLM ("this excerpt comes from: مقدمة > الفصاحة >
فصاحة الكلمة") without being part of the teaching content.

## Lesson 9: Footnote excerpting decision follows dependency test

Not all footnotes become excerpts. The decision:
- Substantive scholarly content → teaching excerpt at appropriate node
- Word glosses / verse parsing → excluded as `footnote_apparatus`
- Mixed → scholarly portion excerpted, apparatus excluded

In Passage 1: 12 of 36 fn atoms became teaching excerpts (5 excerpts);
24 fn atoms excluded as apparatus.

## Lesson 10: Report display must never truncate atom text

Truncating atom text in reports creates false appearance of data corruption.
Always display full text in human-readable reports, using word wrapping.

## Lesson 11: Multi-node exercise items need primary_test_node

When an exercise tests multiple taxonomy nodes simultaneously (e.g., a passage
containing both تنافر and غرابة words), `tests_nodes` captures all relevant
nodes but `primary_test_node` identifies the single most prominent one. This
prevents ambiguity during automated exercise routing.

## Lesson 12: The system must be intelligent, not algorithmic

Classical Arabic texts often lack explicit topic markers. The author may begin
discussing a new concept without announcing it (no section header, no "أما...").
The excerpting system must understand what the author means from contextual
clues, scholarly conventions, and the flow of argumentation — not from
surface-level pattern matching. This is fundamental to the design philosophy.

## Lesson 13: Wrong context is more dangerous than missing context

Context atoms are powerful — they orient the reader and create mental links
between topics. But a WRONG context atom is worse than no context at all. If
an excerpt about تنافر الحروف accidentally carries a context atom from the
غرابة classification, the reader (or synthesis LLM) will form an incorrect
mental model of how the topics relate. Context must be verified with the same
rigor as core content. During automated excerpting, context assignment should
be a separate validation step with conservative defaults (omit rather than
guess).

## Lesson 14: Canonical text must be built FROM atoms, not independently

If the canonical text file is produced separately from atomization (e.g., from
a different normalization pass), the char offsets will inevitably drift. The
only way to guarantee `atom.text == canonical[start:end]` is to construct the
canonical file by concatenating atom texts with separators. The atoms are the
ground truth; the canonical file is a derived artifact for offset verification.

## Lesson 15: Heading atoms have a deliberate dual state — and it must be explicit

Heading atoms are EXCLUDED (as `heading_structural`) AND REFERENCED in
`heading_path` arrays. This is intentional: headings carry no teaching content
(so they don't become core/context), but they provide navigational structure
(so excerpts need to record their position in the book's hierarchy).

The validator must allow this combination and NOT flag it as "atom is both
excluded and used." The rule: heading_path references do not count as "usage"
for coverage purposes. Only core_atoms and context_atoms count.

This must be stated explicitly in any documentation or onboarding material,
because someone reading the spec fresh will see an atom that is simultaneously
excluded and referenced, and assume it's a bug.

## Lesson 16: Cross-layer content uses relations, not context_atoms

A matn excerpt should never have a footnote atom in its context_atoms (or vice
versa). Cross-layer relationships are expressed through typed relations
(footnote_supports, footnote_explains, etc.) that connect two separate
excerpts, each in its own layer.

Why: source_spans offsets are layer-specific (they refer to either the matn
canonical or the footnote canonical, never both). Mixing layers in
context_atoms would create offset confusion. Relations keep the layers clean.

## Lesson 17: Large excerpts are acceptable when the author's discussion is continuous

Passage 1's غرابة excerpt (jawahir:exc:000005) has 16 core atoms spanning approximately 3
pages of the original book. This is large but correct — the author treats
غرابة as one continuous discussion with internal sub-divisions (حيرة vs
وحشي) that never break into separate topics. The rule:

- If the author provides a clear structural break (new heading, new topic
  marker like "وأما..."), that break should create a new excerpt.
- If the author continues discussing the same عيب with internal
  sub-classifications, examples, and scholarly disputes, it stays one excerpt.
- The boundary reasoning must explain why the excerpt is large and confirm
  that no natural break was missed.

For synthesis, the LLM will receive the full excerpt. If it's too large for
effective synthesis, that's a synthesis-layer problem to solve (e.g., by
summarizing sub-sections), not an excerpting-layer problem. Excerpts must
reflect the author's actual discourse structure, not artificial length limits.

## Lesson 18: Every vocabulary in the system must be extensible

No enumeration in the system — roles, relation types, atom types, exclusion
reasons, case types, taxonomy nodes — should be treated as a permanently closed
list. Content sovereignty means the CONTENT drives what categories exist, not the
other way around. However, vocabularies are closed allowlists within a given
schema version — extension requires a schema version bump with documented
justification. Unknown values must fail validation, not pass silently.

The starting vocabularies are:
- Core roles: author_prose, evidence, exercise_content
- Context roles: classification_frame, preceding_setup,
  cross_science_background, back_reference
- Relation types: footnote_supports, footnote_explains, footnote_source,
  footnote_citation_only, has_overview, shared_shahid, exercise_tests, etc.
- Atom types: heading, prose_sentence, bonded_cluster, list_item,
  verse_evidence
- Exclusion reasons: heading_structural, footnote_apparatus,
  duplicate_content, etc.

When the system encounters content that doesn't fit ANY existing category,
it proposes a new entry (subject to human review). This applies equally to
the taxonomy tree AND to every other vocabulary in the schema. Nothing in
the system should be hardcoded or stale. There should be NO LIMITING FACTORS
that prevent the system from growing to faithfully represent whatever content
it encounters.

**Clarification:** "extensible" does not mean "open-ended at runtime." All
enumerations are closed allowlists within a given schema version — the
validator rejects unknown values. Extension happens via a schema version
bump with documented justification. This gives strict correctness checking
within a version and controlled evolution across versions.

The same principle applies to evidence source metadata. An author may cite
a verse by المتنبي with an explicit attribution in the متن, while another
author may cite the same verse with the attribution only in a footnote, and
a third may cite it with no attribution at all. The system must be ready
to capture source metadata at the atom level when it is available, and to
grow its source vocabulary as new citation patterns emerge.

## Lesson 19: Self-critical design review is not optional

The system architect (whether human or LLM) must proactively identify design
flaws, not wait for them to be discovered during testing or downstream
breakage. Every design decision should be stress-tested with the question:
"will this cause regret when we scale to 100 books?" Common failure modes:

- A field name or type that works for book 1 but is semantically wrong for
  the general case (e.g., "core_atom_ids" sounding like a flat list when the
  system actually needs structured entries with roles).
- An implicit rule that is never formally documented (e.g., heading atoms
  being both excluded and referenced — correct behavior, but confusing if
  not stated explicitly).
- A vocabulary that is accidentally treated as closed (e.g., only having
  footnote_supports and footnote_explains, not anticipating footnote_source).
- A documentation statement that contradicts the actual data model (e.g.,
  "byte range" written where the actual unit is unicode codepoints).

These are not cosmetic issues. Each one is a landmine that will cause either
data corruption, incorrect synthesis, or expensive retrofitting at scale.
They must be caught during design, not during production.

## Lesson 20: Prose quotations used as شواهد get role=evidence

When the author cites a prose quotation from another source as شاهد (proof
or illustration), the cited text gets role=evidence — same as verse شواهد.
The atom_type captures the FORM (prose_sentence vs verse_evidence); the role
captures the FUNCTION (evidence vs author_prose). These are orthogonal.

Discovered via atom 036 (عيسى بن عمرو's "تكأكأتم" quotation): identical
evidential function to surrounding verse شواهد (atoms 026, 038, 040), but
was initially misclassified as author_prose because it was prose, not verse.

## Lesson 21: Exercise set↔item relations are mandatory

Each exercise item (exercise_role=item) and each exercise answer
(exercise_role=answer) MUST carry a `belongs_to_exercise_set` relation
pointing to exactly one exercise set. Without this, exercise groupings
cannot be reconstructed at scale. The validator enforces: exactly one
`belongs_to_exercise_set` per item/answer.

## Lesson 22: Exercise answer footnotes are excerpts, not apparatus

Footnotes in exercise sections may contain explicit scholarly judgments
identifying the عيب in an exercise item (e.g., "جعجعة غير فصيحة لتنافر
حروفها"). These are NOT word glosses — they pass the dependency test and
contain the answer key for the exercise. Treatment:

- exercise_role = "answer"
- core_atoms role = "exercise_answer_content"
- Linked to the exercise item via `answers_exercise_item` relation
- Placed at the exercise taxonomy node (tatbiq_*), NEVER at concept leaves
- tests_nodes / primary_test_node aligned with the exercise item they answer

Distinguishing from pure apparatus: if the footnote merely glosses a word
(e.g., "الاسفنط = الخمر"), it stays excluded. If it provides a scholarly
judgment identifying which عيب applies, it becomes an answer excerpt.

## Lesson 23: Author inconsistencies must be documented, never silently corrected

When the source text contains internal contradictions (e.g., a summary that
lists different items than the original enumeration), both versions are
preserved per content sovereignty. But the inconsistency MUST be documented:
- source_inconsistency internal_tag on the relevant atom
- Explicit note in the excerpt's boundary_reasoning
- "No node from summary-only" caution: do not auto-create taxonomy nodes
  from terms that appear only in drive-by mentions without substantive treatment

## Lesson 24: Relations are intentionally unidirectional

Relations express authorial/structural directionality (e.g., "this item
belongs to this set", "this answer addresses this item", "this excerpt
has an overview"). The reverse direction is always computable at query time.
The system does NOT store bidirectional relations — this is by design, not
an omission. Documentation must state this explicitly to prevent well-meaning
"fixes" that add redundant back-links.

## Lesson 25: Orphaned footnote references need explicit status

Source texts may contain footnote reference markers (e.g., "(1)") that point
to no corresponding footnote text (printing errors, missing pages, etc.).
These must not be left as empty footnote_atom_ids arrays — they need an
explicit `footnote_ref_status: "orphan"` with an `orphan_note` explaining
why. The validator enforces: non-empty atom_ids OR explicit orphan status.

## Lesson 26: Quotation-role heuristic catches real errors

The validator should warn when an atom's atomization_notes mention "quotation"
or "quoted" but the atom is assigned role=author_prose. This heuristic caught
the atom 036 error and flagged fn:006 (المثل السائر quotation) for review.
False positive rate is low; true positive value is high. Keep as warning, not
error, since some edge cases (author narrating another's view) are legitimate
author_prose.

## Lesson 27: Extended scholarly quotations are evidence, not author_prose

When the footnote author (or متن author) quotes at length from another
scholarly work — not just a single verse شاهد but an extended analytical
passage — the quoted atoms are still role=evidence (since they are "external
prose cited by the author"). The atom_type stays prose_sentence (it IS prose),
but the role reflects that these are NOT the current author's own words.

Discovered via jawahir:exc:000010 (fn:006-009): an extended quotation from المثل السائر
by ابن الأثير, introduced by الهاشمي. All four atoms were initially
author_prose, but they are actually ابن الأثير's analysis. Only fn:010
("انتهى عن المثل السائر ـ بتصرف") is genuinely author_prose — it's the
attribution/closing formula.

This generalizes: any time one author cites another's analytical text,
the cited portion gets role=evidence regardless of length. The current
author's own attribution formulas, transitions, and framing remain
author_prose. The boundary between "author narrating" and "author quoting"
is determined by whether the words belong to the current author or to
the cited source.

## Lesson 28: Audits must cite baseline SHA and file+record IDs

Every formal audit of a baseline must include:
1. The baseline_sha256 from the manifest (so the exact files are unambiguous)
2. For each finding: the specific file, record_type, and record ID (e.g.,
   "passage1_excerpts_v02.jsonl, excerpt jawahir:exc:000005, core_atoms[4]")
3. A "NOT CHECKED" section listing which aspects were deliberately excluded
   from the audit scope (so readers don't assume unchecked = validated)

This prevents cross-version confusion (auditing stale files) and ensures
findings are reproducible. The v0.2.2→v0.3.0 transition exposed this:
a third-party review mixed valid findings with stale claims, partly because
neither party anchored to a specific SHA.

## Lesson 29: Enums are closed per schema version, extensible via version bumps

Vocabularies (roles, relation types, exclusion reasons, atom types, etc.)
are closed enumerations within any given schema version. This is NOT a
contradiction with the "extensible vocabularies" principle — it means:

- Within v0.3.0, ONLY the listed values are valid. The validator enforces
  this strictly (no "custom:*" escape hatch in production baselines).
- When new content requires a new value, the schema is bumped to v0.3.1
  (or v0.4.0 for larger changes), the new value is added to the enum, and
  a changelog entry documents why.
- The --allow-unknown-vocab flag exists ONLY for development/exploration,
  never for gold baselines.

This gives us the benefits of both worlds: strict correctness checking
within a version, and controlled evolution across versions. Every vocabulary
expansion is auditable via the schema diff between versions.

## Lesson 30: Known untested patterns (forward-compatibility watch list)

Passage 1 covers a relatively well-structured section with clear headings,
a single topic hierarchy, and straightforward footnotes. The following
patterns have NOT been tested yet and may require schema or design changes
when encountered:

**Structural patterns:**
- متن/شرح/حاشية multi-layer sources (Passage 1 has only matn + footnote)
- Books with no section headings (pure prose flow requiring topic inference)
- Deeply nested sub-headings (Passage 1 goes only 4 levels deep)
- Cross-references between distant sections of the same book
- Footnotes that reference other footnotes

**Content patterns:**
- Scholarly dispute blocks (خلاف) spanning many pages with multiple positions
- Extended false transitions (author appears to change topic but doesn't)
- Content that genuinely belongs at multiple taxonomy nodes equally
  (not the cross-science case — same science, genuinely dual-homed)
- Verse used simultaneously as evidence in teaching AND as exercise content
- Tables, diagrams, or other non-prose content

**Scale patterns:**
- Books with 100+ excerpts per section (excerpt ID numbering, relation density)
- Multiple books at the same taxonomy node (synthesis collision handling)
- Taxonomy nodes that need restructuring after being populated with excerpts
  from earlier books (migration planning)

When any of these patterns is first encountered, it should trigger a
design review before implementation — do not assume the current schema
handles it correctly. Add the pattern, the decision, and the reasoning
to lessons learned.
