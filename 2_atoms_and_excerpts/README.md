# ⚠️ This Is NOT a Pipeline Stage

Despite the name, `2_atoms_and_excerpts/` is **not** Stage 2 of the pipeline. Stage 2 (Structure Discovery) lives in `2_structure_discovery/`.

This folder contains **precision rules and gold baselines** for the manual excerpting workflow that predates the automated pipeline. It is the **binding authority** when stage specs conflict:

| File | What it governs |
|------|----------------|
| `00_BINDING_DECISIONS_v0.3.16.md` | Atom boundaries, excerpt rules, topic scope, headings |
| `checklists_v0.4.md` | ATOM.*, EXC.*, PLACE.*, REL.* checklist items |
| `extraction_protocol_v2.4.md` | Manual checkpoint sequence (CP1–CP6) |

The `1_jawahir_al_balagha/` subfolder contains the hand-crafted gold baselines for بلاغة.

Several tools (`pipeline_gold.py`, `scaffold_passage.py`, `validate_gold.py`) have hardcoded paths to this folder, which is why it hasn't been renamed.
