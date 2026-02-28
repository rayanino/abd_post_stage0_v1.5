# Stage 2: Structure Discovery — Zoom-In Brief

## Mandate

This is the **least mature and most critical** stage. It has zero existing tooling and the spec is a draft. Structure Discovery defines passage boundaries, which everything downstream (atomization, excerpting, taxonomy) depends on. This zoom-in will likely require the most time and iteration.

## Pre-Identified Issues

1. **No tooling exists.** Unlike Stage 1 (which has a working normalizer), this stage has no code. The three-pass algorithm is defined in the spec but has never been implemented or tested.

2. **LLM Pass 3 is underspecified.** Passes 1 (HTML-tagged headings) and 2 (keyword heuristics) are deterministic and relatively straightforward. Pass 3 (LLM-discovered divisions) is where the hard problems live: untagged headings, implicit section breaks, ambiguous hierarchy levels. The spec acknowledges this but offers no prompt design or examples.

3. **Passage boundary rules are soft.** The spec says passages should be 2–15 pages (soft guideline). It doesn't define precise rules for: when a structural division is too small to be its own passage (merge with neighbor), when it's too large (subdivide), or how to handle divisions that span page boundaries mid-sentence.

4. **Hierarchy inference is underspecified.** Section 4 defines detection methods but says little about how to infer the hierarchy (parent-child relationships). For example, how does the system know that باب 1 contains فصل 1.1? HTML nesting? Keyword semantics? Page range containment?

5. **`digestible` flag logic is vague.** The spec mentions a `digestible` property on divisions (non-digestible: مقدمة المحقق, خاتمة, فهرس) but doesn't define precise rules. How does the system distinguish a non-digestible editor's introduction from a digestible author's introduction?

6. **Corpus surveys exist but aren't operationalized.** Three corpus survey reports exist (`CORPUS_SURVEY_kutub_al_balagha.md`, `_kutub_sarf_nahw.md`, `_kutub_al_lugha.md`) plus a master survey. These document structural patterns observed across real books. The spec should incorporate these findings, but currently the surveys and the spec are somewhat disconnected.

7. **`structural_patterns.yaml` covers only 2 books.** The pattern library (v0.1) has patterns from جواهر البلاغة and شذا العرف. Additional books are needed to stress-test (TODO-010, TODO-017).

8. **Output format undefined.** The spec says Stage 2 produces `passages.jsonl` but doesn't define the schema. Stage 3 expects `passages.jsonl` as input — the format must be defined precisely.

## What to Read

- `2_structure_discovery/STRUCTURE_SPEC.md` (primary — 331 lines)
- `2_structure_discovery/edge_cases.md`
- `2_structure_discovery/structural_patterns.yaml` (pattern library, 2 books)
- `2_structure_discovery/MASTER_CORPUS_SURVEY.md`
- `2_structure_discovery/CORPUS_SURVEY_kutub_al_balagha.md` (if time permits)
- `1_normalization/NORMALIZATION_SPEC.md` §4.1 (understand the input: `pages.jsonl` format)
- `gold_baselines/jawahir_al_balagha/shamela_export.htm` (the actual source HTML — to understand what Pass 1 and Pass 2 work with)

## Expected Deliverables

- Finalized three-pass algorithm with precise rules for each pass
- `passages.jsonl` schema definition (new file in `schemas/` or inline)
- Hierarchy inference rules (explicit algorithm)
- `digestible` flag decision procedure
- Passage boundary sizing rules (when to merge/split divisions)
- LLM Pass 3 prompt design (at least a skeleton)
- Updated edge cases
- Honest assessment of what can't be finalized without additional HTML test data
