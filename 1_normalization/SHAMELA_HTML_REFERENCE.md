# Shamela HTML Export Reference

**Purpose:** Complete structural reference for the HTML format produced by [المكتبة الشاملة (Shamela Library)](https://shamela.ws/) desktop application exports. This is the **sole input format** for the ABD normalization pipeline.

**Audience:** A developer who has never seen Shamela HTML and needs to write or maintain the normalizer.

**Corpus validated against:** 1,046 files, 189,676 pages, three Arabic-language sciences (لغة، بلاغة، نحو وصرف).

---

## 1. Document Skeleton

Every Shamela HTML export follows this exact skeleton. There are zero exceptions across the corpus.

```html
<!DOCTYPE html>
<html lang='ar' dir='rtl'>
<head>
  <meta content='text/html; charset=UTF-8' http-equiv='Content-Type'>
  <style>
    /* Shamela presentation CSS — irrelevant to content extraction */
    body { direction: rtl; ... }
    .title { color: #800000; }
    .footnote, .PageHead { font: bold 16pt "Traditional Naskh"; color: #464646; }
    .PageText { text-align: justify; background-color: #EFEBD6; ... }
    /* etc. */
  </style>
  <title>BOOK TITLE</title>
</head>
<body>
  <div class='Main'>
    <!-- CONTENT: sequence of PageText divs -->
  </div>
</body>
</html>
```

**Key facts:**
- Encoding is always UTF-8.
- The `<style>` block is presentation-only; ignore it entirely.
- The `<title>` contains the Arabic book title.
- All content is inside `<div class='Main'>`.
- Within `Main`, the content is a flat sequence of `<div class='PageText'>` blocks (one per printed page), plus 1–4 metadata pages at the start.

---

## 2. Page Blocks

### 2.1 The PageText div

Every printed page is wrapped in `<div class='PageText'>...</div>`. This is the fundamental unit of the normalizer.

**CRITICAL: The nested-div trap.** You cannot use a regex like `<div class='PageText'>(.*?)</div>` to extract page content, because the footnote section is a NESTED `<div class='footnote'>` inside the PageText div. The closing `</div>` of the footnote div would be matched first, truncating the page.

**Correct approach:** Find all positions of the string `<div class='PageText'>` and take the content between consecutive positions. The last page runs to the end of the file (or to `</div>\n</div></body></html>`).

### 2.2 Page structure

A typical content page has this internal structure:

```
<div class='PageText'>
  ┌─ RUNNING HEADER ──────────────────────────────────────────────┐
  │ <div class='PageHead'>                                        │
  │   <span class='PartName'>BOOK TITLE</span>                    │
  │   <span class='PageNumber'>(ص: ٢٠)</span>                     │
  │   <hr/>                                                       │
  │ </div>                                                        │
  └───────────────────────────────────────────────────────────────┘
  
  ┌─ MATN (author's text) ────────────────────────────────────────┐
  │ Text content with </p> line breaks and <font> numbering       │
  │ ...                                                           │
  └───────────────────────────────────────────────────────────────┘
  
  ┌─ FOOTNOTE SEPARATOR ──────────────────────────────────────────┐
  │ <hr width='95' align='right'>                                 │
  └───────────────────────────────────────────────────────────────┘
  
  ┌─ FOOTNOTES ───────────────────────────────────────────────────┐
  │ <div class='footnote'>                                        │
  │   (1) ـ First footnote text                                   │
  │   <font color=#be0000>(2)</font> ـ Second footnote text       │
  │ </div>                                                        │
  └───────────────────────────────────────────────────────────────┘
</div>
```

Not all sections are always present. See §2.4 for the combinations.

### 2.3 Metadata/title pages (skipped)

The first 1–4 PageText blocks in every file are metadata pages with no page number. They look like this:

```html
<div class='PageText'>
  <span class='title'>جواهر البلاغة في المعاني والبيان والبديع&nbsp;&nbsp;&nbsp;</span>
  <span class='footnote'>(أحمد الهاشمي)</span>
  <p><span class='title'>القسم:</span> البلاغة
  <hr>
  <p><span class='title'>الكتاب<font color=#be0000>:</font></span> جواهر البلاغة في المعاني والبيان والبديع
  <p><span class='title'>المؤلف<font color=#be0000>:</font></span> أحمد بن إبراهيم بن مصطفى الهاشمي
  <p><span class='title'>الناشر<font color=#be0000>:</font></span> المكتبة العصرية، بيروت
  <p><span class='title'>عدد الصفحات<font color=#be0000>:</font></span> 344
  <p><font color=#be0000>[</font>ترقيم الكتاب موافق للمطبوع<font color=#be0000>]</font>
  <p><span class='title'>تاريخ النشر بالشاملة<font color=#be0000>:</font></span> 8 ذو الحجة 1431
</div>
```

**How to detect:** No `<span class='PageNumber'>` element. No `(ص: N)` text. **Action:** Skip entirely. These pages contain only bibliographic metadata already available elsewhere.

Note the `<span class='title'>` CSS class used here for labels like "القسم:", "الكتاب:", "المؤلف:". This class appears **only** on metadata pages.

Also note the lone `<hr>` (no width attribute) — this appears once per file on the title page. It is NOT the footnote separator.

### 2.4 Page type combinations

| Has header? | Has matn? | Has footnotes? | Frequency | Notes |
|:-----------:|:---------:|:--------------:|----------:|-------|
| ✓ | ✓ | ✓ | ~67% | Normal scholarly page |
| ✓ | ✓ | ✗ | ~33% | Page without footnotes |
| ✗ | ✓ | ✗ | 1–4/file | Metadata page (skipped) |
| ✓ | img only | ✗ | 7 total | Embedded page scan (rare) |

There are NO pages with footnotes but no matn. There are NO pages with a header but no content.

---

## 3. Running Header

### 3.1 Structure

```html
<div class='PageHead'>
  <span class='PartName'>جواهر البلاغة في المعاني والبيان والبديع</span>
  <span class='PageNumber'>(ص: ٢٠)</span>
  <hr/>
</div>
```

- **PartName**: The book/section title. Repeated identically on every page within a section. In single-work books, it's the book title on every page. In compilations, it may change between sections.
- **PageNumber**: Always in the format `(ص: N)` where N uses Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩). Never Western digits. Never missing on content pages.
- **`<hr/>`**: A self-closing HR inside the header div. This is the header separator — NOT the footnote separator. Different tag from `<hr width='95'>`.

