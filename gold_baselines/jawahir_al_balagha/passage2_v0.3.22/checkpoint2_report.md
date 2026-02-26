# CHECKPOINT 2 — Canonicalization & Atomization Report
## Passage 2: جواهر البلاغة, pp. ص ٢٦ → ص ٣٢

**Date:** 2026-02-21
**Schema:** gold_standard_v0.3.1
**Continuation from Passage 1:** all verified ✓

---

## A. CANONICAL FILES

| File | Chars | Bytes (UTF-8) | SHA-256 | Atoms |
|------|-------|---------------|---------|-------|
| passage2_matn_canonical.txt | 4,542 | 8,147 | `a17c82f...` | 86 |
| passage2_fn_canonical.txt | 7,642 | 13,599 | `6b69c45...` | 66 |

### Canonicalization Corrections Applied
1. **ى القنوعو (p.32 line 1):** Shamela corruption/duplicate fragment of القنوع from p.31 last line. **Discarded.** The complete verse already appears on p.31.
2. **Footnote reference markers:** Stripped `(N)` patterns at end-of-line (fn refs) while preserving:
- IMPORTANT: Enumeration labels like '(1) ...' at the *start* of exercise items are treated as authorial numbering, not as footnote markers, and therefore are NOT recorded in atom `footnote_refs`.
   - Authorial exercise/section numbering (e.g., '(1)' at start of an item) is preserved in text but is not treated as a footnote marker
   - Inline content enumeration (e.g., 6 عيوب list on p.32)
   - Footnote labels within footnote canonical (kept as plain text)
3. **بقَرمَد (2) ِ** (p.30): Stripped fn ref `(2)` and stray diacritical ِ after verse end.
4. **كثرة التكرار (2) (6)** (p.32): The `(2)` was a fn ref to p.32 footnote about التكرار; the `(6)` is enumeration item #6. Stripped only the `(2)`.

---

## B. ATOM STATISTICS

### Matn Layer: 86 atoms (jawahir:matn:000060 → 000145)

| Atom Type | Count | Description |
|-----------|-------|-------------|
| exercise_content | 45 | Exercise items, instructions, specimens |
| verse_evidence | 20 | Poetic evidence (شواهد) |
| prose_sentence | 10 | Definitions, attributions, commentary |
| heading | 7 | Section/exercise headings |
| prose_evidence | 3 | Extended prose specimens (امرؤ القيس) |
| list_item | 1 | 6-عيوب enumeration (p.32) |

### Footnote Layer: 66 atoms (jawahir:fn:000037 → 000102)

| Atom Type | Count | Description |
|-----------|-------|-------------|
| prose_sentence | 58 | Glosses, commentary, تنبيهات, definitions |
| verse_evidence | 7 | Evidence verses within تنبيهات section |
| bonded_cluster | 1 | المتلمس verse + continuation |

### Grand Total: 152 atoms

---

## C. NOTABLE ATOMIZATION DECISIONS

### C.1 Bonded Clusters
- **T1 (matn:000072–000073):** امرؤ القيس prose specimen spans two canonical lines due to Shamela line wrapping. Single prose_evidence unit.
- **T2 (fn:000076):** المتلمس verse + continuation form a single poetic specimen illustrating الابتذال ضرب 2.

### C.2 Page 27 Inline Footnote References
The امرؤ القيس prose passage had 8 inline footnote markers `(1)`–`(8)` glossing individual غرابة words (جفنة, الصمادح, احبنطى, خنفقيق, نقاخا, ينباع, مصوون, البعاق). These were stripped from the matn canonical since they're apparatus markers, not content. The corresponding fn atoms (jawahir:fn:000042–000049) are cross-referenced via `footnote_refs` in the matn atom.

### C.3 Duplicate Footnotes (Shamela Export Artifact)
Two footnotes are duplicated across page boundaries:

| First Occurrence | Duplicate | Content | Decision |
|-----------------|-----------|---------|----------|
| p.28 fn(12) = jawahir:fn:000062 | p.30 fn(1) = jawahir:fn:000088 | النصاح glosses | fn:000088 marked for exclusion |
| p.29 fn(2) = jawahir:fn:000087 | p.30 fn(2) = jawahir:fn:000089 | الدمية glosses | fn:000089 marked for exclusion |

