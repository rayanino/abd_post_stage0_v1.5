# Stage 0: Book Intake — Specification

**Status:** Finalized (fifth review pass — prototype parser, schema stress tests, builder ambiguity audit)
**Version:** 1.4
**Precision level:** High

---

## 1. Purpose

Create an immutable anchor for everything downstream. After intake, the source HTML is frozen and all subsequent stages trace back to this snapshot. Metadata is extracted and validated. The book is registered in the project.

**Repo root** is the directory containing `books/`, `schemas/`, `tools/`, and `taxonomy/`. All `relpath` values throughout the pipeline are relative to this root.

---

## 2. Input

| Input | Source | Required |
|-------|--------|----------|
| Source path | Positional CLI argument | Yes |
| Book ID | `--book-id` | Yes |
| Primary science | `--science` (`balagha`, `sarf`, `nahw`, `imlaa`, `unrelated`, or `multi`) | Yes |
| Science parts file | `--science-parts` (YAML file) | Only when `--science multi` |
| Edition notes | `--notes` | No |
| Force flag | `--force` | No |
| Non-interactive | `--non-interactive` | No |
| Dry run | `--dry-run` | No |

**Source path** is either:
- A single `.htm` file (single-volume Shamela export)
- A directory containing `.htm` files (multi-volume Shamela export — folder is named by book, volume files are numbered `001.htm`, `002.htm`, etc.)

**Primary science** is the user's expectation of the book's primary science. This is an **informational prior, not a routing constraint.** Any excerpt from any book can land in any science's taxonomy tree — excerpt science is determined by content at Stage 4, not by the book's declared science at Stage 0.

- `balagha`, `sarf`, `nahw`, `imlaa` — one of the four sciences
- `unrelated` — book is outside our four sciences but may contain relevant passages
- `multi` — book covers multiple sciences (requires `--science-parts`)

**Book ID** — see §3.1 for validation rules.

**Science parts file** — required when `--science multi`, forbidden otherwise. A YAML file mapping book sections to sciences. Format:
```yaml
- section: "القسم الأول"
  science_id: sarf
  description: "علم الصرف والاشتقاق"
- section: "القسم الثاني"
  science_id: nahw
  description: "علم النحو"
```
Must be a YAML array of objects, each with `section` (string), `science_id` (one of `balagha`, `sarf`, `nahw`, `imlaa`), and `description` (string).

**Edition notes** — optional free-text describing the edition, genre, or any relevant context (e.g., `"ت شاكر edition"`, `"modern textbook"`, `"classical prose treatise"`). Stored in metadata for traceability.

**`--force`** — bypasses the duplicate SHA-256 check (EC-I.5). Use when intentionally re-ingesting the same source file under a different book ID.

**`--non-interactive`** — skips all confirmation prompts. Soft confirmations (low/medium-reliability القسم, `unrelated`/`multi` acknowledgment, truncation warnings) auto-accept the user's declaration. Hard confirmations (high-reliability القسم mismatch, supplementary file decisions) cause the tool to exit with a non-zero error code. See §3.6 for the classification of each confirmation.

**`--dry-run`** — runs all validation, duplicate detection, and metadata extraction, prints what would be created (directory structure, metadata, registry entry), but writes nothing to disk. All steps through §3.8 execute normally; only §3.4 (file copying) and §3.9 (writing outputs) are skipped.

**Interaction model:** The intake tool is a CLI script with interactive prompts via `stdin`. All prompts require explicit `y` / `n` response (or free text where noted). No auto-confirm defaults.

**Example invocations:**
```bash
# Single-volume, single science
python tools/intake.py books/sources/shadha_al_arf.htm \
  --book-id shadha --science sarf --notes "Modern textbook"

# Multi-volume
python tools/intake.py books/sources/sharh_ibn_aqil/ \
  --book-id ibn_aqil --science nahw \
  --notes "4-volume commentary. Vols 1-2 have footnotes, vols 3-4 do not."

# Multi-science with parts file
python tools/intake.py books/sources/miftah_al_ulum.htm \
  --book-id miftah --science multi --science-parts miftah_parts.yaml

# Book with supplementary file
python tools/intake.py books/sources/dalail_al_ijaz/ \
  --book-id dalail --science balagha

# Dry run
python tools/intake.py books/sources/jawahir_al_balagha.htm \
  --book-id jawahir --science balagha --dry-run
```

---

## 3. Operations (in order)

### 3.0 CLI and path validation

Before any pipeline operations begin, validate CLI arguments and resolve paths:

1. **Source path existence:** Verify that the positional source path argument exists on disk (file or directory). If not: abort with `"Source path '{path}' does not exist."`.

2. **Flag consistency:**
   - If `--science multi` without `--science-parts`: abort with `"--science-parts is required when --science is 'multi'."`
   - If `--science-parts` provided without `--science multi`: abort with `"--science-parts is only allowed when --science is 'multi'. You passed --science '{value}'."`
   - Validate the `--science-parts` YAML file: must exist, must be valid YAML, must be a list, each item must have `section`, `science_id`, and `description`. If invalid: abort with specific error.