### 3.2 Handling

**Remove entirely.** The running header is a print layout artifact:
- The book title is invariant metadata (captured elsewhere).
- The page number is extracted into `page_number_arabic` / `page_number_int` fields.
- The `<hr/>` is decorative.

### 3.3 Page number extraction

The page number is inside the PageNumber span but can also be extracted from anywhere in the block with the regex:

```regex
\(ص:\s*([٠-٩]+)\s*\)
```

This captures the Arabic-Indic digit string. Convert to integer with the mapping: ٠→0, ١→1, ٢→2, ٣→3, ٤→4, ٥→5, ٦→6, ٧→7, ٨→8, ٩→9.

**First page numbers in the corpus range from ١ to ٣٤٩ (some editions start numbering late).** Page numbers can exceed ٥٠٠٠ in large multi-volume works with continuous pagination.

---

## 4. HR Tags and Layer Separators (Critical Distinction)

Shamela exports contain three kinds of `<hr>` tags. Confusing them breaks the normalizer.

| Tag | Location | Count/file | Purpose |
|-----|----------|------------|---------|
| `<hr/>` | Inside `PageHead` div | 1 per content page (~311 in جواهر) | Header separator — decorative |
| `<hr width='95' align='right'>` | Between matn and footnotes | 0 or 1 per page (~207 in جواهر) | **Footnote separator — structural** |
| `<hr>` (no attributes) | Title/metadata page, OR before `<s0>` in sharh books | varies | See below |

**Only `<hr width='95'>` is the footnote separator.** It is the SOLE marker that separates the matn layer from the footnote layer. If you see it, everything after it (within the same PageText) is footnotes. If you don't see it, the page has no footnotes.

### 4.1 The `<s0>` commentary layer separator (1 book)

The book "ضياء السالك إلى أوضح المسالك" (4 volumes, 1,672 pages) uses a three-layer page structure instead of the normal two-layer structure. In this book, a plain `<hr>` followed by `<s0>` marks the boundary between the original text being commented on and the modern sharh (commentary/explanation):

```
Page structure in ضياء السالك:
┌─ HEADER ──────────────────────────────────────┐
│ <div class='PageHead'>...</div>               │
└───────────────────────────────────────────────┘
┌─ LAYER 1: Original text (matn al-asl) ───────┐
│ فصل: يتميز الاسم(1) بخمس علامات(2):         │
│ ...                                           │
└───────────────────────────────────────────────┘
  <hr><s0>          ← commentary separator
┌─ LAYER 2: Commentary (sharh) ─────────────────┐
│ (1) الاسم: كلمة تدل بذاتها...                 │
│ (2) إذا وجدت واحدة منها...                     │
│ ...                                           │
└───────────────────────────────────────────────┘
  <hr width='95' align='right'>   ← footnote separator (may be absent)
┌─ LAYER 3: Footnotes ─────────────────────────┐
│ <div class='footnote'>                        │
│ * "كلامنا" مبتدأ ومضاف إليه...               │
│ </div>                                        │
└───────────────────────────────────────────────┘
```

**Statistics for ضياء السالك vol 1 (419 content pages):**

| Page type | Count | Description |
|-----------|------:|-------------|
| Layers 1+2 only | 252 | Original text + commentary, no footnotes |
| Layers 1+2+3 | 143 | All three layers |
| Layers 1+3 only | 3 | Original text + footnotes, no commentary |
| Layer 1 only | 21 | Original text only |

**Key facts about `<s0>`:**
- It is an **unclosed void tag** (no `</s0>` exists anywhere in the corpus).
- It is ALWAYS preceded by `<hr>` (plain, no attributes). The pattern is always `<hr><s0>`.
- It appears in exactly 1 book (ضياء السالك), which has a duplicate "Copy" directory.
- 1,645 occurrences across 1,672 pages (present on nearly every content page).

**Normalizer handling:** The `<hr>` and `<s0>` are both stripped as generic HTML tags. Layers 1 and 2 are merged into `matn_text`. This is the correct behavior — the commentary IS part of the page content. The `<hr width='95'>` footnote separator still correctly identifies Layer 3. A future enhancement could separate the layers, but it is not required for the current pipeline.

**Important consequence:** In ضياء السالك, the commentary layer contains numbered notes `(1)`, `(2)`, etc. that look like footnote references or footnote entries but are structurally part of the matn (they appear before the `<hr width='95'>` separator). The normalizer treats these as matn content, which is correct. See §6.8 for details.

---

## 5. Matn (Author's Text)

### 5.1 What matn contains

Everything inside the PageText div, AFTER the running header and BEFORE the footnote separator (if any). This is the author's actual text — the content you're extracting.

### 5.2 Line breaks: the orphaned `</p>` pattern

Shamela does NOT use proper `<p>...</p>` paragraph tags. Instead, it uses **orphaned closing `</p>` tags** as line break markers:

```html
فصاحة الكلمة</p>
<font color=#be0000>1.</font> خلوصها من تنافر الحروف: لتكون رقيقة عذبة.</p>
<font color=#be0000>2.</font> خلوصها من الغرابة، وتكون مألوفة الاستعمال.</p>
```