Differences confirmed as trivial: fn number labels `(12)` vs `(1)`, and one comma presence/absence.

### C.4 تنبيهات Section (fn atoms 000069–000084)
The p.29 footnote block contains substantial scholarly content (16 atoms) teaching:
- **الابتذال** as an additional عيب of فصاحة المفرد, with two ضربان
- **الألفاظ المبهمة** — avoid ambiguous words when precision is the goal
- **اللفظ المشترك** — avoid polysemous words without clarifying context

These are atomized as teaching content in the footnote layer. New taxonomy nodes will be proposed at Checkpoint 3.

### C.5 Exercise Structure
Six exercise sections identified and atomized:

| Section | Lines | Items | Heading Atom |
|---------|-------|-------|-------------|
| تمرين (أ) | 24–28 | 4 essay Qs | matn:000083 |
| تمرين (ب) | 29–42 | 9 specimens | matn:000088 |
| تمرين (identify) | 43–46 | 2 items (أ/ب) | matn:000102 |
| تطبيق | 47–52 | 4 verses | matn:000106 |
| تدريب (1) | 63–70 | 3 items | matn:000122 |
| تدريب (2) | 71–78 | 6 items | matn:000130 |

### C.6 Page 28 Footnote (13) — Multi-Item Gloss
fn(13) spans three atoms (fn:000063–000065) serving multiple exercise items:
- (13a) glosses تمرين item أ (ابن الرومي verse)
- Continuation glosses تمرين item ب
- Continuation glosses تطبيق items (الظلم/أسود تفضيل)
Each sub-section atomized as a separate prose_sentence in the footnote layer, per FLAG 4 decision.

---

## D. VALIDATION RESULTS

| Check | Status |
|-------|--------|
| SHA-256 consistency (all atoms) | ✅ |
| Sequential atom IDs (no gaps) | ✅ |
| Text matches canonical at offsets | ✅ |
| No gaps/overlaps in offset coverage | ✅ |
| Full canonical coverage | ✅ |
| All footnote cross-refs point to valid fn atoms | ✅ |

---

## E. FILES PRODUCED

| File | Location | Purpose |
|------|----------|---------|
| passage2_matn_canonical.txt | /home/claude/ | Canonical matn text |
| passage2_fn_canonical.txt | /home/claude/ | Canonical footnote text |
| passage2_matn_atoms_v02.jsonl | /home/claude/ | 86 matn atom records |
| passage2_fn_atoms_v02.jsonl | /home/claude/ | 66 fn atom records |

---

## F. CONTINUATION STATE (for Checkpoint 3)

| Field | Value |
|-------|-------|
| next_matn_atom_seq | 146 |
| next_fn_atom_seq | 103 |
| Duplicate fn atoms to exclude | jawahir:fn:000088, jawahir:fn:000089 |
| Taxonomy changes needed | TC-004+ for الابتذال, الألفاظ المبهمة, اللفظ المشترك, exercise nodes, فصاحة الكلام children |

---

## CHECKPOINT 2 STATUS: COMPLETE — AWAITING REVIEW

**Questions for your review:**

1. Does the matn canonical text look correct? (86 lines, footnote markers properly stripped/kept)
2. Is the exercise section atomization granularity appropriate? (each question/verse = one atom)
3. The تنبيهات atomization yielded 16 fn atoms — is this granularity right, or should some be merged?
4. Ready to proceed to Checkpoint 3 (excerpting + taxonomy proposals)?

## B. ATOM JSONL OUTPUTS (generated)

| File | Records | First ID | Last ID | Offset audit |
|------|---------|----------|---------|------------|
| passage2_matn_atoms_v02.jsonl | 86 | jawahir:matn:000060 | jawahir:matn:000145 | PASS |
| passage2_fn_atoms_v02.jsonl | 66 | jawahir:fn:000037 | jawahir:fn:000102 | PASS |

### Spot-check samples

**MATN first 5 atoms:**

- jawahir:matn:000060 [prose_sentence] (page ص:٢٦): وقال الفرزدق:
- jawahir:matn:000061 [verse_evidence] (page ص:٢٦): واذا الرجال رأوا يزيد رأيتهم خُضعَ الرَّقاب نواكس الأبصار
- jawahir:matn:000062 [prose_sentence] (page ص:٢٦): وقال أبو تمّام:
- jawahir:matn:000063 [verse_evidence] (page ص:٢٦): قد قلت لمّا اطلخمَّ الأمر وانبعثت عشواء تاليةً غيساً دهاريسا
- jawahir:matn:000064 [prose_sentence] (page ص:٢٦): وقال شمر:

