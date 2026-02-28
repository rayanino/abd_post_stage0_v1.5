# Stage 2: Structure Discovery — Edge Cases

## EC-S.1: Same keyword at different hierarchy levels

**Situation:** شذا العرف uses `باب` at level 1 (الباب الأول: في الفعل) AND level 3 (الباب الأول: فَعَلَ يَفعُل). The word "باب" appears at two different nesting depths.
**Resolution:** The LLM (Pass 3) must determine hierarchy from context, not from keyword alone. The level-3 باب has a verb-paradigm title pattern (فَعَلَ يَفعُل) that distinguishes it from a top-level باب. The ordinal sequence also helps: the level-3 أبواب are numbered 1–6 (the six classical verb paradigms), while the level-1 أبواب are also numbered 1–3 but cover broad topics (verbs, nouns, shared rules).

## EC-S.2: Untagged divisions (no `<span class="title">`)

**Situation:** Real divisions exist in the text but have no HTML heading markup. Observed in both books:
- شذا العرف: 6 verb-paradigm أبواب are plain text
- جواهر البلاغة: some المبحث instances lack title spans; تنبيهات and خاتمة are untagged
**Resolution:** Pass 2 (keyword heuristics) catches most of these. Pass 3 (LLM) catches the rest. All untagged divisions are flagged with `confidence: medium` or `low`.

## EC-S.3: Inline division markers

**Situation:** Division keyword is not on its own line but embedded in running text.
**Example:** `تنبيه -قد عَلِمت مما تقدم أن الاسم المتمكن...` (شذا العرف p.23)
**Resolution:** Pass 2 detects via "keyword + dash + content" pattern (confidence: low). The division boundary is at the keyword. The text after the dash is the first content of the new division.

## EC-S.4: TOC exists but doesn't match content headings exactly

**Situation:** The TOC page lists division titles that don't exactly match the in-text headings (slightly different wording, missing diacritics, abbreviated).
**Example:** TOC says `فصل في معاني صيغ الزوائد` but in-text heading says `فصل فى معانى صيغ الزوائد` (different ي spelling).
**Resolution:** Use fuzzy matching (normalized Arabic text comparison, ignoring diacritics and ي/ى variation). Match on keyword + ordinal first, fall back to text similarity.

## EC-S.5: Heading that's actually a topic sentence, not a division

**Situation:** A line starts with a keyword but is actually a topic sentence within continuous text, not a structural division.
**Example:** `باب` used literally in "وهذا الباب واسع في اللغة العربية" ("this topic is broad in Arabic").
**Resolution:** Pass 2 filters: line length >300 chars → reject. If shorter, check for preceding conjunction (وهذا) → reject. LLM Pass 3 as final arbiter.

## EC-S.6: Editor-inserted headings

**Situation:** Modern editors sometimes insert section headings that the original author didn't write. These are enclosed in brackets or marked with editorial notes.
**Example:** `[فصل في أحكام الإدغام]` — brackets indicate editorial insertion.
**Resolution:** Detect bracket patterns. Flag as `editor_inserted: true`. Still use as divisions (they're usually helpful), but record the source as editorial.

## EC-S.7: Non-digestible sections

**Situation:** Parts of the book that shouldn't be atomized/excerpted: editor introduction, table of contents, endorsements, bibliography.
**Detection rules:**
- مقدمة المحقق / مقدمة المعلق → non-digestible (editor content)
- خطبة الكتاب → non-digestible (rhetorical praise, usually)
- فهرس الموضوعات / المحتويات → non-digestible (but use as cross-reference)
- تقاريظ الكتاب → non-digestible
- Author's مقدمة → UNCERTAIN: may contain substantive definitions. Flag for human review.
**Resolution:** Mark `digestible: false` or `digestible: uncertain`. Passages are only created from digestible divisions.

## EC-S.8: Exercise sections

**Situation:** Sections labeled تمارين, تطبيق, مسائل التمرين, أسئلة contain exercises, not teaching content.
**Resolution:** Mark as `digestible: true` with `content_type: exercise`. These become passages whose excerpts will have `type: exercise`.

## EC-S.9: Very long division with no sub-divisions

**Situation:** A باب or فصل spans 30+ pages with no detected sub-headings.
**Resolution:** Flag for review. LLM attempts to find implicit topic boundaries. If found → split. If not found → keep as single long passage with `review_flags: ["long_passage"]`. Human decides.

## EC-S.10: Very short division (<1 page)

**Situation:** A تنبيه or فرع is only a few lines long.
**Resolution:** Apply merge rules (STRUCTURE_SPEC §6.3). Merge into parent division's passage. If merge would create passage >15 pages, keep as standalone tiny passage.

## EC-S.11: Division spans a page break mid-sentence

**Situation:** A division's heading is at the bottom of page N, and its content starts at the top of page N+1.
**Resolution:** The division's `start_page` is the page where the heading appears (page N). Content extraction includes both pages.

## EC-S.12: Duplicate headings

**Situation:** The same heading text appears twice (e.g., two different sections both called "فصل").
**Resolution:** Each instance is a separate division. Distinguish by page number and parent context. The division `id` is unique regardless of title duplication.

## EC-S.13: Book with zero structure

**Situation:** A very old or simple text has no headings, no keywords, no TOC. Pure continuous prose.
**Resolution:** LLM Pass 3 attempts to find topic boundaries. If successful → use those. If the LLM also finds no structure → create one passage per N pages (configurable, default 10). Flag entire book as `structure_confidence: low`.

## EC-S.14: Nested footnotes containing division keywords

**Situation:** A footnote mentions "باب" or "فصل" as a reference, not as a structural heading.
**Resolution:** Pass 2 excludes footnote text from keyword scanning. Stage 1 already separates matn from footnotes.

## EC-S.15: مقدمة (Author's Introduction) content decision

**Situation:** The author's مقدمة sometimes contains genuine definitions and conceptual foundations that belong in the taxonomy, sometimes contains only praise and biographical info.
**Resolution:** Flag as `digestible: uncertain`. LLM evaluates content. If substantive definitions are found → `digestible: true`. If purely rhetorical → `digestible: false`. Human confirms.

## EC-S.16: Dictionary-style books (extreme heading density)

**Situation:** معجم تيمور الكبير has 4,346 headings across 1,771 pages (~2.5 headings/page). Each "heading" is a dictionary entry, not a structural chapter.
**Detection:** Heading density > 1.5 headings/page across the book.
**Resolution:** Flag as `book_genre: dictionary`. Each entry is a micro-division. Passaging strategy changes: group adjacent entries into passages of 5–15 pages rather than treating each entry as a standalone passage. The grouping should respect alphabetical or thematic boundaries where possible.

## EC-S.17: Large book with zero tagged headings

**Situation:** إسفار الفصيح (997 pages) and تصحيفات المحدثين (870 pages) have ZERO content heading spans. All structure is untagged.
**Detection:** Zero double-quote title spans in content pages.
**Resolution:** Pass 1 produces nothing. Pass 2 (keyword heuristics) and Pass 3 (LLM) must carry the entire burden. Flag as `structure_confidence: low` until human reviews. If Pass 2+3 also find very few divisions, consider genre-specific handling (e.g., commentary books may be structured by the base text's structure rather than their own headings).
