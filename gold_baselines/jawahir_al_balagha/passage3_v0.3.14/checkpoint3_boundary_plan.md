# Passage 3 — Checkpoint 3 Boundary & Placement Plan (prospective; for CP4 authoring)

This file captures the **proposed excerpt boundary + placement plan** that will be implemented in Checkpoint 4 for this baseline.  
It is written *before* CP4 to keep the workflow deterministic and reviewable.

## Scope
- Source: `../shamela_export.htm`
- Page range: **ص ٣٣–٤٠**
- Passage baseline: `passage3_v0.3.8/`

## Summary (planned)
- Planned excerpts: **77** (IDs jawahir:exc:000087 … jawahir:exc:000163)
- Planned excerpt kinds: {'teaching': 24, 'exercise': 53}
- Planned source layers: {'matn': 44, 'footnote': 33}
- Planned heading exclusions (structural): `jawahir:matn:000174` (تطبيق), `jawahir:matn:000204` (فصاحة المتكلم), `jawahir:matn:000215` (البلاغة), `jawahir:matn:000219` (بلاغة الكلام)

## Taxonomy evolution plan (v0_4 bump — pre-approved in chat)
This slice introduces leaf topics missing from `balagha_v0_3`. We will bump taxonomy to **`balagha_v0_4`** in CP5 using **TC-008..TC-012**:

- **TC-008 (leaf_granulated):** `3uyub_alkalam_ta3qid` → split into:
  - `3uyub_alkalam_ta3qid_lafzi`
  - `3uyub_alkalam_ta3qid_ma3nawi`
- **TC-009 (node_added):** `3uyub_alkalam_du3f_ta2lif`
- **TC-010 (node_added):** `3uyub_alkalam_tatabu3_idafat`
- **TC-011 (node_added):** `tatbiq_fasahat_alkalam`
- **TC-012 (node_added):** `as2ila_alfasaha`

## Candidate excerpt list
Each row shows: excerpt_id, layer, kind, taxonomy_node_id, **core atom span**.


