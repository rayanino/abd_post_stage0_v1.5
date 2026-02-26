# Passage 3 — Checkpoint 4 Report (Excerpts + Exclusions)

Baseline: `passage3_v0.3.8/`  
Scope: ص ٣٣–٤٠ (Jawahir al-Balagha)

## Outputs created
- `passage3_excerpts_v02.jsonl` (77 excerpt records + 4 exclusion records)

## Counts
- Excerpts: 77
  - teaching: 24
  - exercise: 53
    - exercise_role=set: 2
    - exercise_role=item: 32
    - exercise_role=answer: 19
- Exclusions (heading_structural): 4

## Coverage invariants (self-check)
- Matn non-heading atoms covered as core exactly once: 71 / 71
- Footnote atoms covered as core exactly once: 41 / 41
- No orphan atoms: OK

## Exercise policy enforcement
- Multi-line quoted unit kept as one item excerpt when clearly one unit (implemented for:
  - `jawahir:exc:000118` (matn:000189–000190)
  - `jawahir:exc:000126` (matn:000198–000199)
)

## Relations implemented
- `belongs_to_exercise_set`:
  - tatbiq items/answers → `jawahir:exc:000104`
  - as2ila items → `jawahir:exc:000152`
- `answers_exercise_item`:
  - each footnote answer excerpt points to its corresponding item excerpt (based on matn footnote_refs mapping)
- `footnote_explains`:
  - teaching footnotes → their matn teaching excerpts
  - balagha footnotes → their matn balagha definitions
- `has_overview`:
  - defect teaching excerpts → `jawahir:exc:000103` (summary line excerpt)

## Planned taxonomy bump (CP5 note)
Excerpt records already use `taxonomy_version = balagha_v0_4` and node ids that will be created/updated in CP5 via TC-008..TC-012 (per CP3 plan).  
No taxonomy snapshot is created in CP4 (per pipeline contract).
