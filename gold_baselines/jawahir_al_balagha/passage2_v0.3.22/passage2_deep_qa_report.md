# Passage 2 — Deep QA Report (baseline integrity)

This document is a **human review aid**. It is **non-canonical**.

## Authoritative validation
The only authoritative source for:
- validator version
- validation command
- pass/fail result
- warning/error counts

is:
- `passage2_metadata.json` → `validation.*`
- `checkpoint_outputs/cp6_validate.stdout.txt`

## Structural invariants (sanity recap)
- Excerpts: 64
- Exclusions: 39
- Atoms: 152 (matn 86, footnote 66)
- Heading dual-state: headings are metadata-only (never core/context)
- Layer purity: each excerpt is single-layer (matn vs footnote); cross-layer linkage only via relations

## Cross-passage relations (intentional)
This baseline references a small number of excerpt IDs defined in earlier passages via relations:
- `jawahir:exc:000003`
- `jawahir:exc:000013`

When validating Passage 2 in isolation, these may appear as missing relation targets unless validation is run with `--allow-external-relations`.

## Reproducibility
- `baseline_manifest.json` inventories the package and fingerprints files.
- `checkpoint_outputs/cp6_tool_fingerprint.json` fingerprints the CP6 toolchain and key artifact hashes.
