# Active Gold Baselines — جواهر البلاغة

**Book:** جواهر البلاغة في المعاني والبيان والبديع — أحمد الهاشمي
**Science:** بلاغة
**book_id:** jawahir

## Active baselines (authoritative, immutable)

| Passage | Pages | Directory | Schema | Taxonomy |
|---------|-------|-----------|--------|----------|
| Passage 1 | ص ١٩–٢٥ | `gold_baselines/jawahir_al_balagha/passage1_v0.3.13/` | gold_standard_v0.3.3 | balagha_v0_2 |
| Passage 2 | ص ٢٦–٣٢ | `gold_baselines/jawahir_al_balagha/passage2_v0.3.22/` | gold_standard_v0.3.3 | balagha_v0_3 |
| Passage 3 | ص ٣٣–٤٠ | `gold_baselines/jawahir_al_balagha/passage3_v0.3.14/` | gold_standard_v0.3.3 | balagha_v0_3 |

## Continuation state (from Passage 3 metadata)

Passage 3 is the most recent baseline. Its `passage3_metadata.json` → `continuation` block provides the starting sequence numbers for any future Passage 4.

## Source HTML

The frozen source for all passages:
- `books/jawahir/source/jawahir_al_balagha.htm`

## Notes

- All three baselines have passed CP6 validation without `--skip-traceability`.
- Passages 2–3 use `balagha_v0_3` taxonomy; Passage 1 uses `balagha_v0_2`.
- Latest taxonomy is `balagha_v0_4` (202 nodes, 143 leaves).
