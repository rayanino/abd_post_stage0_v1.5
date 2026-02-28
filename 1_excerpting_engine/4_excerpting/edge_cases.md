# Stage 4: Excerpting — Edge Cases

---

## Multi-Topic Content (the core challenge)

### EC-E.1: Incidental mention of another topic (Category A)

**Situation:** An excerpt about التشبيه (simile) mentions "unlike in المجاز (metaphor) where the resemblance is implicit."
**Resolution:** The mention of المجاز is incidental — a passing contrast. The atom stays in the excerpt with `role: core`. No special handling. The excerpt is placed at the التشبيه node.

### EC-E.2: Supportive dependency — bounded (Category B)

**Situation:** An excerpt about إسناد الفعل إلى الضمائر (verb conjugation with pronouns) contains 2 atoms explaining what ضمائر (pronouns) are. This is نحو content within a صرف passage.
**Resolution:** The 2 pronoun-definition atoms get `role: context` with `context_justification: "Definition of ضمائر needed for understanding conjugation rules"`. The excerpt stays unified, placed at the صرف node. `cross_science_context: "nahw"` is set. The dependency is bounded (2 atoms, author returns to صرف immediately after).

### EC-E.3: Sovereign teaching — clean split (Category C)

**Situation:** A passage in جواهر البلاغة has 10 atoms about الخبر (assertion), then 8 atoms that independently teach الإنشاء (performative), then 5 more atoms about الخبر again.
**Resolution:** Three excerpts:
1. Excerpt 1: atoms 1–10 about الخبر → placed at الخبر node
2. Excerpt 2: atoms 11–18 about الإنشاء → placed at الإنشاء node
3. Excerpt 3: atoms 19–23 about الخبر → placed at الخبر node, with `relation: continues` pointing to Excerpt 1

The key test: atoms 11–18 are self-contained teaching of الإنشاء. Removing them from Excerpt 1 doesn't damage it. They are sovereign.

### EC-E.4: Sovereign teaching — but atoms are interwoven (Category C → B3_interwoven)

**Situation:** The author compares التشبيه and الاستعارة side by side, atom by atom. Each atom teaches both concepts simultaneously. Splitting would destroy both explanations.
**Resolution:** Apply BD §10.1 (interwoven content):
- Create one excerpt containing all atoms
- Duplicate it: Copy 1 placed at التشبيه node, Copy 2 placed at الاستعارة node
- Both copies get `interwoven_group_id: "IWG_001"` linking them
- Both are flagged `B3_interwoven: true`
- This is a last resort — attempted splitting first.

### EC-E.5: Supportive dependency that sprawls (B → reclassify as C)

**Situation:** An excerpt about الإطناب (amplification) contains atoms explaining what الإيجاز (conciseness) is. The author spends 6 atoms on الإيجاز, going well beyond what's needed to understand الإطناب.
**Resolution:** The boundedness guardrail (BD §8.3) triggers: 6 atoms exceeds the typical 1–3 for a bounded dependency. Reclassify from B to C. Split: the الإيجاز atoms become their own excerpt.

### EC-E.6: Cross-science dependency

**Situation:** A بلاغة excerpt about المسند إليه needs to explain the نحو concept of المبتدأ والخبر. The author gives 3 atoms of نحو explanation.
**Resolution:** The 3 نحو atoms are supportive dependency (Category B) IF they are bounded and the author returns to بلاغة. They get `role: context`, `cross_science_context: "nahw"`. The excerpt is placed in the بلاغة tree. The نحو content is NOT separately excerpted into the نحو tree (it serves بلاغة, not نحو).

**EXCEPTION:** If the نحو explanation is sovereign (self-contained, unbounded), it becomes a separate excerpt classified as `nahw` and placed in the نحو tree.

---

## Excerpt Boundary Decisions

### EC-E.7: Author splits one topic across two structural divisions

**Situation:** The author discusses التشبيه in مبحث 4, then continues discussing it in مبحث 5 (perhaps with a different angle). These are separate passages from Stage 2.
**Resolution:** Each passage produces its own excerpts. Cross-passage excerpts about the same topic are linked via `relation: continues` or `relation: builds_on`. They are placed at the same taxonomy node (or adjacent nodes if the angle differs).

### EC-E.8: Very long excerpt (>15 atoms)