3. **Resolve paths:** Normalize the source path to an absolute path. All subsequent operations use this resolved path.

### 3.1 Book ID validation

**Book ID** is a short ASCII identifier provided by the user via `--book-id` (required).

**Rules:**
- Must match `^[a-z][a-z_]*[a-z]$` (starts and ends with a lowercase letter; only lowercase letters and underscores in between)
- 3–40 characters
- Must be unique in `books_registry.yaml`
- Convention: short transliterated name of the book (e.g., `jawahir`, `shadha`, `qatr`)

No auto-generation is attempted. The user knows their books and picks meaningful short names.

**Validation:** If the provided `--book-id` fails any rule, the tool **aborts with a specific error message**. It never silently truncates, transforms, or overwrites.

Error messages:
- `"Book ID '{x}' contains invalid characters. Must match [a-z][a-z_]*[a-z] (start and end with a letter, only lowercase letters and underscores)."`
- `"Book ID '{x}' is {n} characters. Must be 3–40."`
- `"Book ID '{x}' already exists in the registry (book: {title}). Choose a different ID."`

### 3.2 Source validation

**Encoding:** All HTML files are opened as UTF-8. If a file fails to decode as UTF-8, abort with error: `"File {filename} is not valid UTF-8. Shamela exports are expected to be UTF-8."` Note: all observed Shamela exports use CRLF (`\r\n`) line endings and contain no BOM.

**HTML parsing:** Use regex for metadata card extraction. The metadata card is a flat list of `<span>` elements with simple structure — no nested HTML requiring a full DOM parser. This matches the approach used by the normalizer (`tools/normalize_shamela.py`).

**Regex safety note:** The metadata card (first `PageText` div) never contains nested `<div>` elements, so `<div class='PageText'>(.*?)</div>` with `re.DOTALL` correctly captures the full card. This has been verified on all 11 source files. However, content pages DO contain nested `<div class='PageHead'>` inside `<div class='PageText'>` — this regex approach must NOT be used for content page extraction (the normalizer uses a start-to-start splitting strategy instead). This only affects Stage 1, not intake.

**Single-file input:** Run all checks on that file.

**Directory input:** Classify files in the directory:
- **Numbered `.htm` files** (numeric stems: `001.htm`, `002.htm`, etc.) → volume candidates
- **Non-numbered `.htm` files** (e.g., `muqaddima.htm`) → supplementary candidates. Prompt user: `"Found non-numbered file(s): {filenames}. Include as supplementary? [y/n]"`. If yes, for each file prompt: `"Brief description for {filename}: "` (free-text stdin line, stored as `file_note`). **Hard confirmation** — in `--non-interactive` mode, exit with error: `"Non-numbered files found but --non-interactive cannot make supplementary file decisions."`
- **Non-`.htm` files** → silently skipped.

**Directory classification:**
- 2+ numbered `.htm` files → multi-volume. Each numbered file gets `role: "volume"`. Volume numbers are derived from the numeric filename stems, sorted numerically (not lexicographically). Gaps are allowed (e.g., `001.htm`, `003.htm` without `002.htm`) — volume numbers reflect the filenames, not a contiguous sequence. Log a warning if gaps exist.
- Exactly 1 numbered `.htm` file → single-volume. The numbered file gets `role: "primary_export"` (not "volume 1 of 1"). See EC-I.12.
- 0 numbered `.htm` files → abort: `"No numbered .htm files found in directory."`

**Validation checks** (applied to every `.htm` file that will be ingested — primary_export, volume, and supplementary):

| Check | Rule | On failure |
|-------|------|------------|
| File is HTML | Must contain `<html` opening tag | Abort with error identifying the file |
| Is Shamela format | Must contain `<div class='Main'>` AND `<div class='PageText'>` | Abort with error identifying the file |
| Has page markers | Must contain at least one `<span class='PageNumber'>` | Abort with error identifying the file |

**Page counting:** During validation, count `<span class='PageNumber'>` elements in each file. Store as `actual_page_count` per file.

**Important:** Count `PageNumber` spans, NOT `PageText` divs. Not all `PageText` divs represent content pages — some are metadata cards, volume title pages, or mid-book section dividers that contain only the book title with no page number. For example, jawahir has 312 `PageText` divs but only 308 `PageNumber` spans. The difference (4) is 1 metadata card, 1 title page, and 2 section dividers between parts. This discrepancy exists in every file to varying degrees.

### 3.3 Duplicate detection

Compute SHA-256 hash of each source file. Check every hash against `source_hashes` across all existing entries in `books_registry.yaml`.

**Registry bootstrap:** If `books_registry.yaml` does not exist yet (first intake ever), skip the duplicate check entirely — there are no existing entries to conflict with. The file will be created in §3.9.

**File-level check:** A duplicate is detected when any single source file's SHA-256 matches any hash in any existing book's `source_hashes`. This is per-file, not per-book — re-ingesting one volume of a multi-volume book under a different book ID triggers it.

