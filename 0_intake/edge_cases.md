# Stage 0: Intake — Edge Cases

**Companion to:** INTAKE_SPEC.md v1.5

---

## EC-I.1 — Missing metadata fields

**Scenario:** A Shamela export's metadata card is missing one or more expected fields (e.g., no المؤلف, no الناشر).

**Behavior:** The corresponding field in `intake_metadata.json` is set to `null`. Only `title` is required — if missing, intake aborts. All other fields degrade gracefully to null with a log warning.

**Observed:** imla has no muhaqiq. ibn_aqil has no shamela_page_count. These are handled correctly.

---

## EC-I.2 — Unrecognized metadata labels

**Scenario:** The metadata card contains a label that doesn't match any known field pattern (exact or muhaqiq-contains).

**Behavior:** The full `label: value` text is appended to `unrecognized_metadata_lines`. Zero data loss — everything the parser can't classify is captured verbatim.

**Observed:** qatr has `طبع` (printer, distinct from publisher). ibn_aqil has a standalone `[ترقيم...]` annotation. Stress-test corpus surfaced `أعده للشاملة`, `كود المادة`, `المرحلة`, `مصدر الكتاب`, `قدم لها`, `أصل التحقيق`.

---

## EC-I.3 — Shamela page count mismatch

**Scenario:** The `عدد الصفحات` value in Shamela metadata doesn't match the actual `PageNumber` span count in the HTML.

**Behavior:** Both values are recorded separately (`shamela_page_count` vs `actual_page_count` / `total_actual_pages`). No correction is attempted. A 69% mismatch rate was observed across the original 7-book corpus — this is a known Shamela data quality issue.

**Rationale:** Shamela's count is informational. The actual count (from `PageNumber` spans) is authoritative for downstream stages.

---

## EC-I.4 — Leading-digit extraction from annotated numbers

**Scenario:** Shamela appends annotations directly to numeric values with no separator, e.g., `344[ترقيم الكتاب موافق للمطبوع]` or `80أعده للمكتبة الشاملة`.

**Behavior:** Regex `^\d+` extracts only the leading digits. Trailing text is discarded. A simple `int()` would crash on every book in the corpus.

---

## EC-I.5 — Duplicate SHA-256 hash across books

**Scenario:** A source file's SHA-256 hash matches a file already registered under a different book ID.

**Behavior:** Without `--force`: abort with error identifying the existing book. With `--force`: log warning and proceed, creating a separate intake. This enables intentional re-ingestion (e.g., different book ID for a variant edition extracted from the same Shamela export).

---

## EC-I.6 — Truncated HTML export

**Scenario:** The actual page count is significantly lower than Shamela's declared page count, suggesting the HTML export was truncated.

**Behavior:** If `actual / shamela_count < 0.80`, a soft confirmation prompt warns the user. If `actual / shamela_count > 1.25`, a warning is logged (reverse direction — Shamela count may be inaccurate).

**Observed:** Stress-test books مسائل (إذن) (10.1%) and فحولة (60.0%) both triggered the truncation warning. Both were legitimate cases of incomplete exports.

---

## EC-I.7 — Floating annotations between metadata segments

**Scenario:** Shamela inserts book-level annotations (e.g., `[ترقيم الكتاب موافق للمطبوع]`, `[الكتاب مرقم آليا]`) as bare HTML between `<span class='title'>` segments. The segment regex attaches these to the trailing content of the preceding segment.

**Behavior:** The parser strips these annotations when they appear as a suffix of a real field value. When the annotation IS the entire segment (as in ibn_aqil), it flows through to `unrecognized_metadata_lines` for data preservation.

**Validated:** On 18 files (7 original + 11 stress-test), covering all annotation positions.

---

## EC-I.8 — Value partially inside the span tag

**Scenario:** In most books, the field value follows `</span>`. In some (observed in ibn_aqil's المؤلف), the value is partially or fully inside the `<span>` alongside the label.

**Behavior:** The parser concatenates `SPAN_CONTENT + TRAILING_CONTENT` before splitting on the first colon, producing the correct result regardless of where the value falls relative to the span boundary.

---

## EC-I.9 — Multiple muhaqiq-matching labels

**Scenario:** A metadata card has two or more segments whose labels independently match muhaqiq patterns. Observed in 4/788 files in the Other Books corpus: the real muhaqiq (e.g., `تحقيق ودراسة`) followed by `أصل التحقيق` ("origin of the tahqiq" — a thesis description, not an editor name).

**Behavior:** Keep-first semantics. The first muhaqiq match is kept; subsequent matches are logged with a warning and routed to `unrecognized_metadata_lines`. Additionally, `أصل التحقيق` is in an explicit exclusion list (`MUHAQIQ_EXCLUSIONS`) so it never matches in the first place.

---

## EC-I.10 — Red font punctuation in metadata card

**Scenario:** Shamela wraps ALL punctuation in the metadata card in `<font color=#be0000>...</font>` tags — not just colons, but also commas, parentheses, brackets, periods, and dashes.

**Behavior:** The HTML-stripping step removes all font tags before text processing. The colon used for label:value splitting is the text-level colon that remains after stripping.

**Special case:** القسم is the only field where the colon is a plain `:` baked into the span text. All other fields use the red-colored `<font>` colon.

---

## EC-I.11 — Non-UTF-8 encoding

**Scenario:** A source file is not valid UTF-8.

**Behavior:** Immediate abort with error: "File {filename} is not valid UTF-8. Shamela exports are expected to be UTF-8."

**Note:** All observed Shamela exports (788+ files) use UTF-8 with CRLF line endings and no BOM.

---

## EC-I.12 — Single numbered file in a directory

**Scenario:** A directory contains exactly one numbered `.htm` file (e.g., just `001.htm`).

**Behavior:** Treated as single-volume. The file gets `role: "primary_export"` (NOT "volume 1 of 1"). `volume_number` is null. This is consistent with single-file input behavior.

**Rationale:** A single file doesn't constitute a multi-volume set. The "volume" role and numbering are reserved for actual multi-volume sets (2+ numbered files).

---

## Known Limitations

### Concurrent intake

Two simultaneous `intake.py` invocations each load the registry at startup, append their entry in memory, and write the full file at the end. The second write silently overwrites the first's entry. The first book's directory and `intake_metadata.json` exist on disk but the book vanishes from the registry. This is acceptable for a single-user CLI tool but must not be used in parallel.

### Volume count cross-check

When Shamela's `عدد الأجزاء` disagrees with the number of `.htm` volume files found, a warning is emitted but intake proceeds. The actual file count is authoritative.
