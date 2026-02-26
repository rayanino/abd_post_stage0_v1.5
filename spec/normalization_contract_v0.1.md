# Normalization Contract v0.1

This document defines the **only allowed** text-normalization operations in ABD.

ABD aims to be a **faithful extractor**, not an editor. The production pipeline may normalize input text
only to achieve deterministic parsing and stable offsets.

## 1. Allowed operations (MUST be deterministic)

### 1.1 Whitespace normalization
- Convert Windows newlines (`\r\n`) to Unix newlines (`\n`).
- Replace non-breaking spaces (NBSP, U+00A0) with regular spaces.
- Collapse runs of spaces **inside a line** to a single space **only** if those spaces are artifacts of HTML export.
- Trim trailing spaces at end of line.

### 1.2 HTML entity decoding
- Decode standard HTML entities (e.g., `&nbsp;`, `&lt;`, `&gt;`, `&amp;`).

### 1.3 Unicode normalization
- **Do not** apply NFC/NFKC automatically.
- Arabic presentation forms and ligatures MUST be preserved exactly as exported unless you can prove Shamela introduces artifacts.

### 1.4 Tatweel (ـ)
- Preserve tatweel. Do not strip.

### 1.5 Arabic punctuation
- Preserve punctuation exactly.

## 2. Forbidden operations
- Adding, removing, or rewording any characters.
- "Fixing" spelling.
- Adding diacritics.
- Modernizing forms.
- Removing parentheses/brackets.

## 3. Offset policy
Offsets are measured in **Unicode codepoints** over the normalized canonical text.
Every atom's `anchor_span` MUST match exactly.

## 4. Gold baseline compatibility
Existing gold baselines may include `*_clean_*_input.txt` files that are reconstructed from atoms.
Those files are **architectural placeholders** for Checkpoint 1 artifacts, and MUST be explicitly marked in the
CP1 **source locator** file (`passage*_source_slice.json`) via its `notes` field.

Future gold passages SHOULD produce clean input text directly from the HTML slice for the passage.