**Intra-intake check:** If the same intake includes multiple files (directory input), warn if any two files have identical SHA-256 hashes: `"Warning: files {A} and {B} have identical content (SHA-256: {hash})."` This is a warning only, not an abort — duplicate volumes can theoretically exist in a Shamela export.

If an inter-book match is found:
- Without `--force`: abort with `"File {filename} (SHA-256: {hash}) was already intaken as book '{existing_book_id}'. Use --force to create a separate intake."`
- With `--force`: log warning and proceed.

### 3.4 Source freezing

1. Create directory `books/{book_id}/source/`.
2. Copy the source file(s), **preserving original filenames**.
   - Single-file input: the `.htm` file is copied as-is.
   - Directory input: numbered files and any accepted supplementary files are copied. No wrapping subdirectory — files go directly into `source/`.
3. Set the `source/` directory to read-only.

**Immutability rule:** Once frozen, the source is NEVER modified. If the user provides a corrected file, a new book intake is required (new `book_id` or versioned source).

### 3.5 Metadata extraction

Shamela exports embed metadata in the **first `PageText` div** (before any content page with a page number). The app parses this structured card.

For directory input, the metadata card is read from:
- The `primary_export` file (if present), OR
- The lowest-numbered `volume` file (by numeric sort order)
- Never from `supplementary` files.

**Multi-volume note:** All volumes of a multi-volume book contain identical metadata cards (verified on ibn_aqil — all 4 volumes produce the same metadata). Extracting from any volume would yield the same result, but we canonically use the first for determinism.

#### 3.5.1 HTML structure of the metadata card

The metadata card is the first `<div class='PageText'>` in the file. It contains:

```html
<span class='title'>TITLE&nbsp;&nbsp;&nbsp;</span>
<span class='footnote'>(AUTHOR_SHORT)</span>
<p>
<span class='title'>القسم:</span> VALUE<hr>
<p>
<span class='title'>LABEL<font color=#be0000>:</font></span> VALUE
<p>
...more label:value segments...
```

**Key structural facts (validated against all 7 books):**

1. **Title span** comes first, followed immediately by a `<span class='footnote'>` containing the short author name in parentheses. The title span ends with `&nbsp;&nbsp;&nbsp;` (3 non-breaking spaces). The footnote span is NOT inside the title span — it's a separate sibling element.

2. **القسم is special.** It's the only field where the colon is a plain `:` character baked into the span text. All other fields use `<font color=#be0000>:</font>` (red-colored colon) as the separator.

3. **An `<hr>` tag** follows the القسم value (and only القسم). All other fields are separated by `<p>` tags.

4. **Red `<font>` tags** wrap ALL punctuation in the card — not just colons. Observed characters: `:` `,` `(` `)` `[` `]` `.` `-`. This means literal punctuation characters rarely appear in raw HTML; they're almost always wrapped in `<font color=#be0000>...</font>`.

5. **Values can be partially inside the span tag.** In most books, the label is inside `<span class='title'>` and the value follows `</span>`. But in ibn_aqil's المؤلف field, most of the value is inside the span alongside the label, with only the last fragment (`769 هـ)`) after the closing `</span>`. The parsing algorithm must handle both cases.

#### 3.5.2 Parsing algorithm

**Step 1 — Segment extraction.** Find all segments of the form:

```
<span class='title'>SPAN_CONTENT</span>TRAILING_CONTENT
```

Where `TRAILING_CONTENT` is everything after `</span>` up to the next `<span class='title'>` or end of the metadata card. Each segment is the concatenation of `SPAN_CONTENT + TRAILING_CONTENT`.

Note: The `<span class='footnote'>` after the title span is NOT a `<span class='title'>`, so it falls into the trailing content of the first segment. This is correct — the footnote span's content `(AUTHOR_SHORT)` becomes part of the first segment's trailing, from which `shamela_author_short` is extracted.

**Step 2 — Text normalization per segment.** For each segment:
1. Strip all HTML tags (including `<font>`, `<p>`, `<hr>`, `<span class='footnote'>`, etc.)
2. Replace `&nbsp;` and `\xa0` with space
3. Collapse multiple whitespace to single space
4. Trim leading/trailing whitespace

**Step 3 — Title extraction (first segment only).** The first segment is always the title. It has no colon.
- `title` = text content of the first `<span class='title'>` (with HTML stripped and `&nbsp;` removed)
- `shamela_author_short`: Extract from the `<span class='footnote'>` in the trailing content. Match `<span class='footnote'>\(([^)]+)\)</span>` on the raw trailing HTML, before stripping tags. Present in all 7 observed books.

**Step 4 — Field extraction (remaining segments).** For each subsequent segment:
1. Concatenate SPAN_CONTENT + TRAILING_CONTENT, strip HTML tags, normalize text (as Step 2)
2. Split on the first colon (`:`) → `label` (before), `value` (after)
3. Trim both `label` and `value`
4. Match `label` against the known field patterns below (**ordered, first match wins**):

