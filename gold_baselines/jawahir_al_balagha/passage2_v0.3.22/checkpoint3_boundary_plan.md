# Passage 2 — Checkpoint 3 Boundary & Placement Plan (reconstructed from Checkpoint 4)

> NOTE (post-Checkpoint 4 corrections applied in Checkpoint 5):
> - All Passage 2 excerpts are now stamped `taxonomy_version: balagha_v0_3`.
> - Node ID corrected to ASCII: `3uyub_alfard_ibham` (no diacritics).
> - Exercise ontology constraint enforced: jawahir:exc:000031 is the set; items 000032–000034 belong to it.
> - Taxonomy changes are TC-004..TC-007 (see taxonomy_changes.jsonl).


This file captures the **candidate excerpt boundary + placement plan** that led to the finalized Checkpoint 4 outputs. It is provided to keep the Passage 2 folder complete and to prevent future builders from missing the “Checkpoint 3 reasoning layer”.
## Summary
- Total excerpts: **65** (IDs jawahir:exc:000022 … jawahir:exc:000086)
- Total exclusions: **38** (embedded in `passage2_excerpts_v02.jsonl` as `record_type=exclusion`)
- Excerpt kinds: {'exercise': 46, 'teaching': 19}
- Source layers: {'matn': 48, 'footnote': 17}

## Candidate excerpt list
Each row shows: excerpt_id, layer, kind, taxonomy_node_id, **core atom span**.