**Situation:** A single teaching topic legitimately requires 20 atoms to explain.
**Resolution:** Acceptable if the atoms genuinely form one coherent lesson. No artificial splitting. Flag for Judge review: "Large excerpt — verify no hidden topic boundaries."

### EC-E.9: Very short excerpt (1–2 atoms)

**Situation:** A brief definition or rule that stands alone.
**Resolution:** Acceptable if it's a self-contained teaching unit. Common for definitions. No minimum atom count for excerpts.

### EC-E.10: Exercise with embedded teaching

**Situation:** An exercise section (تطبيق) contains explanatory atoms before the actual exercises.
**Resolution:** Split: teaching atoms become a `teaching` excerpt; exercise atoms become an `exercise` excerpt. The exercise excerpt gets `relation: exemplifies` pointing to the teaching excerpt.

### EC-E.11: Exercise referencing content from a different passage

**Situation:** A تطبيق section at the end of a باب has exercises that refer to concepts taught across multiple مباحث.
**Resolution:** The exercise excerpt can have `relation: exemplifies` pointing to multiple teaching excerpts. Each relation is tracked independently.

---

## Science Classification

### EC-E.12: Excerpt clearly belongs to a different science than the book

**Situation:** A صرف book contains a section discussing إعراب (syntactic case endings), which is نحو.
**Resolution:** The excerpt is classified `science_classification: nahw`. It is placed in the نحو taxonomy tree, not the صرف tree. The book's registry entry records that it produced نحو excerpts.

### EC-E.13: Excerpt is genuinely outside all four sciences

**Situation:** A بلاغة book contains a passage about عروض (prosody/meter) which is not one of our four sciences.
**Resolution:** The excerpt is classified `science_classification: unrelated`. It is stored in `books/{book_id}/unrelated_excerpts/`. It is NOT discarded — it's preserved for potential future use.

### EC-E.14: Excerpt could be two sciences simultaneously

**Situation:** An excerpt teaches a concept that straddles صرف and نحو (e.g., إعلال which has both morphological and syntactic aspects).
**Resolution:** Classify by PRIMARY science — the one that best describes the core teaching. Set `related_science` to the secondary one. Do NOT duplicate the excerpt across both trees unless it's genuinely B3_interwoven (both sciences are independently and substantially taught).

### EC-E.15: Science classification confidence is low

**Situation:** The LLM is unsure whether content belongs to نحو or صرف (confidence < 0.6).
**Resolution:** Flag for human review with `review_flags: ["low_science_confidence"]`. Include the LLM's reasoning. Human decides.

---

## Role Assignment

### EC-E.16: Context atom that could be core in a different excerpt

**Situation:** Atom X is `role: context` in Excerpt A (it supports A's topic). But Atom X's content could be a core atom for a different excerpt.
**Resolution:** If the content is sovereign teaching of another topic → it SHOULD be a separate excerpt (Category C, not B). The dependency test (BD §8.2) would have caught this. If it genuinely passed the dependency test (content is definitional, bounded, serves the primary topic), it stays as context. It is NOT duplicated as a core atom elsewhere — that would mean it was sovereign all along.

### EC-E.17: All atoms in a group are context, none are core

**Situation:** A group of atoms all serve another excerpt's topic, with no core atoms of their own.
**Resolution:** This group is NOT an excerpt — it's a set of context atoms that should be attached to the excerpt they serve. If they can't be attached (different passage, too far away), they may be orphaned. Flag for review.

---

## Relation Edge Cases

### EC-E.18: Circular prerequisite chain

**Situation:** Excerpt A claims B is a prerequisite. Excerpt B claims A is a prerequisite.
**Resolution:** Schema validation catches this. Circular prerequisites are forbidden. One of the relations is incorrect — the Judge should identify which.

### EC-E.19: Implicit cross-reference by the author

**Situation:** Author writes "كما تقدم" ("as was mentioned earlier") without specifying what.
**Resolution:** If the referenced topic can be identified from context → create a `cross_reference` relation. If ambiguous → flag with `content_anomalies: ["ambiguous_back_reference"]`. Do NOT guess.

### EC-E.20: Excerpt from a later passage that redefines a concept from an earlier one

**Situation:** Passage 5 redefines or refines a concept that was defined in Passage 2's excerpt.
**Resolution:** Use `relation: refines` or `relation: builds_on`. The later definition does NOT replace the earlier one — both coexist as excerpts. The taxonomy may need a more specific node for the refined version.