There are no opening `<p>` tags. The `</p>` acts as a `<br>`. **Handling:** Convert `</p>` to `\n` (newline).

Occasionally `<br>` tags also appear. Convert those to `\n` as well.

### 5.3 Numbered list markers: `<font color=#be0000>`

Red-colored font tags wrap list numbering markers in the matn:

```html
<font color=#be0000>1.</font> خلوصها من تنافر الحروف
<font color=#be0000>2.</font> خلوصها من الغرابة
```

Also used for other decorative elements:
```html
<font color=#be0000>(</font>ت 1362هـ<font color=#be0000>)</font>    ← parentheses on metadata pages
<font color=#be0000>…</font>                                        ← ellipsis in verse
<font color=#be0000>[</font>ترقيم الكتاب<font color=#be0000>]</font> ← brackets
```

**The font color is ALWAYS `#be0000` (dark red). No other color values exist in the corpus.** This was validated across all 189,676 pages.

**Handling:** Unwrap the tag — keep the text content, remove the `<font>` and `</font>` tags. The numbered markers (`1.`, `2.`) become part of the normalized text. They are the author's original numbering.

### 5.4 Footnote reference markers in matn

When a page has footnotes, the matn contains reference markers pointing to the corresponding footnotes. These markers appear in **two formats** across the corpus:

**Format A — bare parenthesized number (majority of books):**
```html
خلوصها من الكراهة في السمع (1) .
```

**Format B — superscripted red number (11 books, including ضياء السالك, حاشيتان لابن هشام, التخمير, المصباح, etc.):**
```html
يتميز الاسم<sup><font color=#be0000>(1)</font></sup> بخمس علامات<sup><font color=#be0000>(2)</font></sup>:
```

After the normalizer unwraps the `<font>` tag and strips the `<sup>` tag, both formats produce the same plain text: `(1)`. The stripping logic works identically for both.

**Corpus prevalence of `<sup>` in footnote refs:** 11 books, ~62,000 total `<sup>` tags. In books that use Format B, ALL footnote refs use it consistently — there is no mixing of Format A and Format B within a single book.

These markers are **inline markers added by the editor**, not the author's text. They should be stripped — but ONLY when a matching footnote exists on the same page. See §10, Step 8i for the stripping logic.

### 5.5 Verse / poetry markers

Poetry lines use the hemistich separator `…` (U+2026 HORIZONTAL ELLIPSIS):

```
غدائره مستشزراتٌ إلى العلا تضل العقاص في مُثنَّى ومرسل
```

Some verse is wrapped in asterisk markers:

```html
* تركت ناقتي ترعى الهمخع*
```

**Handling:** Strip asterisks, preserve all text including the hemistich separator. Set `has_verse = true` on the page record.

### 5.6 Section headings within matn

Section titles like chapter names appear as plain text within the matn — they are NOT wrapped in any special tag in 99.9% of cases:

```
فصاحة الكلمة
```

This is simply the first line of text after the header removal. The normalizer does NOT detect or tag headings — that's a downstream atomization decision.

**Exception (1 book):** The book "التبيان في قواعد النحو" uses `<span data-type='title'>` for section headings:

```html
&#8204;<span data-type='title' id=toc-16>&#8204;الكلمة وأقسامها</span>
```