- **jawahir:exc:000087** | matn | teaching | `3uyub_alkalam_du3f_ta2lif` | core: `jawahir:matn:000146-jawahir:matn:000149` | context_atoms: 0
- **jawahir:exc:000088** | footnote | teaching | `3uyub_alkalam_du3f_ta2lif` | core: `jawahir:fn:000103-jawahir:fn:000107` | context_atoms: 0
- **jawahir:exc:000089** | footnote | teaching | `3uyub_alkalam_du3f_ta2lif` | core: `jawahir:fn:000108-jawahir:fn:000109` | context_atoms: 0
- **jawahir:exc:000090** | matn | teaching | `3uyub_alkalam_ta3qid_lafzi` | core: `jawahir:matn:000150-jawahir:matn:000154` | context_atoms: 0
- **jawahir:exc:000091** | footnote | teaching | `3uyub_alkalam_ta3qid_lafzi` | core: `jawahir:fn:000110` | context_atoms: 0
- **jawahir:exc:000092** | footnote | teaching | `3uyub_alkalam_ta3qid_lafzi` | core: `jawahir:fn:000111` | context_atoms: 0
- **jawahir:exc:000093** | matn | teaching | `3uyub_alkalam_ta3qid_ma3nawi` | core: `jawahir:matn:000155-jawahir:matn:000163` | context_atoms: 0
- **jawahir:exc:000094** | footnote | teaching | `3uyub_alkalam_ta3qid_ma3nawi` | core: `jawahir:fn:000112` | context_atoms: 0
- **jawahir:exc:000095** | footnote | teaching | `3uyub_alkalam_ta3qid_ma3nawi` | core: `jawahir:fn:000113` | context_atoms: 0
- **jawahir:exc:000096** | footnote | teaching | `3uyub_alkalam_ta3qid_ma3nawi` | core: `jawahir:fn:000114` | context_atoms: 0
- **jawahir:exc:000097** | footnote | teaching | `3uyub_alkalam_ta3qid_ma3nawi` | core: `jawahir:fn:000115-jawahir:fn:000117` | context_atoms: 0
- **jawahir:exc:000098** | footnote | teaching | `3uyub_alkalam_ta3qid_ma3nawi` | core: `jawahir:fn:000118` | context_atoms: 0
- **jawahir:exc:000099** | matn | teaching | `3uyub_alkalam_ikrar` | core: `jawahir:matn:000164-jawahir:matn:000170` | context_atoms: 0
- **jawahir:exc:000100** | footnote | teaching | `3uyub_alkalam_ikrar` | core: `jawahir:fn:000119` | context_atoms: 0
- **jawahir:exc:000101** | matn | teaching | `3uyub_alkalam_tatabu3_idafat` | core: `jawahir:matn:000171-jawahir:matn:000172` | context_atoms: 0
- **jawahir:exc:000102** | footnote | teaching | `3uyub_alkalam_tatabu3_idafat` | core: `jawahir:fn:000120` | context_atoms: 0
- **jawahir:exc:000103** | matn | teaching | `fasahat_alkalam__overview` | core: `jawahir:matn:000173` | context_atoms: 0
- **jawahir:exc:000104** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000175` | context_atoms: 0
- **jawahir:exc:000105** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000176` | context_atoms: 0
- **jawahir:exc:000106** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000177` | context_atoms: 0
- **jawahir:exc:000107** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000178` | context_atoms: 0
- **jawahir:exc:000108** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000179` | context_atoms: 0
- **jawahir:exc:000109** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000180` | context_atoms: 0
- **jawahir:exc:000110** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000181` | context_atoms: 0
- **jawahir:exc:000111** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000182` | context_atoms: 0
- **jawahir:exc:000112** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000183` | context_atoms: 0
- **jawahir:exc:000113** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000184` | context_atoms: 0
- **jawahir:exc:000114** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000185` | context_atoms: 0
- **jawahir:exc:000115** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000186` | context_atoms: 0
- **jawahir:exc:000116** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000187` | context_atoms: 0
- **jawahir:exc:000117** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000188` | context_atoms: 0
- **jawahir:exc:000118** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000189-jawahir:matn:000190` | context_atoms: 0
- **jawahir:exc:000119** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000191` | context_atoms: 0
- **jawahir:exc:000120** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000192` | context_atoms: 0
- **jawahir:exc:000121** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000193` | context_atoms: 0
- **jawahir:exc:000122** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000194` | context_atoms: 0
- **jawahir:exc:000123** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000195` | context_atoms: 0
- **jawahir:exc:000124** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000196` | context_atoms: 0
- **jawahir:exc:000125** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000197` | context_atoms: 0
- **jawahir:exc:000126** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000198-jawahir:matn:000199` | context_atoms: 0
- **jawahir:exc:000127** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000200` | context_atoms: 0
- **jawahir:exc:000128** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000201` | context_atoms: 0
- **jawahir:exc:000129** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000202` | context_atoms: 0
- **jawahir:exc:000130** | matn | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:matn:000203` | context_atoms: 0
- **jawahir:exc:000131** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000121` | context_atoms: 0
- **jawahir:exc:000132** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000122` | context_atoms: 0
- **jawahir:exc:000133** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000123` | context_atoms: 0
- **jawahir:exc:000134** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000124` | context_atoms: 0
- **jawahir:exc:000135** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000125` | context_atoms: 0
- **jawahir:exc:000136** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000126` | context_atoms: 0
- **jawahir:exc:000137** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000127` | context_atoms: 0
- **jawahir:exc:000138** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000128` | context_atoms: 0
- **jawahir:exc:000139** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000129` | context_atoms: 0
- **jawahir:exc:000140** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000130` | context_atoms: 0
- **jawahir:exc:000141** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000131` | context_atoms: 0
- **jawahir:exc:000142** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000132` | context_atoms: 0
- **jawahir:exc:000143** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000133` | context_atoms: 0
- **jawahir:exc:000144** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000134` | context_atoms: 0
- **jawahir:exc:000145** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000135` | context_atoms: 0
- **jawahir:exc:000146** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000136` | context_atoms: 0
- **jawahir:exc:000147** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000137` | context_atoms: 0
- **jawahir:exc:000148** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000138` | context_atoms: 0
- **jawahir:exc:000149** | footnote | exercise | `tatbiq_fasahat_alkalam` | core: `jawahir:fn:000139` | context_atoms: 0
- **jawahir:exc:000150** | matn | teaching | `fasahat_almutakallim` | core: `jawahir:matn:000205-jawahir:matn:000207` | context_atoms: 0
- **jawahir:exc:000151** | footnote | teaching | `fasahat_almutakallim` | core: `jawahir:fn:000140` | context_atoms: 0
- **jawahir:exc:000152** | matn | exercise | `as2ila_alfasaha` | core: `jawahir:matn:000208` | context_atoms: 0
- **jawahir:exc:000153** | matn | exercise | `as2ila_alfasaha` | core: `jawahir:matn:000209` | context_atoms: 0
- **jawahir:exc:000154** | matn | exercise | `as2ila_alfasaha` | core: `jawahir:matn:000210` | context_atoms: 0
- **jawahir:exc:000155** | matn | exercise | `as2ila_alfasaha` | core: `jawahir:matn:000211` | context_atoms: 0
- **jawahir:exc:000156** | matn | exercise | `as2ila_alfasaha` | core: `jawahir:matn:000212` | context_atoms: 0
- **jawahir:exc:000157** | matn | exercise | `as2ila_alfasaha` | core: `jawahir:matn:000213` | context_atoms: 0
- **jawahir:exc:000158** | matn | exercise | `as2ila_alfasaha` | core: `jawahir:matn:000214` | context_atoms: 0
- **jawahir:exc:000159** | matn | teaching | `ta3rif_albalagha_lugha` | core: `jawahir:matn:000216-jawahir:matn:000217` | context_atoms: 0
- **jawahir:exc:000160** | footnote | teaching | `sabab_tasmiyat_albalagha` | core: `jawahir:fn:000141-jawahir:fn:000142` | context_atoms: 0
- **jawahir:exc:000161** | matn | teaching | `ta3rif_albalagha_istilah` | core: `jawahir:matn:000218` | context_atoms: 0
- **jawahir:exc:000162** | matn | teaching | `qayd_mutabaqat_albalagha_lilhal` | core: `jawahir:matn:000220` | context_atoms: 0
- **jawahir:exc:000163** | footnote | teaching | `qayd_mutabaqat_albalagha_lilhal` | core: `jawahir:fn:000143` | context_atoms: 0

## Critical notes for CP4 implementer

- **Exercise unit policy (approved):** multi-line verse that is clearly one quoted unit is kept as *one* exercise item excerpt (implemented here by grouping atoms 000198+000199; also item 000189+000190 is one unit because the prose correction line is part of the same exercise prompt).
- **Footnote markers are page-local:** repeated `(1)` etc are disambiguated by `page_hint` + deterministic `footnote_atom_ids` in matn atoms. No renumbering.
- **Mixed-scope exercise answers:** some exercise footnotes judge a word as (لغة رديئة / لم يسمع) — these are technically word-level fasaha issues but appear inside this فصاحة الكلام exercise set. We will preserve them as-is (content sovereignty) and record `tests_nodes` accordingly in CP4.
- **Balāgha definitions are mixed across atoms:** matn atom 000218 contains both a ‘بليغ’ usage clause and the technical scope restriction (بلاغة للكلام/المتكلم). We will place it under `ta3rif_albalagha_istilah` (single-leaf policy), and keep the purely لغوي definition in 000216–000217.