- **jawahir:exc:000022** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000060-000061` | context_atoms: 0
- **jawahir:exc:000023** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000062-000063` | context_atoms: 0
- **jawahir:exc:000024** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000064-000068` | context_atoms: 0
- **jawahir:exc:000025** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000069-000070` | context_atoms: 0
- **jawahir:exc:000026** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000071-000078` | context_atoms: 0
- **jawahir:exc:000027** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000079` | context_atoms: 0
- **jawahir:exc:000028** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000080` | context_atoms: 0
- **jawahir:exc:000029** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000081` | context_atoms: 0
- **jawahir:exc:000030** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000082` | context_atoms: 0
- **jawahir:exc:000031** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000084` | context_atoms: 0
- **jawahir:exc:000032** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000085` | context_atoms: 0
- **jawahir:exc:000033** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000086` | context_atoms: 0
- **jawahir:exc:000034** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000087` | context_atoms: 0
- **jawahir:exc:000035** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000089` | context_atoms: 0
- **jawahir:exc:000036** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000090` | context_atoms: 0
- **jawahir:exc:000037** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000091` | context_atoms: 0
- **jawahir:exc:000038** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000092` | context_atoms: 0
- **jawahir:exc:000039** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000093` | context_atoms: 0
- **jawahir:exc:000040** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000094` | context_atoms: 0
- **jawahir:exc:000041** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000095` | context_atoms: 0
- **jawahir:exc:000042** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000096` | context_atoms: 0
- **jawahir:exc:000043** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000097-000099` | context_atoms: 0
- **jawahir:exc:000044** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000100-000101` | context_atoms: 0
- **jawahir:exc:000045** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000103` | context_atoms: 0
- **jawahir:exc:000046** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000104` | context_atoms: 0
- **jawahir:exc:000047** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000105` | context_atoms: 0
- **jawahir:exc:000048** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000107` | context_atoms: 0
- **jawahir:exc:000049** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000108` | context_atoms: 0
- **jawahir:exc:000050** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000109` | context_atoms: 0
- **jawahir:exc:000051** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000110` | context_atoms: 0
- **jawahir:exc:000052** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000111` | context_atoms: 0
- **jawahir:exc:000053** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000112-000113` | context_atoms: 0
- **jawahir:exc:000054** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000114-000116` | context_atoms: 0
- **jawahir:exc:000055** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000117-000118` | context_atoms: 0
- **jawahir:exc:000056** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000119-000120` | context_atoms: 0
- **jawahir:exc:000057** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000122` | context_atoms: 0
- **jawahir:exc:000058** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000123-000124` | context_atoms: 0
- **jawahir:exc:000059** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000125-000127` | context_atoms: 0
- **jawahir:exc:000060** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000128-000129` | context_atoms: 0
- **jawahir:exc:000061** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000131` | context_atoms: 0
- **jawahir:exc:000062** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000132` | context_atoms: 0
- **jawahir:exc:000063** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000133` | context_atoms: 0
- **jawahir:exc:000064** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000134` | context_atoms: 0
- **jawahir:exc:000065** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000135` | context_atoms: 0
- **jawahir:exc:000066** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000136` | context_atoms: 0
- **jawahir:exc:000067** | matn | exercise | `tatbiq_fasahat_alfard` | core: `jawahir:matn:000137` | context_atoms: 0
- **jawahir:exc:000068** | matn | teaching | `fasahat_alkalam__overview` | core: `jawahir:matn:000139-000140` | context_atoms: 0
- **jawahir:exc:000069** | matn | teaching | `3uyub_alkalam_tanafur_kalimat` | core: `jawahir:matn:000141-000145` | context_atoms: 0
- **jawahir:exc:000070** | footnote | teaching | `3uyub_alfard_mukhalafat_qiyas` | core: `jawahir:fn:000037` | context_atoms: 0
- **jawahir:exc:000071** | footnote | teaching | `3uyub_alfard_karahat_sam3` | core: `jawahir:fn:000038` | context_atoms: 0
- **jawahir:exc:000072** | footnote | teaching | `3uyub_alfard_karahat_sam3` | core: `jawahir:fn:000040` | context_atoms: 0
- **jawahir:exc:000073** | footnote | teaching | `3uyub_alfard_mukhalafat_qiyas` | core: `jawahir:fn:000041` | context_atoms: 0
- **jawahir:exc:000074** | footnote | teaching | `3uyub_alfard_mukhalafat_qiyas` | core: `jawahir:fn:000048` | context_atoms: 0
- **jawahir:exc:000075** | footnote | teaching | `3uyub_alfard_gharaba` | core: `jawahir:fn:000049` | context_atoms: 0
- **jawahir:exc:000076** | footnote | teaching | `3uyub_alfard_mukhalafat_qiyas` | core: `jawahir:fn:000050` | context_atoms: 0
- **jawahir:exc:000077** | footnote | teaching | `3uyub_alfard_mukhalafat_qiyas` | core: `jawahir:fn:000051` | context_atoms: 0
- **jawahir:exc:000078** | footnote | teaching | `3uyub_alfard_gharaba` | core: `jawahir:fn:000056` | context_atoms: 0
- **jawahir:exc:000079** | footnote | teaching | `3uyub_alfard_mukhalafat_qiyas` | core: `jawahir:fn:000065-000068` | context_atoms: 0
- **jawahir:exc:000080** | footnote | teaching | `3uyub_alfard_ibtidhal` | core: `jawahir:fn:000069-000082` | context_atoms: 0
- **jawahir:exc:000081** | footnote | teaching | `3uyub_alfard_ibham` | core: `jawahir:fn:000083` | context_atoms: 0
- **jawahir:exc:000082** | footnote | teaching | `3uyub_alfard_ishtirak_bila_qarina` | core: `jawahir:fn:000084` | context_atoms: 0
- **jawahir:exc:000083** | footnote | teaching | `fasahat_alkalam__overview` | core: `jawahir:fn:000097-000098` | context_atoms: 0
- **jawahir:exc:000084** | footnote | teaching | `fasahat_alkalam__overview` | core: `jawahir:fn:000099-000100` | context_atoms: 0
- **jawahir:exc:000085** | footnote | teaching | `3uyub_alkalam_tanafur_kalimat` | core: `jawahir:fn:000101` | context_atoms: 0
- **jawahir:exc:000086** | footnote | teaching | `3uyub_alkalam_tanafur_kalimat` | core: `jawahir:fn:000102` | context_atoms: 0

## Placement frequency (top 20)
- `tatbiq_fasahat_alfard`: 46
- `3uyub_alfard_mukhalafat_qiyas`: 6
- `fasahat_alkalam__overview`: 3
- `3uyub_alkalam_tanafur_kalimat`: 3
- `3uyub_alfard_karahat_sam3`: 2
- `3uyub_alfard_gharaba`: 2
- `3uyub_alfard_ibtidhal`: 1
- `3uyub_alfard_ibham`: 1
- `3uyub_alfard_ishtirak_bila_qarina`: 1

## Critical notes for builders
- Parentheses numbering like `(1)` can be **authorial enumeration** or **footnote markers**; correct distinction must be made in the HTML layer. For this gold passage, we did **not** force matn↔footnote links based on numeric labels when ambiguous.
- Headings are structural; they are excluded and only referenced via `heading_path` in excerpt records.
- Split-discussion policy: no stitched distant cores; use separate excerpts linked by relations where needed.