The `&#8204;` is a zero-width non-joiner (U+200C). **Handling:** Strip the span tag like all other HTML tags. The heading text is preserved. The ZWNJ characters are preserved (they're Unicode, not tags).

---

## 6. Footnotes

This is the most complex part of Shamela HTML and where most bugs hide.

### 6.1 Physical structure

Footnotes occupy the bottom portion of a page, after the `<hr width='95'>` separator, inside a `<div class='footnote'>` wrapper:

```html
<hr width='95' align='right'>
<div class='footnote'>
  (1) ـ First footnote text goes here.</p>
  <font color=#be0000>(2)</font> ـ Second footnote text.</p>
  <font color=#be0000>(3)</font> Third footnote (no dash).
</div>
```

### 6.2 Footnote numbering patterns

**The first footnote** in a div is plain text (not wrapped in a font tag):
```
(1) ـ footnote text
```

**Subsequent footnotes** (2nd, 3rd, etc.) have their number wrapped in a red font tag:
```html
<font color=#be0000>(2)</font> ـ footnote text
<font color=#be0000>(3)</font> footnote text
```

This is consistent across the entire corpus. The first `(N)` is never in a font tag; all others always are.

### 6.3 Dash separator variants

After the `(N)` number, there may or may not be a dash separator before the footnote text:

| Pattern | Example | Frequency in جواهر |
|---------|---------|-------------------|
| `(N) ـ text` | `(1) ـ الأسلوب الحكيم` | ~6% |
| `(N) text` | `(1) القياس مودة` | ~94% |

The dash can be:
- `ـ` (U+0640 ARABIC TATWEEL / kashida)
- `-` (U+002D HYPHEN-MINUS)
- `–` (U+2013 EN DASH)

**Handling:** Match `(N)` followed by optional whitespace + optional dash + optional whitespace. Strip the entire prefix (number + dash) to get the clean footnote text.

### 6.4 Parsing multiple footnotes from one div

A single `<div class='footnote'>` may contain 1 to 15+ footnotes. They are NOT in separate containers — they flow as continuous HTML within the div, separated only by `(N)` markers.

**Real example (p.28 of جواهر) — 15 footnotes in one div:**

```html
<div class='footnote'>
  (1) القياس مودة بالادغام.</p>
  <font color=#be0000>(2)</font> لوط لازق والاوالس النياق.</p>
  <font color=#be0000>(3)</font> ضرب من القلائد.</p>
  <font color=#be0000>(4)</font> المثعنجر لنمظة متنافر...</p>
  <font color=#be0000>(5)</font> القريض الشعر...</p>
  ...
  <font color=#be0000>(15)</font> هوالك فواعل...
</div>
```

**Parsing strategy:**
1. Unwrap all `<font>` tags (keep text, remove tags).
2. Convert to plain text (strip remaining tags).
3. Split at `(N)` boundaries where N is a digit sequence at the start of a line or preceded by whitespace/newline.
4. For each fragment, extract the number N and the text after the optional dash.

### 6.5 Cross-page footnotes (orphan footnotes)

A footnote reference `(N)` in the matn on page X may correspond to a footnote `(N)` in the footnote section of page X+1. This happens when the editor placed the footnote continuation on the next page.

**Real example (p.171 of جواهر):**

```html
<!-- PAGE 171 matn -->
ما الله إلا خالق كلّ شيءٍ (1)
<!-- PAGE 171 footnotes -->
(1) قصر الموصوف على الصفة في القصر الحقيقي...
(2) فقد قصر الله محمداً على صفة للرسالة...
```

Here footnote (2) has no matching `(2)` reference in the matn of page 171. The reference `(2)` is on page 172's matn (which continues the discussion). This manifests as:
- Page 171: orphan footnote (2) — footnote exists but no ref in matn
- Page 172: orphan ref (2) — ref in matn but no footnote on this page

**Handling:** This is an **informational warning**, not an error. The normalizer reports orphan footnotes and orphan refs. It does NOT attempt to join footnotes across pages — each page is an independent record. Cross-page continuity is a downstream concern.

### 6.6 Exercise numbers vs footnote references

Exercise/تطبيق sections contain numbered items `(1)`, `(2)`, etc. that look identical to footnote references:

```
تطبيق
بين المسند والمسند إليه في الأمثلة التالية:
(1) قال تعالى: {والله يعلم وأنتم لا تعلمون}
(2) قال الشاعر: ...
```

If these are stripped as footnote references, the exercise numbering is destroyed.

**Protection mechanism:** Footnote reference markers `(N)` in the matn are stripped ONLY when a footnote numbered N exists on the same page. If the page has no footnotes (no `<hr width='95'>`), no stripping occurs. If the page has footnotes 1 and 2, only `(1)` and `(2)` in the matn are stripped — `(3)`, `(4)`, etc. survive even if they look like refs.

### 6.7 Non-footnote parenthesized content

Matn text frequently contains Arabic text in parentheses that must NOT be stripped:

```
(في معرفة الفصاحة والبلاغة)    ← section subtitle
(وأخي هارون هو أفصح منِّي لساناً) ← Quran quotation
(أحمد)                          ← example word
```

**Protection mechanism:** The footnote reference regex only matches `(DIGITS)` — digits only, no Arabic letters. `(في معرفة)` cannot match because it contains Arabic letters. This is a simple and complete guard.

### 6.8 Commentary-layer numbered notes (ضياء السالك)

In books with the three-layer `<s0>` structure (see §4.1), the commentary layer (Layer 2) contains numbered notes `(1)`, `(2)`, etc. that look syntactically identical to footnote entries:

**Raw HTML (page 21 of ضياء السالك):**
```html
...كتاب "الخلاصة</p>       ← end of Layer 1 (original text)
<hr><s0>                      ← commentary separator
</p>&nbsp;</p>
<font color=#be0000>(1)</font>  الأرجح: أنه اسم جمع...</p>
<font color=#be0000>(2)</font> جمع أغر من الغرة...</p>
<font color=#be0000>(3)</font> جمع محجل...</p>
...                            ← these look like footnotes but are IN THE MATN AREA
</div>                         ← end of PageText (no <hr width='95'>, no footnote div)
```

**After normalization, these numbered notes appear in `matn_text`:**
```
...كتاب "الخلاصة

(1) الأرجح: أنه اسم جمع، أعرب إعراب الجمع...
(2) جمع أغر من الغرة، وهي بياض في الجبهة...
(3) جمع محجل، وهو من الخيل...
```

**This is correct behavior.** These notes are structurally part of the matn area (they appear before any `<hr width='95'>` separator). The `(N)` markers are NOT stripped because there is no `<div class='footnote'>` with matching numbered entries on these pages. The conditional stripping logic (§10, Step 8i) correctly preserves them.

**How a builder might be confused:** Seeing `(1) text explanation` in the matn output, a builder might think the footnote parser is broken. It is not. These notes are commentary, not footnotes — they are above the footnote separator, not below it. The physical position in the HTML (before vs after `<hr width='95'>`) is the sole determinant.

### 6.9 Alternative footnote prefixes in ضياء السالك

The `<div class='footnote'>` divs in ضياء السالك use non-standard footnote prefixes:

| Prefix | Count (vol 1) | Example |
|--------|-------------:|---------|
| `*` | 132 | `* "كلامنا" مبتدأ ومضاف إليه...` (grammatical analysis) |
| `=` | 11 | `= وجوبًا. "كالشبه" جار ومجرور...` (grammatical analysis) |
| `(N)` | 3 | `(1) هي: سقاية الحجاج` (traditional footnote) |

The current normalizer only parses `(N)` prefixed footnotes. The `*` and `=` prefixed footnotes are included in the `footnotes` field as a single unparsed entry or missed entirely. **This is a known limitation.** A future enhancement could handle these alternative prefixes, but they are confined to one book.

---

## 7. Complete Tag Inventory

Every HTML tag that appears in Shamela exports, with exact handling:

| Tag | Where it appears | Action | Rationale |
|-----|-----------------|--------|-----------|
| `<div class='Main'>` | Document root | Ignore (structural wrapper) | Contains all page blocks |
| `<div class='PageText'>` | Page wrapper | Use as page boundary marker | Split at these to get page blocks |
| `<div class='PageHead'>` | Running header | **Remove entirely** | Print artifact |
| `<span class='PartName'>` | Inside PageHead | Removed with header | Part of header |
| `<span class='PageNumber'>` | Inside PageHead | Extract page number, then remove | `(ص: N)` format |
| `<hr/>` | Inside PageHead | Removed with header | Header decoration |
| `<hr width='95' align='right'>` | Between matn and footnotes | Use as layer separator, then remove | **STRUCTURAL: splits matn/footnotes** |
| `<hr>` | Title page; before `<s0>` in ضياء السالك | Ignore (metadata page) or strip (commentary sep) | Title decoration, or commentary layer boundary (see §4.1) |
| `<div class='footnote'>` | Footnote wrapper | Parse contents as footnotes | Contains all footnotes for this page |
| `</p>` | Everywhere in matn/footnotes | Convert to `\n` | Line break (orphaned closing tag) |
| `<br>` / `<br/>` | Occasional | Convert to `\n` | Line break |
| `<font color=#be0000>` | Matn (numbering) and footnotes (numbers) | **Unwrap** (keep text, remove tag) | Decorative red color |
| `<span class='title'>` | Metadata pages only | Removed with metadata page | Bibliographic labels |
| `<span class='footnote'>` | Metadata pages only (author name) | Removed with metadata page | Author attribution |
| `<span data-type='title'>` | 1 book only (التبيان) | Strip tag, keep text | Section heading |
| `<table dir=rtl>` | 3 books, 5 files | Extract cell text, replace table | Content tables (comparison charts) |
| `<tr>`, `<th>`, `<td>` | Inside tables | Part of table extraction | Table cells |
| `<img src='data:image/...'> ` | 3 books, 5 files | Detect; if image-only page, flag it | Embedded page scans |
| `<sup>` | 11 books, wrapping footnote refs | Strip tag, keep text | Superscript for `(N)` refs: `<sup><font color=#be0000>(N)</font></sup>` |
| `<s0>` | 1 book (ضياء السالك), after `<hr>` | Strip tag (void, unclosed) | Commentary layer separator (see §4.1) |
| `<style>`, `<script>` | Document head | Remove entirely | Presentation/behavior |
| `&nbsp;` | Occasional | Decode to space | HTML entity |
| `&#8204;` | With data-type='title' spans | Decode to U+200C (ZWNJ) | Unicode character |

**Tags NOT present in the corpus** (confirmed across 189,676 pages): `<b>`, `<i>`, `<u>`, `<em>`, `<strong>`, `<a href>`, `<ul>`, `<ol>`, `<li>`, `<blockquote>`, `<pre>`, `<code>`, `<h1>`–`<h6>`, `<span class='quran'>`, `<span class='hadith'>`, any CSS class not listed above.

---

## 8. Real HTML Examples (Before → After)

### 8.1 Normal prose page with footnotes (p.20)

**Raw HTML:**
```html
<div class='PageText'><div class='PageHead'><span class='PartName'>جواهر البلاغة في المعاني والبيان والبديع</span><span class='PageNumber'>(ص: ٢٠)</span><hr/></div>فصاحة الكلمة</p><font color=#be0000>1.</font> خلوصها من تنافر الحروف: لتكون رقيقة عذبة. تخف على اللسان، ولا تثقل على السمع، فلفظ «أسد» أخف من لفظ «فدوكس» .</p><font color=#be0000>2.</font> خلوصها من الغرابة، وتكون مألوفة الاستعمال.</p><font color=#be0000>3.</font> خلوصها من مخالفة القياس الصرفي، حتى لا تكون شاذة.</p><font color=#be0000>4.</font> خلوصها من الكراهة في السمع (1) .</p>أما «تنافر الحروف» ؛ فهو وصف في الكلمة يوجب ثقلها على السمع. وصعوبة أدائها باللسان: بسبب كون حروف الكلمة متقاربة المخارج ـ وهو نوعان:</p><font color=#be0000>1.</font> شديد في الثقل ـ كالظش (للموضع الخشن) ونحو: همخع «لنبت ترعاه الإبل» من قول أعرابي:</p>* تركت ناقتي ترعى الهمخع*</p><font color=#be0000>2.</font> وخفيف في الثقل ـ كالنقنقة «لصوت الضفادع» والنقاخ «للماء العذب الصافي» ونحو: مستشزرات «بمعنى مرتفعات» من قول امرئ القيس يصف شعر ابنة عمه:</p>غدائره مستشزراتٌ إلى العلا تضل العقاص في مُثنَّى ومرسل (2)</p>ولا ضابط لمعرفة الثقل والصعوبة سوى الذوق السليم، والحس الصادق<hr width='95' align='right'><div class='footnote'>(1) ـ ففصاحة الكلمة تكونها من حروف متآلفة يسهل على اللسان نطقها من غير عناء، مع وضوح معناها، وكثرة تداولها بين المتكلمين وموافقتها للقواعد الصرفية ومرجع ذلك الذوق السليم، والالمام بمتن اللغة، وقواعد الصرف ـ وبذلك تسلم مادتها وصيغتها. ومعناها من الخلل ـ واعلم أنه ليس تنافر الحروف يكون موجبه دائما قرب مخارج الحروف. إذ قربها لا يوجبه دائما ـ كما أن تباعدها لا يوجب خفتها ـ فها هي كلمة «بفمي» حسنة، وحروفها من مخرج واحد وهو الشفة، وكلمة «ملع» منتافرة ثقيلة، وحروفها متباعدة المخارج، وأيضاً ليس موجب التنافر طول الكلمة وكثرة حروفها.</p><font color=#be0000>(2)</font> ـ «الغدائر» الضفائر، والضمير يرجع إلى (فرع) في البيت قبله (والاستشراز) الارتفاع (والعقاص) جمع عقيصة وهي الخصلة من الشعر (والثنى) الشعر المفتول (والمرسل) ضده ـ أي ابنة عمه لكثرة شعرها بعضه مرفوع، وبعضه مثنى، وبعضه مرسل، وبعضه معقوص: أي ملوي.</div></div>
```

**Normalization walkthrough:**

1. **Extract page number:** `(ص: ٢٠)` → `page_number_arabic = "٢٠"`, `page_number_int = 20`
2. **Remove running header:** Delete everything from `<div class='PageHead'>` to its closing `</div>` (inclusive).
3. **Split at footnote separator:** Find `<hr width='95' align='right'>`. Everything before = matn HTML. Everything after = footnote HTML.
4. **Parse footnotes FIRST:**
   - Find `<div class='footnote'>` content.
   - First footnote: `(1) ـ ففصاحة الكلمة تكونها...` → number=1, strip `(1) ـ `, text starts at `ففصاحة`.
   - Second footnote: `<font color=#be0000>(2)</font> ـ «الغدائر» الضفائر...` → unwrap font tag → `(2) ـ «الغدائر»...` → number=2, text starts at `«الغدائر»`.
   - Known footnote numbers: {1, 2}.
5. **Clean matn:**
   - Unwrap `<font color=#be0000>` tags: `1.`, `2.`, etc. become plain text.
   - Strip asterisk verse markers: `* تركت ناقتي ترعى الهمخع*` → `تركت ناقتي ترعى الهمخع`
   - Convert `</p>` to `\n`.
   - Strip all remaining HTML tags.
   - Decode HTML entities.
   - Strip footnote refs `(1)` and `(2)` from matn (because footnotes 1 and 2 exist on this page).
   - Normalize whitespace.
6. **Set flags:** `has_verse = true` (hemistich separator `…` absent, but asterisk verse present).

**Normalized output (JSONL record):**
```json
{
  "record_type": "normalized_page",
  "book_id": "jawahir",
  "volume": 1,
  "page_number_arabic": "٢٠",
  "page_number_int": 20,
  "matn_text": "فصاحة الكلمة\n1. خلوصها من تنافر الحروف: لتكون رقيقة عذبة. تخف على اللسان، ولا تثقل على السمع، فلفظ «أسد» أخف من لفظ «فدوكس» .\n2. خلوصها من الغرابة، وتكون مألوفة الاستعمال.\n3. خلوصها من مخالفة القياس الصرفي، حتى لا تكون شاذة.\n4. خلوصها من الكراهة في السمع .\nأما «تنافر الحروف» ؛ فهو وصف في الكلمة يوجب ثقلها على السمع. وصعوبة أدائها باللسان: بسبب كون حروف الكلمة متقاربة المخارج ـ وهو نوعان:\n1. شديد في الثقل ـ كالظش (للموضع الخشن) ونحو: همخع «لنبت ترعاه الإبل» من قول أعرابي:\nتركت ناقتي ترعى الهمخع\n2. وخفيف في الثقل ـ كالنقنقة «لصوت الضفادع» والنقاخ «للماء العذب الصافي» ونحو: مستشزرات «بمعنى مرتفعات» من قول امرئ القيس يصف شعر ابنة عمه:\nغدائره مستشزراتٌ إلى العلا تضل العقاص في مُثنَّى ومرسل\nولا ضابط لمعرفة الثقل والصعوبة سوى الذوق السليم، والحس الصادق",
  "footnotes": [
    {"number": 1, "text": "ففصاحة الكلمة تكونها من حروف متآلفة يسهل على اللسان نطقها من غير عناء، مع وضوح معناها، وكثرة تداولها بين المتكلمين وموافقتها للقواعد الصرفية ومرجع ذلك الذوق السليم، والالمام بمتن اللغة، وقواعد الصرف ـ وبذلك تسلم مادتها وصيغتها. ومعناها من الخلل ـ واعلم أنه ليس تنافر الحروف يكون موجبه دائما قرب مخارج الحروف. إذ قربها لا يوجبه دائما ـ كما أن تباعدها لا يوجب خفتها ـ فها هي كلمة «بفمي» حسنة، وحروفها من مخرج واحد وهو الشفة، وكلمة «ملع» منتافرة ثقيلة، وحروفها متباعدة المخارج، وأيضاً ليس موجب التنافر طول الكلمة وكثرة حروفها."},
    {"number": 2, "text": "«الغدائر» الضفائر، والضمير يرجع إلى (فرع) في البيت قبله (والاستشراز) الارتفاع (والعقاص) جمع عقيصة وهي الخصلة من الشعر (والثنى) الشعر المفتول (والمرسل) ضده ـ أي ابنة عمه لكثرة شعرها بعضه مرفوع، وبعضه مثنى، وبعضه مرسل، وبعضه معقوص: أي ملوي."}
  ],
  "footnote_ref_numbers": [1, 2],
  "has_verse": true,
  "is_image_only": false,
  "has_tables": false,
  "warnings": []
}
```

### 8.2 Page with no footnotes (p.39)

**Raw HTML:**
```html
<div class='PageText'><div class='PageHead'><span class='PartName'>جواهر البلاغة في المعاني والبيان والبديع</span><span class='PageNumber'>(ص: ٣٩)</span><hr/></div>التعبير عن المقصود بكلام فصيح في أيِّ غرضٍ كان.</p>فيكون قادراً بصفة الفصاحة الثابتة في نفسه على صياغة الكلام مُتمكّناً من التّصرف في ضُروبه بصيراً بالخوض في جهاته ومَنَاحِيه.</p>أسئلة على الفصاحة يطلب أجوبتها</p>ما هي الفصاحة لغة واصطلاحا؟ ما الذي يوصف بالفصاحة</p>ما الذي يخرج الكلمة عن كونها فصيحة؟</div>
```

**Key difference:** No `<hr width='95'>`, no `<div class='footnote'>`. After header removal, everything is matn. `footnotes = []`, `footnote_ref_numbers = []`.

### 8.3 Page with table (p.17 of التبيان)

**Raw HTML (abbreviated):**
```html
<div class='PageText'><div class='PageHead'><span class='PartName'>التبيان في قواعد النحو وتقويم اللسان</span><span class='PageNumber'>(ص: ١٧)</span><hr/></div>
&#8204;<span data-type='title' id=toc-16>&#8204;الكلمة وأقسامها</span></p>
الكلمة: هى القول المفرد الدال على معنى...</p>
&#8204;<span data-type='title' id=toc-18>&#8204;الفرق بين الاسم والفعل:</span></p>
<table dir=rtl>
  <tr><th>الاسم </th><th>الفعل </th></tr>
  <tr><td>1 - يدل على الثبات </td><td>1 - يدل علي الحدوث والتجدد </td></tr>
  <tr><td>2 - لا توجد جملة تستغنى عن الاسم </td><td>2 - قد تستغنى الجملة عن الفعل. </td></tr>
  ...
</table>
<hr width='95' align='right'><div class='footnote'><font color=#be0000>(1)</font> سورة طه الآية 71.</div></div>
```

**Table handling:**
- Extract cell text row by row: `الاسم | الفعل` (header row), `1 - يدل على الثبات | 1 - يدل علي الحدوث والتجدد` (data row), etc.
- Join cells with ` | `, rows with `\n`.
- Replace the `<table>...</table>` block in the HTML with the extracted text.
- Set `has_tables = true`.

**Note the `<span data-type='title'>` elements** — these are stripped like all HTML tags, but their text content (`الكلمة وأقسامها`, `الفرق بين الاسم والفعل:`) is preserved.

### 8.4 Image-only page (p.14 of التبيان)

**Raw HTML (base64 truncated):**
```html
<div class='PageText'><div class='PageHead'><span class='PartName'>التبيان في قواعد النحو وتقويم اللسان</span><span class='PageNumber'>(ص: ١٤)</span><hr/></div><img src='data:image/jpg;base64,/9j/4AAQSkZJR...[LARGE BASE64 STRING]...'></div>
```

**Detection:** After removing the header, the only content is an `<img>` tag. No text content remains (< 10 characters after stripping all tags).

**Handling:** Set `is_image_only = true`, `matn_text = ""`, `footnotes = []`. Add warning `"IMAGE_ONLY_PAGE"`.

### 8.5 Orphan footnote page (p.171)

```html
<!-- Matn has ref (1) but NOT (2) -->
ما الله إلا خالق كلّ شيءٍ (1)
<!-- Footnote section has BOTH (1) and (2) -->
(1) قصر الموصوف على الصفة في القصر الحقيقي...
(2) فقد قصر الله محمداً على صفة للرسالة...
```

**Result:** `footnote_ref_numbers = [1]` (only (1) stripped from matn). `footnotes = [{number: 1, ...}, {number: 2, ...}]` (both parsed). Warning: `"Footnotes with no matching ref in matn: [2]"`.

---

## 9. Multi-Volume Books

### 9.1 Directory structure

```
كتاب سيبويه/
├── 001.htm     ← Volume 1
├── 002.htm     ← Volume 2
├── 003.htm     ← Volume 3
└── 004.htm     ← Volume 4
```

Each `.htm` file has the **exact same internal structure** as a single-volume book — full HTML skeleton, metadata pages, then content pages.

### 9.2 Volume number derivation

The volume number is the integer value of the filename stem: `001.htm` → volume 1, `014.htm` → volume 14.

Single-volume books (standalone `.htm` files not in a numbered directory) get `volume = 1`.

### 9.3 Pagination regimes

| Regime | Example | % of multi-vol books | Page number unique within book? |
|--------|---------|---------------------:|:-------------------------------:|
| Continuous | vol1: pp.1–482, vol2: pp.483–1048 | 29% | ✓ Yes |
| Restarted | vol1: pp.1–588, vol2: pp.1–543 | 71% | ✗ No |

**The normalizer does not need to distinguish these.** It records `(volume, page_number_int)` for every page. The compound key is always unique.

Downstream consumers (passage extraction) use the optional `volume_hint` field in the passage config to disambiguate when slicing pages from books with restarted pagination.

### 9.4 Corpus statistics

- 104 multi-volume books in corpus
- Smallest: 2 volumes
- Largest: 138 volumes (شرح ألفية ابن مالك — each "volume" is actually a lesson, 4–39 pages each)
- Largest by page count: تمهيد القواعد — 11 volumes, 5,696 pages, continuous pagination

---

## 10. Step-by-Step Processing Algorithm

This is the complete, ordered procedure for normalizing one Shamela HTML file into JSONL. A builder should implement these steps in this exact order.

### Step 0: Input resolution

If the input is a single `.htm` file, set `volume = 1`. If the input is a directory of numbered files (`001.htm`, `002.htm`, ...), process each file independently with `volume` set to the integer value of the filename stem (`001` → 1, `014` → 14). The rest of the algorithm describes processing one file.

### Step 1: Read the file

Read the entire file as UTF-8. Compute SHA-256 hash of the raw bytes for provenance tracking.

### Step 2: Split into page blocks

Find all occurrences of the string `<div class='PageText'>`. For each occurrence at position `i`, the page block runs from position `i` to the start of the next `<div class='PageText'>` (or end of file for the last block).

**Do NOT use regex to match `<div class='PageText'>...</div>`** — the nested `<div class='footnote'>` inside will cause premature matching. Split by start positions only.

### Step 3: For each page block, extract or skip

For each block, search for the page number pattern `(ص: N)` where N is Arabic-Indic digits. Use the regex: `\(ص:\s*([٠-٩]+)\s*\)`

If no match is found, this is a metadata/title page. **Skip it.** Record it in `pages_skipped` for the report.

If a match is found, convert the Arabic-Indic digit string to an integer (٠→0, ١→1, ... ٩→9) and store as `page_number_arabic` (the original string) and `page_number_int` (the integer).

### Step 4: Detect image-only pages

After extracting the page number, check if the page is an embedded scan. Remove the `<div class='PageHead'>...</div>` header, remove all `<img>` tags, and strip all remaining HTML tags. If the remaining text content is fewer than 10 characters, this is an image-only page.

For image-only pages: emit a record with `is_image_only = true`, `matn_text = ""`, `footnotes = []`, and a warning `"IMAGE_ONLY_PAGE"`. **Skip all remaining steps for this page.**

### Step 5: Remove running header

Remove everything matching `<div class='PageHead'>.*?</div>` (with DOTALL flag for the regex). This removes the book title, page number, and decorative `<hr/>` in one operation.

### Step 6: Split into layers (matn vs footnotes)

Search for the footnote separator `<hr width='95'` (regex: `<hr\s+width='95'[^>]*>`).

If found: everything before the separator is **matn HTML**. Everything after is **footnote HTML**.

If not found: the entire remaining content is matn HTML. Footnote HTML is empty.

### Step 7: Parse footnotes FIRST

This must happen before cleaning the matn, because the set of known footnote numbers is needed for step 8.

From the footnote HTML, extract the content of `<div class='footnote'>...</div>`. If no such div exists (or footnote HTML is empty), `footnotes = []` and `known_fn_numbers = {}`.

To parse the footnote div content into individual entries:

**7a.** Unwrap all `<font color=#be0000>` tags (keep the text content, remove the tag).

**7b.** Convert to plain text: strip all remaining HTML tags, decode HTML entities.

**7c.** Split at `(N)` boundaries. Each `(N)` (where N is a digit sequence) at the start of the text or after a line break marks the start of a new footnote. The text before the first `(N)` (if any) is ignored or attached to a previous footnote.

**7d.** For each footnote, extract the number N and the text. Strip the optional dash separator after `(N)`:
- `(N) ـ text` → strip `(N) ـ `, text starts at first non-whitespace after dash
- `(N) text` → strip `(N) `, text starts at first non-whitespace
- The dash character can be `ـ` (U+0640), `-` (U+002D), or `–` (U+2013)

**7e.** Record `known_fn_numbers = {1, 2, ...}` — the set of footnote numbers found.

### Step 8: Clean matn text

**8a. Replace tables:** Find all `<table>...</table>` blocks. For each, extract cell text row by row (cells joined with ` | `, rows joined with `\n`). Replace the `<table>...</table>` block in the HTML with the extracted text. Record `has_tables = true` if any tables were found.

**8b. Remove images:** Strip any `<img>` tags from the matn HTML (for mixed text+image pages).

**8c. Detect verse:** Before stripping tags, check if the text content contains the hemistich separator `…` (U+2026) or asterisk-wrapped verses `* text *`. Set `has_verse = true` if either is found.

**8d. Unwrap font tags:** Replace `<font color=#be0000>TEXT</font>` with just `TEXT`.

**8e. Convert block-level breaks:** Replace `</p>` with `\n`. Replace `<br>` / `<br/>` with `\n`.

**8f. Strip remaining tags:** Remove all content matching `<[^>]+>`.

**8g. Decode HTML entities:** Convert `&amp;` → `&`, `&nbsp;` → space, `&#8204;` → U+200C, etc.

**8h. Clean verse markers:** Replace `* text *` with `text` (strip asterisks).

**8i. Strip footnote references:** For each `(N)` pattern in the text (where N is digits only), strip it **only if** N is in `known_fn_numbers` from step 7e. This is the critical guard against stripping exercise numbers, verse references, or commentary-layer notes. Record the list of stripped reference numbers as `footnote_ref_numbers`.

**8j. Normalize whitespace:**
- `\r\n` and `\r` → `\n`
- U+00A0 (non-breaking space) → regular space
- Collapse multiple spaces within each line to single space
- Trim each line (remove leading/trailing whitespace)
- Collapse 3+ consecutive blank lines to 1 blank line
- Trim the entire result

### Step 9: Cross-reference validation

Compare `footnote_ref_numbers` (from step 8i) against `known_fn_numbers` (from step 7e).

Orphan refs = refs in matn with no matching footnote entry. Orphan footnotes = footnote entries with no matching ref in matn. Both are recorded as warnings. Orphan footnotes are common and expected (cross-page continuity, see §6.5).

### Step 10: Emit JSONL record

Assemble the final record:

```json
{
  "record_type": "normalized_page",
  "book_id": "<from CLI>",
  "volume": "<from step 0>",
  "page_number_arabic": "<from step 3>",
  "page_number_int": "<from step 3>",
  "matn_text": "<from step 8>",
  "footnotes": [{"number": N, "text": "..."}],
  "footnote_ref_numbers": [1, 2],
  "has_verse": "<from step 8c>",
  "is_image_only": false,
  "has_tables": "<from step 8a>",
  "warnings": ["<any warnings from steps 4–9>"]
}
```

Write as one JSON line per page, in document order (the order pages appear in the HTML), to the output JSONL file.

---

## 11. What the Normalizer Does NOT Do

These are explicitly out of scope. A builder must not implement these:

1. **Heading detection** — whether a line is a section title vs body text is an atomization decision.
2. **Cross-page joining** — text that flows across page boundaries stays separated. Each page is an independent JSONL record.
3. **Spelling/diacritic correction** — preserve the author's text byte-for-byte after tag stripping.
4. **Unicode normalization** — no NFC/NFD conversion. Preserve codepoints as-is.
5. **Footnote cross-page linking** — orphan footnotes are warned about, not resolved.
6. **Continuous vs restarted pagination detection** — just record volume + page number.
7. **OCR of image pages** — image-only pages are flagged as empty.
8. **Anything involving an LLM** — normalization is fully deterministic.