**MATN last 5 atoms:**

- jawahir:matn:000141 [prose_sentence] (page ص:٣٢): الأول - «تنافُر الكلمات مُجتمعة» أن تكون الكلمات ثقيلة على السمع من تركيبها مع بعضها، عَسرة النّطق بها مُجتمعةً على اللّسان (وإن كان كل جزء منه على انفراده فصيحاً) والتنافر يَحصُل: إمِّا بتجاوُز كلمات متقاربة الحروف وإمّا بتكرير كلمة واحدة.
- jawahir:matn:000142 [prose_sentence] (page ص:٣٢): (1) ومنه شديد الثِّقل: كالشطر الثاني في قوله:
- jawahir:matn:000143 [verse_evidence] (page ص:٣٢): وَقبرُ حرب بمكان قفرٌ وَليس قَرب قبر حربٍ قبرُ
- jawahir:matn:000144 [prose_sentence] (page ص:٣٢): (ب) ومنه خفيف الثِّقل كالشطر الأول في قلو أبي تمَّام:
- jawahir:matn:000145 [verse_evidence] (page ص:٣٢): كريم ٌ متى أمدَحهُ والورى معي: وإذا ما لمته لمته وحدي

**FOOTNOTE first 3 atoms:**

- jawahir:fn:000037 [prose_sentence] (page ص:٢٦): (1) ـ فقد جمع (ناكس) على (فواعل) شذوذا وهذا لا يطرد إلا في وصف لمؤنث عاقل لا لمذكر كما هنا إلا في موضعين (فوارس وهوالك) والناكس: مطأطئ الرأس.
- jawahir:fn:000038 [prose_sentence] (page ص:٢٦): (2) ـ قال صاحب المثل السائر ـ ان لفظ (اطلخم) من الالفاظ المنكرة التي جمعت الوصفين القبيحين في انها غريبة، وانها غليظة في السمع كريهة على الذوق، وكذلك لفظة (دهاريس) واطلخم: أي اشت وعظم، والعشواء الليلة المظلمة، والغبسة جمع اغبس وغبسا: وهي الشديدة الظلام مثلها ـ والدهاريس جمع دهريس وهي الدواهي.
- jawahir:fn:000039 [prose_sentence] (page ص:٢٦): (3) - الماء العذب الصافي

**FOOTNOTE last 3 atoms:**

- jawahir:fn:000100 [verse_evidence] (page ص:٣٢): على أن بعضهم أجازهما لوقوعهما في القرآن كما في قوله تعالى «ونفس وما سواها» الآيات - وفي قوله تعالى «ذكر رحمت ربك عبده زكريا»
- jawahir:fn:000101 [prose_sentence] (page ص:٣٢): (3) حرب بن أمية: قتله قائل هذا البيت، وهو هاتف من الجن صاح عليه (وقفر) خال من الماء والكلأ، وقبر اسم ليس مؤخر، وقرب خبرها مقدم - قبل إن هذا البيت لا يمكن إنشاده ثلاث مرات متوالية ألا ويغلط المنشد فيه، لأن نفس اجتماع كلماته وقرب مخارج حروفها، يحدثان ثقلا ظاهراً، مع أن كل كلمة منه لو أخذت وحدها ما كانت مستكرهة ولا ثقيلة.
- jawahir:fn:000102 [prose_sentence] (page ص:٣٢): (4) أي هو كريم، وإذا مدحته وافقني الناس على مدحه، ويمدحونه معي، لإسداء إحسانه إليهم كاسدائه إلى، وإذا لمته لا يوافقني أحد على لومه، لعدم وجود المقتضى للوم فيه - وآثر لمته على هجوته مع أنه مقابل المدح إشارة إلى أنه لا يستحق الهجو ولو فرط منه شيء فإنما يلام عليه فقط، والثقل في قوله «أمدحه» لما بين الحاء والهاء من التنافر، للجمع بينهما: وهما من حروف الحلق - كما ذكره الصاحب اسماعيل بن عباد..