| Priority | Label pattern | Match type | Target field | Parse method |
|----------|--------------|------------|--------------|--------------|
| 1 | `القسم` | exact | `html_qism_field` | string |
| 2 | `الكتاب` | exact | `title_formal` | string |
| 3 | `المؤلف` | exact | `author` | string |
| 4 | `دراسة وتحقيق` | contains | `muhaqiq` | string |
| 5 | `المحقق` | contains | `muhaqiq` | string |
| 6 | `تحقيق` | contains | `muhaqiq` | string |
| 7 | `ضبط` | contains | `muhaqiq` | string |
| 8 | `إعداد` | contains | `muhaqiq` | string |
| 9 | `تخريج` | contains | `muhaqiq` | string |
| 10 | `علق` | contains | `muhaqiq` | string |
| 11 | `الناشر` | exact | `publisher` | string |
| 12 | `الطبعة` | exact | `shamela_edition` | string |
| 13 | `عدد الصفحات` | exact | `shamela_page_count` | leading digits (see below) |
| 14 | `عدد الأجزاء` | exact | `shamela_volume_count` | leading digits (see below) |
| 15 | `عام النشر` | exact | `publication_year` | string |
| 16 | `تاريخ النشر بالشاملة` | exact | `shamela_pub_date` | string |

5. If no pattern matches → append the full segment text to `unrecognized_metadata_lines`.

**Muhaqiq matching is ordered and first-match-wins.** This is critical because labels can match multiple patterns. For example, `ضبطه وكتب هوامشه وعلق عليه` matches both `ضبط` (priority 7) and `علق` (priority 10). First match at priority 7 wins. `دراسة وتحقيق` (priority 4) is checked before `تحقيق` (priority 6) to prevent false substring matches.

**Leading-digit parsing** for `shamela_page_count` and `shamela_volume_count`: Extract via regex `^(\d+)` from the value string. Shamela appends annotations directly to the number with no separator, e.g., `344[ترقيم الكتاب موافق للمطبوع]` or `80أعده للمكتبة الشاملة...`. A simple `int()` will crash on every book in the corpus. If no leading digits found, set to null and log warning.

**Trailing annotation in page count values:** After extracting the leading digits, the remaining text in the value is discarded. In 6/7 books, this includes the `[ترقيم الكتاب موافق للمطبوع]` annotation (meaning "book numbering matches the printed edition"). In imla, it also includes a preparer attribution (`أعده للمكتبة الشاملة/ أبو ياسر الجزائري`). These annotations are low-value for our pipeline and are not separately captured. In ibn_aqil, the `[ترقيم...]` annotation is a separate segment (wrapped in its own `<span class='title'>`) and goes to `unrecognized_metadata_lines` — this is the one case where it IS preserved.

**Important note on value location:** In most books, the value follows the `</span>` closing tag (in the trailing content). However, in some books (observed in ibn_aqil), the value is partially or fully **inside the `<span>` tag itself** alongside the label. The algorithm handles both cases by concatenating SPAN_CONTENT + TRAILING_CONTENT before splitting on the first colon. This produces the correct result regardless of where the value falls relative to the span boundary.

**Floating annotation stripping:** Shamela inserts book-level annotations (e.g., `[ترقيم الكتاب موافق للمطبوع]`, `[الكتاب مرقم آليا]`, `[الكتاب مرقم آليا غير موافق للمطبوع]`) as bare HTML between `<span class='title'>` segments. Because they are not wrapped in their own title span, the segment regex attaches them to the **trailing content of the preceding segment**, polluting that field's value. The parser strips these annotations when they appear as a suffix of an otherwise-meaningful segment. Specifically:
- After constructing the full text for each segment, check for a trailing match of `\[(?:ترقيم الكتاب|الكتاب مرقم)[^\]]*\]` at the end.
- If found **and** there is real content before it, strip the annotation.
- If the annotation **is** the entire segment (as in ibn_aqil, where it has its own `<span class='title'>`), do not strip — let it flow through to `unrecognized_metadata_lines` for data preservation.
This has been validated on 18 files: 7 original corpus + 11 stress-test books covering all annotation positions (after page count, edition, author, muhaqiq fields, and as standalone segments).

**Edge case — missing fields:** Not all fields are guaranteed present. `title` is required (abort if missing). All others default to null with a warning.

#### 3.5.3 Known metadata fields across corpus

Validated against all 7 project books:

| Field | Frequency | Target | Notes |
|-------|-----------|--------|-------|
| Title (first span) | 7/7 | `title` | Always present |
| Footnote (author short) | 7/7 | `shamela_author_short` | In `<span class='footnote'>` after title |
| القسم | 7/7 | `html_qism_field` | Only field with plain colon |
| الكتاب | 7/7 | `title_formal` | Often more accurate than title span |
| المؤلف | 7/7 | `author` | |
| الناشر | 7/7 | `publisher` | |
| تاريخ النشر بالشاملة | 7/7 | `shamela_pub_date` | |
| عدد الصفحات | 6/7 | `shamela_page_count` | Absent in ibn_aqil (has عدد الأجزاء instead) |
| الطبعة | 4/7 | `shamela_edition` | |
| المحقق / muhaqiq variants | 6/7 | `muhaqiq` | 7 known label variants |
| عدد الأجزاء | 1/7 | `shamela_volume_count` | Only ibn_aqil |
| عام النشر | 1/7 | `publication_year` | Only imla |
| طبع | 1/7 | → `unrecognized` | Only qatr. "Printer" — distinct from publisher. |
| [ترقيم... | 1/7 | → `unrecognized` | Only ibn_aqil has this as a separate segment |

The 7 muhaqiq label variants remain **known, not exhaustive** — the broader 1,046-file corpus may contain additional variants. The catch-all ensures zero data loss at the segment level: any metadata card segment whose label does not match a known pattern is preserved in full.

#### 3.5.4 Title fields: `title` vs `title_formal`

Two title-related fields exist because Shamela provides the book name in two places with potentially different values:

- **`title`** — from the first `<span class='title'>` in the metadata card. This is Shamela's display name. May contain shorthand like editor markers (e.g., `دلائل الإعجاز ت شاكر`).
- **`title_formal`** — from the `الكتاب:` field. This is the book's proper name (e.g., `دلائل الإعجاز في علم المعاني`). More accurate for formal references. Null if absent.

Downstream stages should prefer `title_formal` when available, falling back to `title`.

### 3.6 Science validation

Cross-reference the user's primary science declaration against the HTML's القسم field.

**Critical finding (from كتب اللغة corpus, 79 books):** The القسم field is often a **Shamela library section name**, not a science classification. For example, all 79 books in the كتب اللغة collection have القسم: "كتب اللغة" — which tells us nothing about whether the book is صرف, نحو, بلاغة, or إملاء.

**Important:** The `primary_science` field records the user's declaration after confirmation. It is informational — it does not constrain excerpt routing. See §2 for the full rationale.

**القسم reliability tiers:**

| القسم value | Reliability | Action |
|-------------|------------|--------|
| `البلاغة` | High — directly maps to a science | Auto-confirm if user declaration matches |
| `النحو والصرف` | Medium — maps to two sciences | User must specify which |
| `الصرف` | High | Auto-confirm |
| `النحو` | High | Auto-confirm |
| `كتب اللغة` | Low — broad category, not science-specific | User declaration is sole authority |
| `أصول الفقه`, `العقيدة`, etc. | Low — outside our sciences entirely | If user declares one of our 4, confirm: "القسم says X. You declared Y. Confirm?" |
| Any other | Unknown | Log and ask user to confirm |

**Decision matrix with `--non-interactive` behavior:**

| User declaration | القسم reliability | Interactive action | `--non-interactive` |
|------------------|-------------------|-------------------|---------------------|
| Any | High + matches | Auto-confirm | Auto-confirm |
| `sarf` or `nahw` | Medium (النحو والصرف) | Confirm | **Soft** — auto-accept user declaration |
| Any of our 4 | Low (كتب اللغة, etc.) | Accept, log | Accept, log |
| Any of our 4 | High + doesn't match | Warn + confirm | **Hard** — exit with error |
| Any of our 4 | Unknown | Ask + confirm | **Soft** — auto-accept user declaration |
| `unrelated` | Any | Confirm acknowledgment | **Soft** — auto-accept |
| `multi` | Any | Confirm acknowledgment | **Soft** — auto-accept |

**Rationale for hard vs soft:** A high-reliability القسم directly contradicting the user (e.g., user says بلاغة, القسم says النحو) is likely a real mistake that requires attention. All other cases are low-stakes — the user's declaration is probably correct and the القسم is just uninformative.

### 3.7 Book category determination

Based on the science declaration:

| Category | Condition | `primary_science` value |
|----------|-----------|------------------------|
| `single_science` | User declares one of our 4 sciences | The declared science |
| `multi_science` | User declares `multi` | `null` (no single primary science) |
| `tangentially_relevant` | User declares `unrelated` | `null` (not about our sciences) |

**Note on `multi_science`:** For books like مفتاح العلوم (صرف + نحو + بلاغة), the user provides `science_parts` via `--science-parts`. This is informational and helps orient downstream stages, but does not constrain excerpt routing.

### 3.8 Taxonomy snapshot

Snapshot **all active taxonomy versions** from `taxonomy/taxonomy_registry.yaml` and record them in `taxonomy_at_intake`. This applies to every book regardless of category, because any excerpt from any book can land in any science's tree.

**Missing registry:** If `taxonomy/taxonomy_registry.yaml` does not exist or is empty, set `taxonomy_at_intake` to `{}` (empty object) and log warning: `"No taxonomy registry found. taxonomy_at_intake will be empty."`. Intake proceeds — the snapshot records whatever exists. This is expected during early project setup before any taxonomy trees are created.

If a science has no taxonomy tree in the registry, this is a project-level blocker (not an intake error). Log: `"No active taxonomy for {science_id}. Taxonomy must be created before excerpting can begin for this science."` Intake proceeds — the snapshot records whatever exists.

### 3.9 Write outputs

1. Write `intake_metadata.json` to `books/{book_id}/intake_metadata.json`. This file is immutable after creation — like the frozen source, it is never modified. If metadata needs to be corrected, a new intake is required.

2. Update `books/books_registry.yaml`:
   - If the file does not exist (first intake): create it with the standard header (`registry_version`, `notes`) and the `books` list containing the new entry.
   - If the file exists: load the full file, add the new entry to the `books` list in memory, write the complete file atomically (write to a temporary file in the same directory, then rename to `books_registry.yaml`). This prevents corruption from partial writes or crashes.
   - **YAML nullable fields:** Omit fields that are null rather than writing `field: null`. This keeps the registry clean and readable. For example, a book with no muhaqiq simply has no `muhaqiq` key in its registry entry.

**Atomic operation guarantee:** If any step in §3.0–§3.9 fails, the tool removes the entire `books/{book_id}/` directory (if partially created) and does NOT update the registry. Intake either completes fully or leaves no trace. The tool logs the failure reason before cleanup.

---

## 4. Output artifacts

### 4.1 Directory structure

```
books/{book_id}/
├── source/                         # Frozen source (immutable after creation)
│   └── jawahir_al_balagha.htm      # Single-volume: original filename
│
│   (or for multi-volume:)
│   ├── 001.htm
│   ├── 002.htm
│   ├── 003.htm
│   └── 004.htm
│
└── intake_metadata.json            # All extracted and validated metadata
```

**Migration note:** The 7 books currently in `books/sources/` were registered before this spec was finalized and use a flat shared layout. When the intake tool is built, it will create per-book directories as specified here. Existing books can be migrated incrementally or left as-is — the registry's `relpath` field is an explicit path that works regardless of directory convention.

### 4.2 `intake_metadata.json`

Validated against `schemas/intake_metadata_schema_v0.1.json`.

All hash values, file sizes, and page counts in the examples below are **verified against the actual source files** in this repository.

**Example 1 — single-volume, single-science book (jawahir):**

```json
{
  "schema_version": "intake_metadata_v0.1",
  "book_id": "jawahir",
  "title": "جواهر البلاغة في المعاني والبيان والبديع",
  "title_formal": "جواهر البلاغة في المعاني والبيان والبديع",
  "shamela_author_short": "أحمد الهاشمي",
  "author": "أحمد بن إبراهيم بن مصطفى الهاشمي (ت 1362هـ)",
  "muhaqiq": "د. يوسف الصميلي",
  "publisher": "المكتبة العصرية، بيروت",
  "shamela_page_count": 344,
  "shamela_edition": null,
  "shamela_volume_count": null,
  "publication_year": null,
  "html_qism_field": "البلاغة",
  "shamela_pub_date": "8 ذو الحجة 1431",
  "primary_science": "balagha",
  "book_category": "single_science",
  "science_parts": null,
  "volume_count": 1,
  "total_actual_pages": 308,
  "source_files": [
    {
      "relpath": "books/jawahir/source/jawahir_al_balagha.htm",
      "sha256": "a4bb8979d8428daf61f88021d6548ad38dc827916aef28589aae6ef9dd6d1ec7",
      "size_bytes": 1045269,
      "role": "primary_export",
      "volume_number": null,
      "actual_page_count": 308,
      "file_note": null
    }
  ],
  "unrecognized_metadata_lines": [],
  "edition_notes": "Shamela desktop HTML export. Modern textbook (بلاغة). Gold baselines exist for pp. 19-40.",
  "language": "ar",
  "intake_utc": "2026-02-25T12:00:00Z",
  "taxonomy_at_intake": {
    "balagha": "balagha_v0_4",
    "sarf": "sarf_v0_1",
    "nahw": "nahw_v0_1",
    "imlaa": "imlaa_v0_1"
  }
}
```

**Example 2 — multi-volume book (ibn_aqil):**

```json
{
  "schema_version": "intake_metadata_v0.1",
  "book_id": "ibn_aqil",
  "title": "شرح ابن عقيل على ألفية ابن مالك",
  "title_formal": "شرح ابن عقيل على ألفية ابن مالك",
  "shamela_author_short": "ابن عقيل",
  "author": "ابن عقيل، عبد الله بن عبد الرحمن العقيلي الهمداني المصري (المتوفى: 769 هـ)",
  "muhaqiq": "محمد محيي الدين عبد الحميد [ت 1392 هـ]",
  "publisher": "دار التراث - القاهرة، دار مصر للطباعة، سعيد جودة السحار وشركاه",
  "shamela_page_count": null,
  "shamela_edition": "العشرون 1400 هـ - 1980 م",
  "shamela_volume_count": 4,
  "publication_year": null,
  "html_qism_field": "النحو والصرف",
  "shamela_pub_date": "8 ذو الحجة 1431",
  "primary_science": "nahw",
  "book_category": "single_science",
  "science_parts": null,
  "volume_count": 4,
  "total_actual_pages": 1328,
  "source_files": [
    {
      "relpath": "books/ibn_aqil/source/001.htm",
      "sha256": "13f42287d1eb179d769e311193de6b000b12873160aa88e4dbb03344b6c7d6d0",
      "size_bytes": 1151587,
      "role": "volume",
      "volume_number": 1,
      "actual_page_count": 390,
      "file_note": null
    },
    {
      "relpath": "books/ibn_aqil/source/002.htm",
      "sha256": "a567e3784f60703c4c2154ff59c1a6bd05213090ca6e3cfecfc0431a7ee344b0",
      "size_bytes": 793366,
      "role": "volume",
      "volume_number": 2,
      "actual_page_count": 291,
      "file_note": null
    },
    {
      "relpath": "books/ibn_aqil/source/003.htm",
      "sha256": "da847f34106b31e13c34ce9bbe3fa3f9cf9c7574380170fd808d4357f13ab030",
      "size_bytes": 323392,
      "role": "volume",
      "volume_number": 3,
      "actual_page_count": 328,
      "file_note": null
    },
    {
      "relpath": "books/ibn_aqil/source/004.htm",
      "sha256": "e9216bd2cfc5639f2ce37beab4ff9b0bf40c1c967996b196068bcc6c9ee3372c",
      "size_bytes": 375840,
      "role": "volume",
      "volume_number": 4,
      "actual_page_count": 319,
      "file_note": null
    }
  ],
  "unrecognized_metadata_lines": [
    "[ترقيم الكتاب موافق للمطبوع، وأول مجلدين، بحاشية: منحة الجليل، بتحقيق شرح ابن عقيل]"
  ],
  "edition_notes": "4-volume commentary on ألفية ابن مالك. Vols 1-2 have footnotes, vols 3-4 do not.",
  "language": "ar",
  "intake_utc": "2026-02-25T12:00:00Z",
  "taxonomy_at_intake": {
    "balagha": "balagha_v0_4",
    "sarf": "sarf_v0_1",
    "nahw": "nahw_v0_1",
    "imlaa": "imlaa_v0_1"
  }
}
```

**Example 3 — multi-science book (miftah):**

```json
{
  "schema_version": "intake_metadata_v0.1",
  "book_id": "miftah",
  "title": "مفتاح العلوم",
  "title_formal": "مفتاح العلوم",
  "shamela_author_short": "السكاكي",
  "author": "يوسف بن أبي بكر بن محمد بن علي السكاكي الخوارزمي الحنفي أبو يعقوب (ت 626هـ)",
  "muhaqiq": "نعيم زرزور",
  "publisher": "دار الكتب العلمية، بيروت - لبنان",
  "shamela_page_count": 602,
  "shamela_edition": "الثانية، 1407 هـ - 1987 م",
  "shamela_volume_count": null,
  "publication_year": null,
  "html_qism_field": "البلاغة",
  "shamela_pub_date": "8 ذو الحجة 1431",
  "primary_science": null,
  "book_category": "multi_science",
  "science_parts": [
    {
      "section": "القسم الأول",
      "science_id": "sarf",
      "description": "علم الصرف والاشتقاق"
    },
    {
      "section": "القسم الثاني",
      "science_id": "nahw",
      "description": "علم النحو"
    },
    {
      "section": "القسم الثالث",
      "science_id": "balagha",
      "description": "علم المعاني والبيان والبديع"
    }
  ],
  "volume_count": 1,
  "total_actual_pages": 592,
  "source_files": [
    {
      "relpath": "books/miftah/source/miftah_al_ulum.htm",
      "sha256": "40b41f796e28900f9ef75fd34367f9530e72de83c20f6a0762b99c5d3782b1be",
      "size_bytes": 1416111,
      "role": "primary_export",
      "volume_number": null,
      "actual_page_count": 592,
      "file_note": null
    }
  ],
  "unrecognized_metadata_lines": [],
  "edition_notes": "Foundational cross-science text: Part 1 = صرف, Part 2 = نحو, Part 3 = بلاغة. Classical (626 هـ).",
  "language": "ar",
  "intake_utc": "2026-02-25T12:00:00Z",
  "taxonomy_at_intake": {
    "balagha": "balagha_v0_4",
    "sarf": "sarf_v0_1",
    "nahw": "nahw_v0_1",
    "imlaa": "imlaa_v0_1"
  }
}
```

**Example 4 — book with supplementary file (dalail):**

```json
{
  "schema_version": "intake_metadata_v0.1",
  "book_id": "dalail",
  "title": "دلائل الإعجاز ت شاكر",
  "title_formal": "دلائل الإعجاز في علم المعاني",
  "shamela_author_short": "عبد القاهر الجرجاني",
  "author": "أبو بكر عبد القاهر بن عبد الرحمن بن محمد الفارسي الأصل، الجرجاني الدار (ت 471 هـ)",
  "muhaqiq": "محمود محمد شاكر أبو فهر",
  "publisher": "مطبعة المدني بالقاهرة - دار المدني بجدة",
  "shamela_page_count": 684,
  "shamela_edition": "الثالثة 1413 هـ - 1992 م",
  "shamela_volume_count": null,
  "publication_year": null,
  "html_qism_field": "البلاغة",
  "shamela_pub_date": "24 ذو القعدة 1432",
  "primary_science": "balagha",
  "book_category": "single_science",
  "science_parts": null,
  "volume_count": 1,
  "total_actual_pages": 688,
  "source_files": [
    {
      "relpath": "books/dalail/source/001.htm",
      "sha256": "c5eb9730b0a36253919d9321244f171bc3d89e7c04b383f2cb6d97c766df72e3",
      "size_bytes": 1738904,
      "role": "primary_export",
      "volume_number": null,
      "actual_page_count": 676,
      "file_note": null
    },
    {
      "relpath": "books/dalail/source/muqaddima.htm",
      "sha256": "4ac3a58ef9583b5befaa960d14410c1e6700a9b48d5f4eda6ec8564edf19b4d3",
      "size_bytes": 37926,
      "role": "supplementary",
      "volume_number": null,
      "actual_page_count": 12,
      "file_note": "muqaddima — 12-page preface by the muhaqiq"
    }
  ],
  "unrecognized_metadata_lines": [],
  "edition_notes": "Shamela desktop export (ت شاكر edition). Classical prose treatise.",
  "language": "ar",
  "intake_utc": "2026-02-25T12:00:00Z",
  "taxonomy_at_intake": {
    "balagha": "balagha_v0_4",
    "sarf": "sarf_v0_1",
    "nahw": "nahw_v0_1",
    "imlaa": "imlaa_v0_1"
  }
}
```

Note: dalail's `title` is `"دلائل الإعجاز ت شاكر"` (Shamela's display name with editor shorthand), while `title_formal` is `"دلائل الإعجاز في علم المعاني"` (the book's proper name from الكتاب). This illustrates why both fields exist.

### 4.3 Registry entry format

The `books_registry.yaml` entry is a projection of intake metadata. Field names are identical where they overlap.

```yaml
- book_id: shadha
  title: "شذا العرف في فن الصرف"
  title_formal: "شذا العرف في فن الصرف"
  author: "أحمد بن محمد الحملاوي (ت 1351هـ)"
  muhaqiq: "نصر الله عبد الرحمن نصر الله"
  primary_science: sarf
  book_category: single_science
  source_format: shamela_html
  source_files:
    - relpath: "books/shadha/source/shadha_al_arf.htm"
      role: primary_export
  source_hashes:
    - "8c3fcc8e69b7b573b45be8eb3429748d6ddd43b1e6795382812dbefc5aaf1579"
  volume_count: 1
  language: ar
  edition_notes: "Shamela desktop HTML export. Modern textbook (صرف)."
  status: active
```

Fields in the registry but NOT in `intake_metadata.json`: `status` (lifecycle — set to `active` at intake, may change later), `source_format` (always `shamela_html` for now — may expand if other formats are supported).

**`source_hashes` derivation:** This is a flat list of SHA-256 hex digests, derived from all files in `source_files` — including supplementary files. The order matches `source_files`. For a single-volume book, `source_hashes` has 1 entry. For a multi-volume book with supplementary, it has N entries. This flat list enables fast duplicate checking in §3.3 without needing to parse nested `source_files` structures.

Fields in `intake_metadata.json` but NOT in the registry: `schema_version`, `shamela_author_short`, `size_bytes`, `actual_page_count`, `total_actual_pages`, `shamela_page_count`, `shamela_edition`, `shamela_volume_count`, `publication_year`, `html_qism_field`, `shamela_pub_date`, `publisher`, `unrecognized_metadata_lines`, `intake_utc`, `taxonomy_at_intake`, `science_parts`, `file_note`.

**Registry migration:** The current `books_registry.yaml` uses legacy field names from before this spec. The following renames apply:

| Legacy field | New field | Notes |
|---|---|---|
| `science_id` | `primary_science` | Clarifies it's an informational prior; null for multi/unrelated |
| `page_count` | *(removed)* | Was Shamela's inaccurate value; now in metadata as `shamela_page_count` |
| `volumes` | `volume_count` | Consistent with metadata |
| *(new)* | `title_formal` | From الكتاب field |
| *(new)* | `book_category` | `single_science` / `multi_science` / `tangentially_relevant` |
| *(new)* | `source_hashes` | Flat list of SHA-256 values for duplicate detection |

When the intake tool is built, it generates registry entries using the new field names. Existing entries should be migrated to match.

---

## 5. Edge Cases

→ See `edge_cases.md` in this folder.

---

## 6. What This Stage Does NOT Do

- Does not read or process book content beyond the metadata card (first `PageText` div)
- Does not normalize text (that's Stage 1)
- Does not detect structural divisions, volume markers, or section boundaries within content (that's Stage 2)
- Does not determine which specific excerpts belong to which science (that's Stage 4) — the book's declared science is an informational prior, not a routing constraint
