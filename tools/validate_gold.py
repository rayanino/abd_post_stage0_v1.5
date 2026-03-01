#!/usr/bin/env python3
"""
Gold Standard Validator v0.3.13
Validates atoms, excerpts, exclusions, taxonomy_changes, and decision traceability
against gold_standard_schema_v0.3.3.json (or earlier) with comprehensive structural invariants.

Usage:
  python validate_gold.py \
    --atoms passage2_matn_atoms_v02.jsonl passage2_fn_atoms_v02.jsonl \
    --excerpts passage2_excerpts_v02.jsonl \
    --schema gold_standard_schema_v0.3.3.json \
    --canonical matn:passage2_matn_canonical.txt footnote:passage2_fn_canonical.txt \
    --taxonomy-changes taxonomy_changes.jsonl \
    --taxonomy balagha_v0_3.yaml \
    --decisions passage2_decisions.jsonl \
	    --checklists 2_atoms_and_excerpts/checklists_v0.4.md \
    [--allow-unknown-vocab] [--allow-external-relations]

New in v0.3.8 (checkpoint index — no schema changes):
  - checkpoint_outputs/index.txt required when CP1+ completed
  - index must be deterministic and match tools/checkpoint_index_lib.py algorithm
  - validator recomputes expected index and requires exact match

New in v0.3.12 (reference-style + checklist-version lint — no schema changes):
  - Lint: ambiguous excerpt shorthand like E16 is forbidden in authoritative note fields (boundary_reasoning, exclusion_note, title_reason, anomaly details, decision notes)
    * Enforced as ERROR for baselines with baseline_version >= v0.3.13; WARN otherwise.
  - Lint: excerpt_decision.checklist_version should match the version of the provided --checklists file
    * Enforced as ERROR for baselines with baseline_version >= v0.3.13; WARN otherwise.


New in v0.3.13 (multi-baseline external resolution — no schema changes):
  - Optional: resolve missing excerpt relation targets and taxonomy_change.triggered_by_excerpt_id
    against the union of excerpt_ids from all ACTIVE_GOLD baselines under the ABD root.
    * Use --resolve-external-from-active-gold to enable.
    * This reduces "expected" warning noise from cross-passage references while still erroring
      when a target is missing across the whole active gold set.

New in v0.3.11 (content anomaly lint — schema v0.3.3+):
  - Excerpt-level `content_anomalies` validated (shape via schema; evidence_atom_ids existence enforced)
  - Optional evidence_excerpt_ids checked after excerpt load
  - Fix: excerpt_title uniqueness collection under taxonomy_node_id

New in v0.3.10 (cross-science consistency lint — no schema changes):
  - When cross_science_context=true, require case_types includes D4_cross_science and related_science is set
  - rhetorical_treatment_of_cross_science cannot be true unless cross_science_context is true

New in v0.3.9 (supportive dependency lint — no schema changes):
  - If boundary_reasoning contains a SUPPORTIVE_DEPENDENCIES: YAML block, the validator
    parses and lints its shape and cross-checks consistency with context_atoms.
  - This lint is conditional/optional: it only runs when the marker block is present.

New in v0.3.7 (checkpoint outputs capture — no schema changes):
  - checkpoint_state.json required (unless --skip-checkpoint-state-check)
  - checkpoint_state.json validated against checkpoint_state_schema_v0.1.json when available
  - checkpoint state integrity checks: status vs last_completed; artifact existence; manifest sha256 match

New in v0.3.5 (source locator hardening — no schema changes):
  - Source locator contract enforcement: {passage}_source_slice.json validates against source_locator_schema_v0.1.json when available
  - CP1 locator integrity checks: selector sanity + source artifact sha256 match (when baseline_relpath exists)

New in v0.3.4 (architecture hardening — no schema changes):
  - Archive guard: refuse to validate anything under _ARCHIVE/ unless --allow-archive
  - Support-file schema validation: passage metadata, baseline manifest, decision log (JSON schema)
  - Checkpoint-1 artifact enforcement: *_clean_*_input.txt + *_source_slice.json (unless --skip-clean-input-check)
  - Optional taxonomy snapshot identity check via --taxonomy-registry

New in v0.3.3 (binding-aligned hardening — no schema changes):
  - Controlled core-duplication exceptions: interwoven_group_id (B3_interwoven) and shared_shahid (evidence only)
  - Strict taxonomy leaf policy: leaf:true required for childless nodes; leaf nodes cannot have children
  - Relation target integrity (with --allow-external-relations for cross-passage targets)
  - split_discussion must mirror split_* relations

New in v0.3.2 (traceability layer — no schema changes):
  - --decisions: validates decision log JSONL
    • every excerpt_id has exactly one excerpt_decision record
    • all PLACE.P1-P7 checklist items present with boolean values
    • checklist IDs referenced exist in checklists file
  - --checklists: path to checklists markdown file for ID validation
  - boundary_reasoning labeled-block enforcement (GROUPING, BOUNDARY, ROLES,
    PLACEMENT, CHECKLIST, ALTS)
  - atomization_notes structured format check (TYPE, BOUNDARY, CHECKLIST)

Inherited from v0.3.1:
  - exercise_answer_content core role + exercise_role=answer
  - answers_exercise_item + belongs_to_exercise_set relation types
  - Exercise item must belong to exactly one exercise set (validator enforced)
  - footnote_ref_status: orphan refs must have note; non-orphan must have atom_ids
  - source_inconsistency internal_tag type
  - Heuristic: warn if atomization_notes mentions quotation but role=author_prose
"""

import json, sys, re, argparse, hashlib
from collections import defaultdict

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    print("ERROR: missing dependency PyYAML. Fix: python -m pip install -r requirements.txt")
    sys.exit(1)


def _is_archive_path(p: str) -> bool:
    p2 = str(p).replace("\\", "/")
    return "/_ARCHIVE/" in p2 or p2.endswith("/_ARCHIVE")


def _archive_guard(paths, allow_archive: bool, report) -> bool:
    bad = [p for p in paths if p and _is_archive_path(p)]
    if bad and not allow_archive:
        report.error("Refusing to run on _ARCHIVE paths without --allow-archive: " + ", ".join(map(str, bad)))
        return False
    return True


def _auto_detect_one(base_dir: str, pattern: str):
    import glob, os
    hits = sorted(glob.glob(os.path.join(base_dir, pattern)))
    return hits[0] if len(hits) == 1 else None



def _find_abd_root(start_dir: str):
    """Ascend from start_dir to find the ABD root (directory containing tools/ and schemas/)."""
    import os
    cur = os.path.abspath(start_dir)
    for _ in range(12):
        if os.path.isdir(os.path.join(cur, "tools")) and os.path.isdir(os.path.join(cur, "schemas")):
            # validate_gold.py should live in tools/
            if os.path.exists(os.path.join(cur, "tools", "validate_gold.py")):
                return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def _find_active_gold_files(root: str):
    import os
    out = []
    for dirpath, _, filenames in os.walk(root):
        if "ACTIVE_GOLD.md" in filenames:
            out.append(os.path.join(dirpath, "ACTIVE_GOLD.md"))
    return sorted(out)


def _parse_baseline_dirs(active_gold_md: str):
    import re, os
    base = os.path.dirname(active_gold_md)
    dirs = []
    for line in open(active_gold_md, encoding="utf-8"):
        m = re.search(r"`([^`]*passage\d+_v[0-9.]+/?)`", line)
        if m:
            rel = m.group(1).rstrip("/")
            dirs.append(os.path.abspath(os.path.join(base, rel)))
    return dirs


def _collect_excerpt_ids_from_baseline_dir(baseline_dir: str):
    """Load excerpt_ids from the baseline's excerpts JSONL (record_type=excerpt)."""
    import glob, os
    ids = set()
    hits = sorted(glob.glob(os.path.join(baseline_dir, "passage*_excerpts_v*.jsonl")))
    if not hits:
        return ids
    # If multiple hits exist, load all.
    for p in hits:
        for _, rec in load_jsonl(p):
            if rec.get("record_type") == "excerpt":
                eid = rec.get("excerpt_id")
                if eid:
                    ids.add(eid)
    return ids


def _resolve_external_excerpt_ids_from_active_gold(base_dir: str, report):
    """Resolve union of excerpt_ids across all ACTIVE_GOLD baselines under the ABD root."""
    abd_root = _find_abd_root(base_dir)
    if not abd_root:
        report.warn("[external] Could not locate ABD root to resolve ACTIVE_GOLD baselines")
        return set()
    gold_files = _find_active_gold_files(abd_root)
    if not gold_files:
        report.warn("[external] No ACTIVE_GOLD.md files found under ABD root; external resolution disabled")
        return set()

    baseline_dirs = []
    for f in gold_files:
        baseline_dirs.extend(_parse_baseline_dirs(f))

    # de-dup and ignore archives
    seen = set()
    uniq = []
    for d in baseline_dirs:
        d2 = d.replace("\\", "/")
        if "/_ARCHIVE/" in d2:
            continue
        if d not in seen:
            seen.add(d)
            uniq.append(d)

    union = set()
    for d in uniq:
        union |= _collect_excerpt_ids_from_baseline_dir(d)

    report.note(f"[external] Resolved {len(union)} excerpt_ids from {len(uniq)} active baselines")
    return union




def _load_support_schema(schemas_dir: str, filename: str):
    import os
    p = os.path.join(schemas_dir, filename)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _validate_json_file(path: str, schema_obj, report, prefix: str):
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        jsonschema.validate(obj, schema_obj)
        report.note(f"{prefix} Schema OK: {path}")
        return obj
    except Exception as e:
        report.error(f"{prefix} Schema FAIL: {path} — {e}")
        return None


def _validate_jsonl_file(path: str, schema_obj, report, prefix: str) -> bool:
    ok = True
    for line_num, rec in load_jsonl(path):
        if "_parse_error" in rec:
            ok = False
            continue
        try:
            jsonschema.validate(rec, schema_obj)
        except Exception as e:
            ok = False
            report.error(f"{prefix} Line {line_num}: schema FAIL — {e}")
    if ok:
        report.note(f"{prefix} JSONL schema OK: {path}")
    return ok


def _sha256_bytes(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _check_clean_inputs(base_dir: str, passage_id: str, canonical_map: dict, schemas_dir: str | None, skip: bool, report):
    """Enforce existence of CP1 (Checkpoint-1) artifacts.

    CP1 artifacts represent the *raw clean text slice* extracted from the source HTML before any
    layer-separation, exclusions, or atomization decisions.

    Therefore CP1 artifacts are **not expected** to match canonical layer texts byte-for-byte.
    The validator only enforces presence + basic well-formedness + metadata consistency.
    """
    import os
    if skip:
        report.note("[cp1] Clean input check skipped (--skip-clean-input-check)")
        return

    expected = {
        "matn": f"{passage_id}_clean_matn_input.txt",
        "footnote": f"{passage_id}_clean_fn_input.txt",
        "slice": f"{passage_id}_source_slice.json",
    }

    for _, fn in expected.items():
        p = os.path.join(base_dir, fn)
        if not os.path.exists(p):
            report.error(f"[cp1] Missing required Checkpoint-1 artifact: {fn}")

    # Basic well-formedness: newline-terminated files are preferred for deterministic concatenation.
    for k in ("matn", "footnote"):
        p = os.path.join(base_dir, expected[k])
        if os.path.exists(p):
            try:
                b = open(p, "rb").read()
                if b and not b.endswith(b"\n"):
                    report.warn(f"[cp1] {expected[k]} does not end with newline (recommended).")
            except Exception:
                report.warn(f"[cp1] Could not read {expected[k]} to check newline termination.")

    # If source slice JSON exists, validate against source locator schema when available.
    slice_path = os.path.join(base_dir, expected["slice"])
    if os.path.exists(slice_path):
        try:
            slice_obj = json.loads(open(slice_path, encoding="utf-8").read())
            schema_path = None
            if schemas_dir:
                cand = os.path.join(schemas_dir, "source_locator_schema_v0.1.json")
                if os.path.exists(cand):
                    schema_path = cand

            if schema_path:
                try:
                    schema_obj = json.loads(open(schema_path, encoding="utf-8").read())
                    jsonschema.validate(slice_obj, schema_obj)
                    report.note(f"[cp1] Source locator schema OK: {expected['slice']}")
                except Exception as e:
                    report.error(f"[cp1] Source locator schema FAIL: {expected['slice']} — {e}")

                # Additional invariants not expressible in JSON Schema.
                try:
                    for sel in slice_obj.get("selectors", []):
                        if sel.get("kind") == "html_char_range":
                            cs = int(sel.get("char_start", -1))
                            ce = int(sel.get("char_end", -1))
                            if ce <= cs:
                                report.error(f"[cp1] html_char_range invalid: char_end ({ce}) <= char_start ({cs})")
                        if sel.get("kind") == "shamela_page_marker_range":
                            ps = int(sel.get("page_start", -1))
                            pe = int(sel.get("page_end", -1))
                            if pe < ps:
                                report.error(f"[cp1] page marker range invalid: page_end ({pe}) < page_start ({ps})")

                    src = slice_obj.get("source_artifact", {})
                    rel = src.get("baseline_relpath")
                    sha = src.get("sha256")
                    if rel:
                        src_path = os.path.abspath(os.path.join(base_dir, rel))
                        if not os.path.exists(src_path):
                            report.error(f"[cp1] source artifact not found at baseline_relpath: {rel}")
                        else:
                            actual = _sha256_bytes(src_path)
                            if sha and actual != sha:
                                report.error(f"[cp1] source artifact sha256 mismatch for {rel}: expected {sha}, got {actual}")
                except Exception as e:
                    report.warn(f"[cp1] Could not perform additional source locator checks: {e}")
            else:
                # Legacy fallback: minimal key presence only.
                for req in ("source_html", "page_start", "page_end"):
                    if req not in slice_obj:
                        report.warn(f"[cp1] {expected['slice']} missing key: {req}")
        except Exception:
            report.warn(f"[cp1] {expected['slice']} is not valid JSON.")


def _check_checkpoint_state(base_dir: str, metadata_obj: dict | None, schemas_dir: str | None, skip: bool, report):

    """Validate and sanity-check checkpoint_state.json.

    Requirements (when not skipped):
      - checkpoint_state.json exists in base_dir
      - validates against checkpoint_state_schema_v0.1.json (when schemas_dir provided)
      - checkpoint_last_completed aligns with per-checkpoint status
      - listed artifacts exist relative to base_dir
      - integrity.baseline_manifest_sha256 matches sha256(baseline_manifest.json)
      - integrity.validator_version matches metadata.validation.validator_version (if metadata provided)
    """
    import os

    if skip:
        report.note("[cp_state] Checkpoint state check skipped (--skip-checkpoint-state-check)")
        return None

    state_fp = os.path.join(base_dir, "checkpoint_state.json")
    if not os.path.exists(state_fp):
        report.error("[cp_state] Missing checkpoint_state.json (required)")
        return None

    state_obj = None
    if schemas_dir:
        try:
            st_schema = _load_support_schema(schemas_dir, "checkpoint_state_schema_v0.1.json")
            state_obj = _validate_json_file(state_fp, st_schema, report, "[support:checkpoint_state]")
        except Exception as e:
            report.error(f"[support:checkpoint_state] Could not validate schema: {e}")
            return None
    else:
        try:
            with open(state_fp, encoding="utf-8") as f:
                state_obj = json.load(f)
            report.warn("[support:checkpoint_state] schemas_dir not provided; skipping schema validation")
        except Exception as e:
            report.error(f"[support:checkpoint_state] Could not load: {e}")
            return None

    if not state_obj:
        return None

    last = int(state_obj.get("checkpoint_last_completed", 0))
    cps = state_obj.get("checkpoints", {})

    for i in range(1, 7):
        c = cps.get(str(i))
        if not c:
            report.error(f"[cp_state] Missing checkpoint entry: {i}")
            continue
        status = c.get("status")
        if i <= last and status != "done":
            report.error(f"[cp_state] checkpoint {i} must be done when last_completed={last}")
        if i > last and status == "done":
            report.warn(f"[cp_state] checkpoint {i} is done but last_completed={last} (consider bumping last_completed)")

        for rel in (c.get("artifacts") or []):
            ap = os.path.join(base_dir, rel)
            if not os.path.exists(ap):
                report.error(f"[cp_state] checkpoint {i} lists missing artifact: {rel}")

    # Standardized checkpoint output capture (architectural contract)
    od = os.path.join(base_dir, 'checkpoint_outputs')
    if last >= 1:
        if not os.path.isdir(od):
            report.error('[cp_state] Missing checkpoint_outputs/ directory (required when CP1+ completed)')
        else:
            req1 = ['cp1_extract_clean_input.stdout.txt', 'cp1_extract_clean_input.stderr.txt']
            for fn in req1:
                fp = os.path.join(od, fn)
                if not os.path.exists(fp):
                    report.error(f'[cp_state] Missing CP1 log: checkpoint_outputs/{fn}')
            # Ensure CP1 artifact listing includes the logs
            c1 = cps.get('1') or {}
            arts1 = set(c1.get('artifacts') or [])
            for fn in req1:
                rel = f'checkpoint_outputs/{fn}'
                if rel not in arts1:
                    report.error(f'[cp_state] CP1 must list log in artifacts: {rel}')
            # Deterministic checkpoint index (required when CP1+ is completed)
            idx_rel = 'checkpoint_outputs/index.txt'
            idx_fp = os.path.join(base_dir, idx_rel)
            if not os.path.exists(idx_fp):
                report.error(f'[cp_state] Missing checkpoint index: {idx_rel}')
            else:
                if idx_rel not in arts1:
                    report.error(f'[cp_state] CP1 must list index in artifacts: {idx_rel}')
                # Recompute expected deterministic content and require exact match.
                try:
                    from checkpoint_index_lib import expected_index_text
                    expected = expected_index_text(base_dir)
                    with open(idx_fp, encoding='utf-8') as f:
                        actual = f.read()
                    if actual != expected:
                        report.error('[cp_state] checkpoint_outputs/index.txt does not match expected deterministic content (regenerate)')
                except Exception as e:
                    report.error(f'[cp_state] Could not validate checkpoint_outputs/index.txt deterministically: {e}')

    if last >= 6:
        if not os.path.isdir(od):
            report.error('[cp_state] Missing checkpoint_outputs/ directory (required when CP6 completed)')
        else:
            req6 = ['cp6_validate.stdout.txt', 'cp6_validate.stderr.txt', 'cp6_render_md.stdout.txt', 'cp6_render_md.stderr.txt']
            for fn in req6:
                fp = os.path.join(od, fn)
                if not os.path.exists(fp):
                    report.error(f'[cp_state] Missing CP6 log: checkpoint_outputs/{fn}')
            c6 = cps.get('6') or {}
            arts6 = set(c6.get('artifacts') or [])
            for fn in req6:
                rel = f'checkpoint_outputs/{fn}'
                if rel not in arts6:
                    report.error(f'[cp_state] CP6 must list log in artifacts: {rel}')
            # When CP6 is completed, CP6 artifact listing must include the deterministic index too.
            idx_rel = 'checkpoint_outputs/index.txt'
            if idx_rel not in arts6:
                report.error(f'[cp_state] CP6 must list index in artifacts: {idx_rel}')
            # CP6 tool fingerprint (required when CP6 completed)
            fp_rel = 'checkpoint_outputs/cp6_tool_fingerprint.json'
            fp_fp = os.path.join(base_dir, fp_rel)
            if not os.path.exists(fp_fp):
                if _is_archive_path(base_dir):
                    report.warn(f'[cp_state] Missing CP6 tool fingerprint (archive baseline): {fp_rel}')
                else:
                    report.error(f'[cp_state] Missing CP6 tool fingerprint: {fp_rel}')
            else:
                if fp_rel not in arts6:
                    if _is_archive_path(base_dir):
                        report.warn(f'[cp_state] CP6 should list tool fingerprint in artifacts (archive baseline): {fp_rel}')
                    else:
                        report.error(f'[cp_state] CP6 must list tool fingerprint in artifacts: {fp_rel}')
                # Basic JSON shape validation
                try:
                    obj = json.load(open(fp_fp, encoding='utf-8'))
                    if obj.get('record_type') != 'cp6_tool_fingerprint':
                        report.error('[cp_state] cp6_tool_fingerprint.json record_type must be cp6_tool_fingerprint')
                    for k in ('fingerprint_version','generated_utc','tools','baseline','validation'):
                        if k not in obj:
                            report.error(f'[cp_state] cp6_tool_fingerprint.json missing key: {k}')
                except Exception as e:
                    report.error(f'[cp_state] Could not parse cp6_tool_fingerprint.json: {e}')

    man_fp = os.path.join(base_dir, "baseline_manifest.json")
    if os.path.exists(man_fp):
        actual = _sha256_bytes(man_fp)
        claimed = (state_obj.get("integrity") or {}).get("baseline_manifest_sha256")
        if claimed and claimed != actual:
            report.error(f"[cp_state] integrity.baseline_manifest_sha256 mismatch: claimed {claimed} vs actual {actual}")
    else:
        report.warn("[cp_state] baseline_manifest.json missing (cannot verify integrity.baseline_manifest_sha256)")

    if metadata_obj:
        mv = ((metadata_obj.get("validation") or {}).get("validator_version") or "").strip()
        cv = ((state_obj.get("integrity") or {}).get("validator_version") or "").strip()
        if mv and cv and mv != cv:
            report.error(f"[cp_state] integrity.validator_version mismatch: state {cv} vs metadata {mv}")

    return state_obj



def _taxonomy_snapshot_identity(taxonomy_path: str, taxonomy_version: str, taxonomy_registry_path: str, report):
    """Optional: verify baseline taxonomy snapshot matches canonical taxonomy file in registry."""
    if not taxonomy_registry_path:
        return
    if not HAS_YAML:
        report.warn("[taxonomy] PyYAML not installed; cannot verify snapshot identity")
        return

    import os
    try:
        reg = yaml.safe_load(open(taxonomy_registry_path, encoding="utf-8"))
    except Exception as e:
        report.error(f"[taxonomy] Failed to load taxonomy registry: {e}")
        return

    rel = None
    for sci in reg.get("sciences", []):
        for v in sci.get("versions", []):
            if v.get("taxonomy_version") == taxonomy_version:
                rel = v.get("relpath")
                break
        if rel:
            break

    if not rel:
        report.warn(f"[taxonomy] taxonomy_version '{taxonomy_version}' not found in registry")
        return

    reg_dir = os.path.abspath(os.path.dirname(taxonomy_registry_path))
    canon = os.path.abspath(os.path.join(reg_dir, "..", rel))

    if not os.path.exists(canon):
        report.warn(f"[taxonomy] canonical taxonomy file not found at {canon}")
        return

    if _sha256_bytes(taxonomy_path) != _sha256_bytes(canon):
        report.error(f"[taxonomy] taxonomy snapshot mismatch: {taxonomy_path} != {canon}")
    else:
        report.note(f"[taxonomy] taxonomy snapshot matches registry canonical: {taxonomy_version}")

# Authoritative layer-token mapping (source: project_glossary.md §3)
# source_layer value → token that appears in atom_id middle segment
LAYER_TOKEN_MAP = {
    "matn": "matn",
    "footnote": "fn",
    "sharh": "sharh",
    "hashiya": "hashiya",
    "tahqiq_3ilmi": "tahqiq",
}

try:
    import jsonschema
except ImportError:
    print("ERROR: missing dependency jsonschema. Fix: python -m pip install -r requirements.txt")
    sys.exit(1)

BANNER = "Gold Standard Validator v0.3.13"

# Approved vocabularies (versioned — grow via schema bump)
CORE_ROLES = {"author_prose", "evidence", "exercise_content", "exercise_answer_content"}
CONTEXT_ROLES = {"preceding_setup", "classification_frame",
                 "back_reference", "cross_science_background"}


def load_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line: continue
            try:
                records.append((i, json.loads(line)))
            except json.JSONDecodeError as e:
                records.append((i, {"_parse_error": str(e), "_raw": line}))
    return records


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []

    def error(self, msg): self.errors.append(msg)
    def warn(self, msg): self.warnings.append(msg)
    def note(self, msg): self.info.append(msg)

    def print_summary(self):
        print("\n" + "=" * 70)
        print(f"  {BANNER} — VALIDATION REPORT")
        print("=" * 70)
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for e in self.errors: print(f"  • {e}")
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for w in self.warnings: print(f"  • {w}")
        if self.info:
            print(f"\nℹ️  INFO ({len(self.info)}):")
            for i in self.info: print(f"  • {i}")
        if not self.errors:
            print("\n✅ ALL CHECKS PASSED")
        else:
            print(f"\n🛑 {len(self.errors)} ERROR(S) — FIX BEFORE PROCEEDING")
        print("=" * 70)
        return len(self.errors) == 0


def validate_schema(records, schema, report, label=""):
    for line_num, rec in records:
        if "_parse_error" in rec:
            report.error(f"{label}Line {line_num}: JSON parse error: {rec['_parse_error']}")
            continue
        try:
            jsonschema.validate(rec, schema)
        except jsonschema.ValidationError as e:
            msg = str(e.message)[:200]
            rt = rec.get("record_type", "?")
            rid = rec.get("atom_id", rec.get("excerpt_id", rec.get("change_id", "")))
            report.error(f"{label}{rt} '{rid}': Schema: {msg}")


def validate_atoms(atoms, report):
    seen_ids = {}
    atom_map = {}
    for line_num, atom in atoms:
        aid = atom.get("atom_id", "???")
        if aid in seen_ids:
            report.error(f"Duplicate atom_id '{aid}' at lines {seen_ids[aid]} and {line_num}")
        seen_ids[aid] = line_num
        atom_map[aid] = atom

        layer = atom.get("source_layer", "")
        expected_token = LAYER_TOKEN_MAP.get(layer)
        if expected_token:
            actual_token = aid.split(":")[1] if ":" in aid else ""
            if actual_token != expected_token:
                report.error(f"{aid}: atom_id token '{actual_token}' "
                           f"doesn't match source_layer '{layer}' "
                           f"(expected token '{expected_token}')")
        elif layer:
            report.warn(f"{aid}: source_layer '{layer}' not in LAYER_TOKEN_MAP")

        anchor = atom.get("source_anchor", {})
        start = anchor.get("char_offset_start", 0)
        end = anchor.get("char_offset_end", 0)
        if end <= start:
            report.error(f"{aid}: source_anchor end ({end}) <= start ({start})")

        text = atom.get("text", "")
        if len(text) != end - start:
            report.warn(f"{aid}: text length ({len(text)}) != anchor span ({end - start})")

        atype = atom.get("atom_type", "")
        trigger = atom.get("bonded_cluster_trigger")
        if atype == "bonded_cluster" and trigger is None:
            report.error(f"{aid}: bonded_cluster without trigger")
        if atype != "bonded_cluster" and trigger is not None:
            report.error(f"{aid}: non-bonded_cluster with trigger set")

        if layer == "footnote" and atom.get("footnote_refs", []):
            report.error(f"{aid}: footnote-layer atom has footnote_refs")

        # Footnote ref status enforcement (v0.3.1)
        for ref in atom.get("footnote_refs", []):
            fids = ref.get("footnote_atom_ids", [])
            status = ref.get("footnote_ref_status", "normal")
            if status == "orphan":
                if fids:
                    report.error(f"{aid}: orphan footnote_ref has non-empty footnote_atom_ids")
                if not ref.get("orphan_note"):
                    report.error(f"{aid}: orphan footnote_ref missing orphan_note")
            else:
                if not fids:
                    report.error(f"{aid}: footnote_ref has empty footnote_atom_ids but status is not 'orphan'")

        # Heuristic: warn if atomization_notes mentions quotation but role might be wrong
        notes = atom.get("atomization_notes", "")
        if notes and ("quotation" in notes.lower() or "مقولة" in notes or "quoted" in notes.lower()):
            pass  # tracked via atom_map lookup in validate_excerpts

        if not text.strip():
            report.error(f"{aid}: empty text")

    report.note(f"Atoms: {len(atoms)} total, {len(seen_ids)} unique IDs")
    type_counts = defaultdict(int)
    layer_counts = defaultdict(int)
    for _, a in atoms:
        type_counts[a.get("atom_type", "?")] += 1
        layer_counts[a.get("source_layer", "?")] += 1
    report.note(f"Atom types: {dict(type_counts)}")
    report.note(f"Layers: {dict(layer_counts)}")
    return atom_map


def validate_offsets(atoms, canonical_files, report):
    canonical_texts = {}
    for layer, (fpath, expected_sha) in canonical_files.items():
        try:
            with open(fpath, encoding="utf-8") as f:
                content = f.read()
            actual_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if expected_sha and actual_sha != expected_sha:
                report.error(f"Canonical '{fpath}' SHA mismatch")
            canonical_texts[layer] = content
        except FileNotFoundError:
            report.error(f"Canonical file not found: {fpath}")

    ok = fail = 0
    for _, atom in atoms:
        layer = atom.get("source_layer", "")
        if layer not in canonical_texts: continue
        canon = canonical_texts[layer]
        s = atom.get("source_anchor", {}).get("char_offset_start")
        e = atom.get("source_anchor", {}).get("char_offset_end")
        if s is None or e is None: continue
        if atom.get("text", "") == canon[s:e]:
            ok += 1
        else:
            fail += 1
            report.error(f"{atom['atom_id']}: offset FAILED — text != canonical[{s}:{e}]")

    if fail == 0 and ok > 0:
        report.note(f"Offset audit PASSED: {ok}/{ok}")
    elif fail > 0:
        report.note(f"Offset audit: {ok} passed, {fail} FAILED")
    return canonical_texts


def validate_excerpts(excerpts, atom_map, report, allow_unknown_vocab=False,
                     allow_external_relations=False, supports_excerpt_title=False, supports_content_anomalies=False, strict_lints=False, external_excerpt_ids=None):
    """Validate excerpt records.

    Returns:
      - seen_excerpt_ids: dict excerpt_id -> line_num
      - core_ids: set of atom_ids used as core anywhere
      - excerpt_map: dict excerpt_id -> excerpt_record

    Core-uniqueness is enforced with two explicit exceptions:
      (1) interwoven groups (interwoven_group_id + B3_interwoven + interwoven_sibling connectivity)
      (2) shared evidence (shared_shahid) for role=evidence only
    """
    seen = {}
    excerpt_map = {}

    title_by_node = defaultdict(list) if supports_excerpt_title else None

    # atom_id -> list[(excerpt_id, role)]
    core_occ = defaultdict(list)

    for line_num, exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        if eid in seen:
            report.error(f"Duplicate excerpt_id '{eid}'")
        seen[eid] = line_num
        excerpt_map[eid] = exc

        layer = exc.get("source_layer", "")

        # ── Excerpt titles (schema v0.3.2+) ──
        if supports_excerpt_title and title_by_node is not None:
            title = exc.get("excerpt_title")
            treason = exc.get("excerpt_title_reason")
            node_id = exc.get("taxonomy_node_id", "")
            if not title or not treason:
                report.warn(f"{eid}: missing excerpt_title or excerpt_title_reason")
            else:
                title_by_node[node_id].append((title, eid))
                # Reference-style lint (titles reasoning)
                if isinstance(treason, str):
                    _lint_no_shorthand_excerpt_refs(treason, f"{eid}: excerpt_title_reason", report, strict_lints)

        # ── Content anomalies (schema v0.3.3+) ──
        if supports_content_anomalies:
            for an in (exc.get("content_anomalies") or []):
                # Reference-style lint across anomaly notes
                det = an.get('details','')
                if isinstance(det, str):
                    _lint_no_shorthand_excerpt_refs(det, f"{eid}: content_anomalies.details", report, strict_lints)
                syn = an.get('synthesis_instruction','')
                if isinstance(syn, str):
                    _lint_no_shorthand_excerpt_refs(syn, f"{eid}: content_anomalies.synthesis_instruction", report, strict_lints)
                for aid in (an.get("evidence_atom_ids") or []):
                    if aid not in atom_map:
                        report.error(f"{eid}: content_anomalies evidence_atom_id '{aid}' not found")

        # ── Core atoms ──
        for entry in exc.get("core_atoms", []):
            aid = entry["atom_id"] if isinstance(entry, dict) else entry
            role = entry.get("role", "") if isinstance(entry, dict) else ""

            if aid not in atom_map:
                report.error(f"{eid}: core atom '{aid}' not found")
                continue

            # Layer match
            if atom_map[aid].get("source_layer", "") != layer:
                report.error(
                    f"{eid}: core '{aid}' layer mismatch "
                    f"(atom={atom_map[aid]['source_layer']}, excerpt={layer})"
                )

            # Role allowlist
            if role not in CORE_ROLES:
                if allow_unknown_vocab:
                    report.warn(f"{eid}: unknown core role '{role}'")
                else:
                    report.error(f"{eid}: core role '{role}' not in {CORE_ROLES}")

            core_occ[aid].append((eid, role))

        # ── Context atoms ──
        for ctx in exc.get("context_atoms", []):
            caid = ctx.get("atom_id", "")
            crole = ctx.get("role", "")

            if caid not in atom_map:
                report.error(f"{eid}: context atom '{caid}' not found")
                continue

            # Layer match
            if atom_map[caid].get("source_layer", "") != layer:
                report.error(
                    f"{eid}: context '{caid}' layer mismatch "
                    f"(atom={atom_map[caid]['source_layer']}, excerpt={layer})"
                )

            # Forbid evidence in context
            if crole == "evidence":
                report.error(f"{eid}: context '{caid}' has role='evidence' — must be core")

            # Role allowlist
            if crole not in CONTEXT_ROLES and crole != "evidence":
                if allow_unknown_vocab:
                    report.warn(f"{eid}: unknown context role '{crole}'")
                else:
                    report.error(f"{eid}: context role '{crole}' not in {CONTEXT_ROLES}")

        # ── Heading path ──
        for hid in exc.get("heading_path", []):
            if hid not in atom_map:
                report.error(f"{eid}: heading_path '{hid}' not found")
                continue
            if atom_map[hid].get("atom_type", "") != "heading":
                report.error(
                    f"{eid}: heading_path '{hid}' is type "
                    f"'{atom_map[hid].get('atom_type')}', not 'heading'"
                )
            if atom_map[hid].get("source_layer", "") != layer:
                report.error(f"{eid}: heading_path '{hid}' layer mismatch")

        # ── Exercise ──
        kind = exc.get("excerpt_kind", "")
        if kind == "exercise":
            tn = exc.get("tests_nodes", [])
            ptn = exc.get("primary_test_node")
            if not tn:
                report.warn(f"{eid}: exercise has no tests_nodes")
            if ptn is not None and tn and ptn not in tn:
                report.error(f"{eid}: primary_test_node '{ptn}' not in tests_nodes")
        # ── Cross-science ──
        cs = bool(exc.get("cross_science_context", False))
        rhet = bool(exc.get("rhetorical_treatment_of_cross_science", False))
        rs = exc.get("related_science")
        ct = (exc.get("case_types") or [])
        has_d4 = "D4_cross_science" in ct

        # rhetorical_treatment is a subtype; it must not be true when cross_science_context is false.
        if rhet and not cs:
            report.error(f"{eid}: rhetorical_treatment_of_cross_science true but cross_science_context false")

        if cs and rs is None:
            report.error(f"{eid}: cross_science_context true but related_science null")
        if (not cs) and rs is not None:
            report.warn(f"{eid}: related_science set but cross_science_context false")

        # Training label consistency (binding): D4_cross_science mirrors cross_science_context.
        if cs and not has_d4:
            report.error(f"{eid}: cross_science_context true but case_types missing 'D4_cross_science'")
        if has_d4 and not cs:
            report.error(f"{eid}: case_types includes 'D4_cross_science' but cross_science_context false")

        # ── Relations (local checks; target-exists check happens after load) ──
        for rel in exc.get("relations", []):
            if rel.get("target_excerpt_id") is None and not rel.get("target_hint"):
                report.error(f"{eid}: relation '{rel.get('type')}' has no target and no hint")

        # ── Split discussion (binding: must mirror relations) — hint check only here ──
        sd = exc.get("split_discussion", {})
        if sd.get("is_split"):
            for c in sd.get("continues_in", []) + sd.get("continued_from", []):
                if c.get("target_excerpt_id") is None and not c.get("target_hint"):
                    report.error(f"{eid}: split pointer without hint")

    # ───────────────────────────────────────────────────────────────────
    # Post-pass graph / integrity checks
    # ───────────────────────────────────────────────────────────────────

    # Content anomaly excerpt refs (schema v0.3.3+)
    if supports_content_anomalies:
        for _eid, _exc in excerpt_map.items():
            for an in (_exc.get('content_anomalies') or []):
                for teid in (an.get('evidence_excerpt_ids') or []):
                    if teid not in seen:
                        if external_excerpt_ids and teid in external_excerpt_ids:
                            continue
                        report.error(f"{_eid}: content_anomalies evidence_excerpt_id '{teid}' not found")

    # Excerpt title uniqueness (binding guidance)
    if supports_excerpt_title and title_by_node is not None:
        for node_id, pairs in title_by_node.items():
            if not pairs:
                continue
            seen_titles = {}
            for title, eid in pairs:
                seen_titles.setdefault(title, []).append(eid)
            for title, eids in seen_titles.items():
                if len(eids) > 1:
                    report.error(f"Duplicate excerpt_title under node '{node_id}': '{title}' used by {sorted(eids)}")

    # Relation target existence
    for eid, exc in excerpt_map.items():
        for rel in exc.get("relations", []):
            tid = rel.get("target_excerpt_id")
            if tid is not None and tid not in excerpt_map:
                if external_excerpt_ids and tid in external_excerpt_ids:
                    continue
                if allow_external_relations:
                    report.warn(f"{eid}: relation '{rel.get('type')}' targets missing excerpt_id '{tid}'")
                else:
                    report.error(f"{eid}: relation '{rel.get('type')}' targets missing excerpt_id '{tid}'")

    # Split discussion must mirror relations (binding)
    for eid, exc in excerpt_map.items():
        rels = exc.get("relations", [])
        rel_cont = [r for r in rels if r.get("type") == "split_continues_in"]
        rel_from = [r for r in rels if r.get("type") == "split_continued_from"]

        sd = exc.get("split_discussion", {}) or {}
        sd_is = bool(sd.get("is_split"))

        if (rel_cont or rel_from) and not sd_is:
            report.error(f"{eid}: has split_* relations but split_discussion.is_split is false")
        if sd_is and not (rel_cont or rel_from):
            report.error(f"{eid}: split_discussion.is_split true but no split_* relations present")

        def norm_rel(r):
            return (r.get("type"), r.get("target_excerpt_id"), r.get("target_hint", ""))

        sd_cont = [norm_rel(r) for r in (sd.get("continues_in", []) or [])]
        sd_from = [norm_rel(r) for r in (sd.get("continued_from", []) or [])]
        rel_cont_n = [norm_rel(r) for r in rel_cont]
        rel_from_n = [norm_rel(r) for r in rel_from]

        if set(sd_cont) != set(rel_cont_n):
            report.error(f"{eid}: split_discussion.continues_in does not match relations split_continues_in")
        if set(sd_from) != set(rel_from_n):
            report.error(f"{eid}: split_discussion.continued_from does not match relations split_continued_from")

        if not sd_is:
            if (sd.get("continues_in") or sd.get("continued_from") or sd.get("split_note")):
                report.warn(f"{eid}: split_discussion not split but has non-default fields")

    # Build adjacency helpers
    def build_adj(edge_type):
        adj = defaultdict(set)
        for sid, exc in excerpt_map.items():
            for rel in exc.get("relations", []):
                if rel.get("type") != edge_type:
                    continue
                tid = rel.get("target_excerpt_id")
                if tid is None:
                    continue
                adj[sid].add(tid)
                adj[tid].add(sid)
        return adj

    adj_interwoven = build_adj("interwoven_sibling")
    adj_shared = build_adj("shared_shahid")

    def is_connected(nodes, adj):
        nodes = set(nodes)
        if not nodes:
            return True
        start = next(iter(nodes))
        stack = [start]
        seen_n = {start}
        while stack:
            cur = stack.pop()
            for nxt in adj.get(cur, set()):
                if nxt in nodes and nxt not in seen_n:
                    seen_n.add(nxt)
                    stack.append(nxt)
        return seen_n == nodes

    # Interwoven group invariants
    iw_groups = defaultdict(list)
    for eid, exc in excerpt_map.items():
        gid = exc.get("interwoven_group_id")
        if gid:
            iw_groups[gid].append(eid)
            if "B3_interwoven" not in (exc.get("case_types") or []):
                report.error(f"{eid}: interwoven_group_id set but case_types missing 'B3_interwoven'")

    for gid, eids in iw_groups.items():
        if len(eids) < 2:
            report.error(f"Interwoven group '{gid}' has only {len(eids)} excerpt(s) — must be >= 2")
        if not is_connected(eids, adj_interwoven):
            report.error(f"Interwoven group '{gid}' is not connected via interwoven_sibling relations")
        tax_nodes = {excerpt_map[e].get('taxonomy_node_id') for e in eids}
        if len(tax_nodes) == 1:
            report.warn(f"Interwoven group '{gid}' has only one taxonomy_node_id ({next(iter(tax_nodes))})")

    # Core duplication policy enforcement
    core_ids = set(core_occ.keys())
    dup_atoms = {aid: occ for aid, occ in core_occ.items() if len(occ) > 1}

    def allowed_shared_shahid(eids):
        return is_connected(eids, adj_shared)

    for aid in sorted(dup_atoms.keys()):
        occ = dup_atoms[aid]
        eids = [e for e, _ in occ]
        roles = {r for _, r in occ}
        if len(roles) != 1:
            report.error(f"Core-duplication: '{aid}' has inconsistent roles across excerpts: {sorted(roles)}")
            continue
        role = next(iter(roles))

        gids = {excerpt_map[e].get("interwoven_group_id") for e in eids}
        gids = {g for g in gids if g}

        if len(gids) == 1:
            gid = next(iter(gids))
            group_eids = iw_groups.get(gid, [])
            if not set(eids).issubset(set(group_eids)):
                report.error(f"Core-duplication: '{aid}' appears in excerpts not all in interwoven group '{gid}'")
            continue

        if role == "evidence" and allowed_shared_shahid(eids):
            continue

        report.error(
            f"Core-duplication: '{aid}' appears as core in {len(eids)} excerpts {sorted(set(eids))} "
            f"without a valid interwoven_group_id or shared_shahid evidence linkage"
        )

    for gid, eids in iw_groups.items():
        found = False
        for aid, occ in dup_atoms.items():
            if all(excerpt_map[e].get('interwoven_group_id') == gid for e, _ in occ):
                found = True
                break
        if not found:
            report.warn(f"Interwoven group '{gid}' has no duplicated core atoms — check if group_id was intended")

    report.note(f"Excerpts: {len(excerpts)}, Unique core atoms: {len(core_ids)}")
    if dup_atoms:
        report.note(f"Core-duplication occurrences: {len(dup_atoms)} atom_id(s) are core in multiple excerpts")

    # ── v0.3.1: Exercise item must belong to exactly one exercise set ──
    for _, exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        erole = exc.get("exercise_role")
        if erole in ("item", "answer"):
            set_rels = [r for r in exc.get("relations", [])
                       if r.get("type") == "belongs_to_exercise_set"]
            if len(set_rels) == 0:
                report.error(f"{eid}: exercise {erole} has no belongs_to_exercise_set relation")
            elif len(set_rels) > 1:
                report.error(f"{eid}: exercise {erole} belongs to {len(set_rels)} sets (must be exactly 1)")

    # ── v0.3.1: Quotation heuristic — warn if atomization_notes hint quotation + role=author_prose ──
    for _, exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        for entry in exc.get("core_atoms", []):
            aid = entry["atom_id"] if isinstance(entry, dict) else entry
            role = entry.get("role", "") if isinstance(entry, dict) else ""
            if aid in atom_map and role == "author_prose":
                notes = atom_map[aid].get("atomization_notes", "")
                if notes and ("quotation" in notes.lower() or "مقولة" in notes or "quoted" in notes.lower()):
                    report.warn(f"{eid}: atom '{aid}' notes hint quotation but core role is author_prose")

    return seen, core_ids, excerpt_map


def validate_heading_dualstate(atom_map, exclusions, excerpts, report):
    headings = {aid for aid, a in atom_map.items() if a.get("atom_type") == "heading"}
    excl_heading = {excl.get("atom_id") for _, excl in exclusions
                    if excl.get("exclusion_reason") == "heading_structural"}

    missing = headings - excl_heading
    for aid in sorted(missing):
        report.error(f"Heading '{aid}' has no exclusion record with 'heading_structural'")

    false_excl = excl_heading - headings
    for aid in sorted(false_excl):
        at = atom_map.get(aid, {}).get("atom_type", "MISSING")
        report.error(f"Exclusion '{aid}' is 'heading_structural' but type='{at}'")

    for _, exc in excerpts:
        for entry in exc.get("core_atoms", []):
            aid = entry["atom_id"] if isinstance(entry, dict) else entry
            if aid in headings:
                report.error(f"Heading '{aid}' in core_atoms of '{exc['excerpt_id']}'")
        for ctx in exc.get("context_atoms", []):
            if ctx.get("atom_id") in headings:
                report.error(f"Heading '{ctx['atom_id']}' in context of '{exc['excerpt_id']}'")

    if not (missing or false_excl):
        report.note(f"Heading dual-state PASSED: {len(headings)} headings")


def validate_coverage(atoms, core_ids, excerpts, exclusions, report):
    all_ids = {a.get("atom_id") for _, a in atoms}
    core_ids = set(core_ids)
    ctx_ids = set()
    heading_ids = set()
    for _, exc in excerpts:
        for ctx in exc.get("context_atoms", []):
            ctx_ids.add(ctx.get("atom_id"))
        for hid in exc.get("heading_path", []):
            heading_ids.add(hid)
    excl_ids = {excl.get("atom_id") for _, excl in exclusions}

    covered = core_ids | ctx_ids | heading_ids | excl_ids
    uncovered = all_ids - covered
    for aid in sorted(uncovered):
        report.error(f"Coverage gap: '{aid}' unaccounted")
    if not uncovered:
        report.note("Coverage invariant PASSED")

    bad = (core_ids | ctx_ids) & excl_ids
    for aid in sorted(bad):
        report.error(f"'{aid}' is both used AND excluded")


def validate_exclusions(exclusions, atom_map, report, strict_lints=False):
    for _, excl in exclusions:
        aid = excl.get("atom_id", "???")
        # Reference-style lint for exclusion_note
        en = excl.get('exclusion_note','')
        if isinstance(en, str):
            _lint_no_shorthand_excerpt_refs(en, f"exclusion '{aid}': exclusion_note", report, strict_lints)
        if aid not in atom_map:
            report.error(f"Exclusion for unknown atom '{aid}'")
        reason = excl.get("exclusion_reason", "")
        dup = excl.get("duplicate_of_atom_id")
        if reason == "duplicate_content" and dup is None:
            report.error(f"Exclusion '{aid}': duplicate_content but no duplicate_of_atom_id")
        if reason != "duplicate_content" and dup is not None:
            report.warn(f"Exclusion '{aid}': duplicate_of_atom_id set but reason='{reason}'")
    report.note(f"Exclusions: {len(exclusions)}")


def validate_source_spans(excerpts, atom_map, canonical_texts, report):
    for _, exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        ss = exc.get("source_spans")
        if ss is None: continue
        spans = ss.get("spans", [])
        layer = exc.get("source_layer", "")
        canon = canonical_texts.get(layer)

        span_atoms = set()
        for span in spans:
            for aid in span.get("atom_ids", []):
                span_atoms.add(aid)
                if aid in atom_map and canon:
                    anc = atom_map[aid].get("source_anchor", {})
                    if not (span["char_start"] <= anc.get("char_offset_start", -1) and
                            anc.get("char_offset_end", -1) <= span["char_end"]):
                        report.error(f"{eid}: span doesn't contain atom '{aid}'")

        exc_atoms = set()
        for e in exc.get("core_atoms", []):
            exc_atoms.add(e["atom_id"] if isinstance(e, dict) else e)
        for c in exc.get("context_atoms", []):
            exc_atoms.add(c.get("atom_id", ""))

        missing = exc_atoms - span_atoms
        if missing:
            report.error(f"{eid}: atoms missing from source_spans: {missing}")

    report.note("Source spans validation complete")


# ============================================================================
# TRACEABILITY LAYER (v0.3.2)
# ============================================================================

def extract_checklist_ids(checklists_path):
    """Extract all valid checklist IDs from the markdown file."""
    ids = set()
    with open(checklists_path, encoding="utf-8") as f:
        for line in f:
            # Match IDs like ATOM.A1, ATOM.B3, EXC.C1, PLACE.P4, PLACE.S2, etc.
            found = re.findall(r'\b(ATOM\.[A-Z]\d+|EXC\.[A-Z]\d+|PLACE\.[A-Z]\d+|REL\.[A-Z]\d+)\b', line)
            ids.update(found)
    return ids


# ============================================================================
# v0.3.12 lints: reference-style + checklist-version drift
# ============================================================================

SHORTHAND_EXCERPT_REF_RE = re.compile(r'(?<![A-Za-z0-9_.])E[0-9]{1,4}\b')

def _parse_version_tuple(v: str):
    """Parse versions like 'v0.3.12' into (0,3,12). Returns None if unparseable."""
    if not v:
        return None
    m = re.search(r'v?(\d+)\.(\d+)\.(\d+)', str(v).strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))

def _strict_lints_enabled(metadata_obj: dict | None) -> bool:
    """Enable strict lints for new-enough baselines (binding hardening threshold)."""
    bv = None
    if metadata_obj:
        bv = metadata_obj.get("baseline_version") or ""
    tup = _parse_version_tuple(bv)
    return bool(tup and tup >= (0, 3, 13))

def _lint_no_shorthand_excerpt_refs(text: str, where: str, report, strict: bool):
    """Lint ambiguous excerpt shorthand like 'E16' in note fields."""
    if not text:
        return
    if SHORTHAND_EXCERPT_REF_RE.search(text):
        msg = f"[ref_style] {where}: contains ambiguous excerpt shorthand like 'E16'. Use explicit excerpt_id (e.g., jawahir:exc:000016)."
        if strict:
            report.error(msg)
        else:
            report.warn(msg)

def extract_checklist_version(checklists_path: str) -> str:
    """Best-effort extract of checklist version token from the markdown heading.

    Expected heading pattern: '# Gold Standard Checklists v0.4' -> 'checklists_v0.4'
    Returns '' if not found.
    """
    try:
        with open(checklists_path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                if s.startswith("#"):
                    m = re.search(r'v(\d+\.\d+)', s)
                    if m:
                        return f"checklists_v{m.group(1)}"
                # Stop after the first non-empty non-heading line
                break
    except Exception:
        return ""
    return ""

MANDATORY_PLACEMENT_KEYS = {"PLACE.P1", "PLACE.P2", "PLACE.P3", "PLACE.P4",
                            "PLACE.P5", "PLACE.P6", "PLACE.P7", "PLACE.P8"}

# Required labeled blocks in boundary_reasoning (simple regex)
BOUNDARY_REASONING_BLOCKS = ["GROUPING:", "BOUNDARY:", "ROLES:", "PLACEMENT:",
                             "CHECKLIST:", "ALTS:"]

# Supportive dependency review block (prep-phase hardening; conditional lint)
SUPPORTIVE_DEPENDENCIES_MARKER = "SUPPORTIVE_DEPENDENCIES:"
SUPPORTIVE_DEPENDENCY_EXCEPTION_MARKER = "SUPPORTIVE_DEPENDENCY_EXCEPTION:"
SUPPORTIVE_DEP_ALLOWED_CONTEXT_ROLES = {"preceding_setup", "cross_science_background"}

# Required sections in atomization_notes
ATOM_NOTES_SECTIONS = ["TYPE:", "BOUNDARY:", "CHECKLIST:"]


def validate_decisions(decisions_path, excerpt_ids, checklists_path, report, metadata_obj=None):
    """Validate the decision log JSONL against excerpts and checklists."""
    strict = _strict_lints_enabled(metadata_obj)
    expected_checklists_version = extract_checklist_version(checklists_path) if checklists_path else ""
    valid_checklist_ids = set()
    if checklists_path:
        try:
            valid_checklist_ids = extract_checklist_ids(checklists_path)
            report.note(f"Checklists: {len(valid_checklist_ids)} IDs loaded from {checklists_path}")
        except FileNotFoundError:
            report.error(f"Checklists file not found: {checklists_path}")
            return

    records = load_jsonl(decisions_path)
    excerpt_decisions = {}
    atom_decisions = []

    for line_num, rec in records:
        if "_parse_error" in rec:
            report.error(f"[decisions] Line {line_num}: JSON parse error: {rec['_parse_error']}")
            continue

        rt = rec.get("record_type", "???")

        if rt == "excerpt_decision":
            eid = rec.get("excerpt_id", "???")

            # Duplicate check
            if eid in excerpt_decisions:
                report.error(f"[decisions] Duplicate excerpt_decision for '{eid}'")
            excerpt_decisions[eid] = rec

            # Excerpt must exist
            if eid not in excerpt_ids:
                report.error(f"[decisions] excerpt_decision for '{eid}' — "
                           f"excerpt not found in excerpts file")

            # Placement checklist completeness
            pc = rec.get("placement_checklist", {})
            for pk in MANDATORY_PLACEMENT_KEYS:
                if pk not in pc:
                    report.error(f"[decisions] '{eid}': missing mandatory "
                               f"placement checklist item '{pk}'")
                else:
                    item = pc[pk]
                    if isinstance(item, dict):
                        note = item.get('note', '')
                        if isinstance(note, str):
                            _lint_no_shorthand_excerpt_refs(note, f"[decisions] '{eid}' {pk}.note", report, strict)
                    if not isinstance(item, dict) or "pass" not in item:
                        report.error(f"[decisions] '{eid}': '{pk}' must have "
                                   f"'pass' (boolean) and 'note' fields")
                    elif not isinstance(item.get("pass"), bool):
                        report.error(f"[decisions] '{eid}': '{pk}'.pass must be boolean")

            # Validate checklist ID references in solidifying_indicators
            for sid in rec.get("solidifying_indicators", []):
                if valid_checklist_ids and sid not in valid_checklist_ids:
                    report.error(f"[decisions] '{eid}': unknown solidifying indicator '{sid}'")

            # Checklist version (drift-resistant)
            cv = (rec.get('checklist_version') or '').strip()
            if not cv:
                msg = f"[decisions] '{eid}': missing checklist_version"
                (report.error(msg) if strict else report.warn(msg))
            elif expected_checklists_version and cv != expected_checklists_version:
                msg = (f"[decisions] '{eid}': checklist_version='{cv}' does not match checklists file version '{expected_checklists_version}'")
                (report.error(msg) if strict else report.warn(msg))

            # Reference-style lint across free-text note fields (decision-side)
            notes_txt = rec.get('notes', '')
            if isinstance(notes_txt, str):
                _lint_no_shorthand_excerpt_refs(notes_txt, f"[decisions] '{eid}' notes", report, strict)
            for alt in (rec.get('alternatives_considered') or []):
                if isinstance(alt, dict):
                    rr = alt.get('rejection_reason', '')
                    if isinstance(rr, str):
                        _lint_no_shorthand_excerpt_refs(rr, f"[decisions] '{eid}' alternatives_considered.rejection_reason", report, strict)

        elif rt == "atom_decision":
            atom_decisions.append(rec)
            # Validate checklist refs
            for cref in rec.get("checklist_refs", []):
                if valid_checklist_ids and cref not in valid_checklist_ids:
                    report.error(f"[decisions] atom '{rec.get('atom_id', '???')}': "
                               f"unknown checklist ref '{cref}'")
        else:
            report.warn(f"[decisions] Line {line_num}: unknown record_type '{rt}'")

    # Every excerpt must have a decision record
    for eid in excerpt_ids:
        if eid not in excerpt_decisions:
            report.error(f"[decisions] No excerpt_decision record for '{eid}'")

    report.note(f"Decisions: {len(excerpt_decisions)} excerpt, "
                f"{len(atom_decisions)} atom")


def validate_boundary_reasoning_blocks(excerpts, report, strict_lints=False):
    """Check that every excerpt's boundary_reasoning contains required labeled blocks."""
    for _, exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        br = exc.get("boundary_reasoning", "")
        for block in BOUNDARY_REASONING_BLOCKS:
            if block not in br:
                report.error(f"[traceability] '{eid}': boundary_reasoning "
                           f"missing required block '{block}'")
        # Reference-style lint for boundary_reasoning
        if isinstance(br, str):
            _lint_no_shorthand_excerpt_refs(br, f"{eid}: boundary_reasoning", report, strict_lints)


def _extract_supportive_dependencies_yaml(br_text: str):
    """Extract the SUPPORTIVE_DEPENDENCIES YAML block from boundary_reasoning.

    Returns the YAML text (including the marker line) or None if not present.

    Extraction rule:
      - Start at the first line whose stripped text equals SUPPORTIVE_DEPENDENCIES:
      - Continue until the next *top-level* ALLCAPS_LABEL: line (no indentation),
        or end-of-text.
    """
    if not br_text:
        return None
    lines = br_text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip() == SUPPORTIVE_DEPENDENCIES_MARKER:
            start = i
            break
    if start is None:
        return None

    block = [lines[start]]
    for j in range(start + 1, len(lines)):
        ln = lines[j]
        # Stop at the next top-level labeled block header
        if ln and (not ln.startswith(" ") and not ln.startswith("\t")):
            if re.match(r"^[A-Z][A-Z0-9_]*:\s*$", ln) and ln.strip() != SUPPORTIVE_DEPENDENCIES_MARKER:
                break
        block.append(ln)
    return "\n".join(block).rstrip() + "\n"


def lint_supportive_dependencies_blocks(excerpts, atom_map, report):
    """Conditional lint: validate the SUPPORTIVE_DEPENDENCIES YAML block shape.

    This is *optional* in the sense that it only runs when the marker block exists.
    When present, it becomes strict: malformed YAML or inconsistent references are errors.
    """
    if not HAS_YAML:
        report.error("[support_dep] PyYAML not available; cannot lint SUPPORTIVE_DEPENDENCIES blocks")
        return

    for _, exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        br = exc.get("boundary_reasoning", "") or ""

        yaml_text = _extract_supportive_dependencies_yaml(br)
        if yaml_text is None:
            continue  # optional lint: only triggers if marker present

        # Parse YAML
        try:
            parsed = yaml.safe_load(yaml_text)
        except Exception as e:
            report.error(f"[support_dep] '{eid}': SUPPORTIVE_DEPENDENCIES YAML parse FAIL — {e}")
            continue

        if not isinstance(parsed, dict) or "SUPPORTIVE_DEPENDENCIES" not in parsed:
            report.error(f"[support_dep] '{eid}': YAML must be a mapping with key 'SUPPORTIVE_DEPENDENCIES'")
            continue

        items = parsed.get("SUPPORTIVE_DEPENDENCIES")
        if not isinstance(items, list) or not items:
            report.error(f"[support_dep] '{eid}': SUPPORTIVE_DEPENDENCIES must be a non-empty list")
            continue

        # Build context/core maps for cross-checks
        ctx_entries = exc.get("context_atoms", []) or []
        ctx_roles = {}
        for ce in ctx_entries:
            if isinstance(ce, dict) and ce.get("atom_id"):
                ctx_roles[ce["atom_id"]] = ce.get("role")
        core_entries = exc.get("core_atoms", []) or []
        core_ids = set()
        for ce in core_entries:
            if isinstance(ce, dict) and ce.get("atom_id"):
                core_ids.add(ce["atom_id"])

        seen_atoms = set()

        for idx, it in enumerate(items):
            if not isinstance(it, dict):
                report.error(f"[support_dep] '{eid}': item[{idx}] must be a mapping")
                continue

            # Required scalar fields
            oth = it.get("other_topic_hint")
            if not isinstance(oth, str) or not oth.strip():
                report.error(f"[support_dep] '{eid}': item[{idx}].other_topic_hint must be non-empty string")

            exp_node = it.get("other_topic_expected_node_id", "")
            if exp_node is not None and not isinstance(exp_node, str):
                report.error(f"[support_dep] '{eid}': item[{idx}].other_topic_expected_node_id must be string (or '')")

            atoms = it.get("atoms")
            if not isinstance(atoms, list) or not atoms or not all(isinstance(a, str) and a for a in atoms):
                report.error(f"[support_dep] '{eid}': item[{idx}].atoms must be a non-empty list of atom_id strings")
                atoms = []

            # Dependency test
            dt = it.get("dependency_test")
            if not isinstance(dt, dict):
                report.error(f"[support_dep] '{eid}': item[{idx}].dependency_test must be a mapping")
                dt = {}
            rb = dt.get("removal_breaks_X")
            ty = dt.get("teaches_Y")
            if not isinstance(rb, bool):
                report.error(f"[support_dep] '{eid}': item[{idx}].dependency_test.removal_breaks_X must be boolean")
            elif rb is False:
                report.error(f"[support_dep] '{eid}': item[{idx}] removal_breaks_X=false contradicts supportive dependency necessity")
            if not isinstance(ty, bool):
                report.error(f"[support_dep] '{eid}': item[{idx}].dependency_test.teaches_Y must be boolean")
            elif ty is True:
                report.error(f"[support_dep] '{eid}': item[{idx}] teaches_Y=true → must split; supportive dependency block is invalid")

            why = it.get("why_needed")
            if not isinstance(why, str) or not why.strip():
                report.error(f"[support_dep] '{eid}': item[{idx}].why_needed must be non-empty string")

            # Boundedness
            bd = it.get("boundedness")
            if not isinstance(bd, dict):
                report.error(f"[support_dep] '{eid}': item[{idx}].boundedness must be a mapping")
                bd = {}
            within = bd.get("within_default")
            excpt = bd.get("exception")
            if not isinstance(within, bool):
                report.error(f"[support_dep] '{eid}': item[{idx}].boundedness.within_default must be boolean")
            if excpt is not None and not isinstance(excpt, str):
                report.error(f"[support_dep] '{eid}': item[{idx}].boundedness.exception must be string")
            if isinstance(within, bool):
                if within and (isinstance(excpt, str) and excpt.strip()):
                    report.error(f"[support_dep] '{eid}': item[{idx}] within_default=true but exception is non-empty")
                if (within is False) and (not isinstance(excpt, str) or not excpt.strip()):
                    report.error(f"[support_dep] '{eid}': item[{idx}] within_default=false requires non-empty boundedness.exception")
                if (within is False) and SUPPORTIVE_DEPENDENCY_EXCEPTION_MARKER not in br:
                    report.error(f"[support_dep] '{eid}': item[{idx}] within_default=false requires '{SUPPORTIVE_DEPENDENCY_EXCEPTION_MARKER}' line in boundary_reasoning")

            # Handling
            hd = it.get("handling")
            if not isinstance(hd, dict):
                report.error(f"[support_dep] '{eid}': item[{idx}].handling must be a mapping")
                hd = {}
            placement = hd.get("placement")
            if placement != "context_atoms":
                report.error(f"[support_dep] '{eid}': item[{idx}].handling.placement must be 'context_atoms'")
            roles = hd.get("context_roles")
            if not isinstance(roles, list) or not roles or not all(isinstance(r, str) and r for r in roles):
                report.error(f"[support_dep] '{eid}': item[{idx}].handling.context_roles must be non-empty list")
                roles = []
            else:
                bad_roles = [r for r in roles if r not in SUPPORTIVE_DEP_ALLOWED_CONTEXT_ROLES]
                if bad_roles:
                    report.error(f"[support_dep] '{eid}': item[{idx}].handling.context_roles contains disallowed roles: {bad_roles}")

            # Atom cross-checks: must be in excerpt context_atoms, not in core_atoms, exist in atom_map
            for a in atoms:
                if a in seen_atoms:
                    report.error(f"[support_dep] '{eid}': atom '{a}' is listed multiple times across SUPPORTIVE_DEPENDENCIES items")
                seen_atoms.add(a)

                if a not in ctx_roles:
                    report.error(f"[support_dep] '{eid}': atom '{a}' must appear in excerpt.context_atoms")
                else:
                    ar = ctx_roles.get(a)
                    if roles and ar not in roles:
                        report.error(f"[support_dep] '{eid}': atom '{a}' has context role '{ar}', not in handling.context_roles {roles}")
                if a in core_ids:
                    report.error(f"[support_dep] '{eid}': atom '{a}' cannot be both supportive dependency and core_atom")
                if atom_map is not None and a not in atom_map:
                    report.error(f"[support_dep] '{eid}': atom '{a}' not found in atoms file")

            # Optional links
            links = it.get("links")
            if links is not None:
                if not isinstance(links, dict):
                    report.error(f"[support_dep] '{eid}': item[{idx}].links must be mapping if present")
                else:
                    rid = links.get("related_excerpt_id", "")
                    rty = links.get("relation_type_if_linked", "")
                    if (rid and not rty) or (rty and not rid):
                        report.error(f"[support_dep] '{eid}': item[{idx}].links requires both related_excerpt_id and relation_type_if_linked when linking")


def validate_atomization_notes_format(atoms, report):
    """Check that every atom's atomization_notes follows the structured template."""
    for _, atom in atoms:
        aid = atom.get("atom_id", "???")
        notes = atom.get("atomization_notes", "")
        if notes is None:
            notes = ""

        # Only enforce for atoms that have notes (null/empty is a separate concern)
        if not notes.strip():
            report.warn(f"[traceability] '{aid}': empty atomization_notes")
            continue

        for section in ATOM_NOTES_SECTIONS:
            if section not in notes:
                report.error(f"[traceability] '{aid}': atomization_notes "
                           f"missing required section '{section}'")

        # Bonded clusters must also have BOND: section
        if atom.get("atom_type") == "bonded_cluster":
            if "BOND:" not in notes:
                report.error(f"[traceability] '{aid}': bonded_cluster "
                           f"atomization_notes missing 'BOND:' section")





def validate_taxonomy_changes(tc_records, schema, report, excerpt_ids=None,
                              excerpt_records=None, allow_external_excerpts=False, external_excerpt_ids=None):
    """Validate taxonomy change records with cross-referencing."""
    if not tc_records:
        report.note("No taxonomy changes")
        return
    if schema:
        validate_schema(tc_records, schema, report, label="[TC] ")
    seen = set()
    tc_by_id = {}
    for _, tc in tc_records:
        cid = tc.get("change_id", "???")
        if cid in seen: report.error(f"[TC] Duplicate '{cid}'")
        seen.add(cid)
        tc_by_id[cid] = tc
        for f in ["node_id", "reasoning", "change_type", "book_id"]:
            if not tc.get(f):
                report.error(f"[TC] '{cid}': missing '{f}'")
        # Cross-check triggered_by_excerpt_id exists
        trigger = tc.get("triggered_by_excerpt_id")
        if trigger and excerpt_ids is not None:
            if trigger not in excerpt_ids:
                if external_excerpt_ids and trigger in external_excerpt_ids:
                    pass
                elif allow_external_excerpts:
                    report.warn(f"[TC] '{cid}': triggered_by_excerpt_id '{trigger}' not in this excerpt set (likely earlier passage)")
                else:
                    report.error(f"[TC] '{cid}': triggered_by_excerpt_id '{trigger}' not found in excerpts")
        # version_before != version_after
        vb = tc.get("taxonomy_version_before", "")
        va = tc.get("taxonomy_version_after", "")
        if vb and va and vb == va:
            report.error(f"[TC] '{cid}': version_before == version_after ('{vb}')")
        # node_added must have parent_node_id
        if tc.get("change_type") == "node_added" and not tc.get("parent_node_id"):
            report.error(f"[TC] '{cid}': node_added without parent_node_id")

    # ── Bidirectional link check ──
    # Forward: TC.triggered_by_excerpt_id → excerpt must have taxonomy_change_triggered = TC.change_id
    if excerpt_records is not None:
        exc_map = {exc.get("excerpt_id"): exc for _, exc in excerpt_records}
        for _, tc in tc_records:
            cid = tc.get("change_id", "???")
            trigger = tc.get("triggered_by_excerpt_id")
            if trigger and trigger in exc_map:
                exc_tc = exc_map[trigger].get("taxonomy_change_triggered")
                if exc_tc != cid:
                    report.error(f"[TC] '{cid}': triggered_by '{trigger}', "
                               f"but excerpt has taxonomy_change_triggered='{exc_tc}' (expected '{cid}')")
        # Reverse: excerpt.taxonomy_change_triggered → must exist in TC records
        for eid, exc in exc_map.items():
            tct = exc.get("taxonomy_change_triggered")
            if tct and tct not in tc_by_id:
                report.error(f"[TC] Excerpt '{eid}': taxonomy_change_triggered='{tct}' "
                           f"but no such TC record exists")

    report.note(f"Taxonomy changes: {len(tc_records)}")


def validate_taxonomy_tree(excerpts, taxonomy_path, report):
    """Validate excerpt taxonomy_node_ids against the taxonomy YAML, with strict leaf policy."""
    if not HAS_YAML:
        report.warn("PyYAML not installed — skipping taxonomy tree validation")
        return

    with open(taxonomy_path, encoding="utf-8") as f:
        tax = yaml.safe_load(f)

    all_nodes = {}

    def collect(nodes, parent_id=None, ancestors=None):
        if ancestors is None:
            ancestors = []
        for n in nodes:
            nid = n["id"]
            children = n.get("children") or []
            has_children = len(children) > 0
            leaf_flag = n.get("leaf", None)

            # Strict leaf policy (binding v0.3.2): leaf must be explicit
            if has_children and leaf_flag is True:
                report.error(f"Taxonomy: node '{nid}' marked leaf:true but has children")
            if (not has_children) and (leaf_flag is not True):
                report.error(f"Taxonomy: node '{nid}' has no children but missing leaf:true")
            if has_children and leaf_flag is False:
                report.warn(f"Taxonomy: node '{nid}' has children but explicitly leaf:false (prefer omit)")

            is_leaf = (leaf_flag is True)

            all_nodes[nid] = {
                "title": n.get("title", ""),
                "leaf": is_leaf,
                "parent": parent_id,
                "ancestors": list(ancestors),
            }

            if has_children:
                collect(children, nid, ancestors + [nid])

    collect(tax["taxonomy"]["nodes"])
    report.note(f"Taxonomy tree: {len(all_nodes)} nodes, {sum(1 for v in all_nodes.values() if v['leaf'])} leaves")

    for _, exc in excerpts:
        eid = exc.get("excerpt_id", "???")
        nid = exc.get("taxonomy_node_id", "")
        if not nid:
            report.error(f"{eid}: missing taxonomy_node_id")
            continue
        if nid not in all_nodes:
            report.error(f"{eid}: taxonomy_node_id '{nid}' not found in taxonomy tree")
            continue
        if not all_nodes[nid]["leaf"]:
            report.error(f"{eid}: taxonomy_node_id '{nid}' is not a leaf node (title: {all_nodes[nid]['title']})")

    report.note("Taxonomy tree validation complete")


def main():
    parser = argparse.ArgumentParser(description=BANNER)
    parser.add_argument("--atoms", required=True, nargs="+")
    parser.add_argument("--excerpts", default=None)
    parser.add_argument("--schema", default=None)
    parser.add_argument("--canonical", nargs="+", default=[])
    parser.add_argument("--taxonomy-changes", default=None)
    parser.add_argument("--taxonomy", default=None,
                       help="Taxonomy YAML file for node existence/leaf validation")
    parser.add_argument("--decisions", default=None,
                       help="Decision log JSONL file for traceability validation")
    parser.add_argument("--checklists", default=None,
                       help="Checklists markdown file for ID validation")
    parser.add_argument("--allow-unknown-vocab", action="store_true",
                       help="Downgrade unknown roles from error to warning")
    parser.add_argument("--allow-external-relations", action="store_true",
                       help="Allow relations to excerpt_ids not present in this excerpt set (warning instead of error)")
    parser.add_argument("--resolve-external-from-active-gold", action="store_true",
                       help="Resolve cross-passage excerpt references against the union of excerpt_ids from all ACTIVE_GOLD baselines under the ABD root. Suppresses missing-target warnings for valid cross-baseline links.")
    parser.add_argument("--skip-traceability", action="store_true",
                       help="Skip traceability checks (for validating Passage 1 data)")
    parser.add_argument("--allow-archive", action="store_true",
                       help="Allow running validation on paths under _ARCHIVE/ (non-authoritative)")
    parser.add_argument("--metadata", default=None,
                       help="Passage metadata JSON for validation (auto-detected if omitted)")
    parser.add_argument("--manifest", default=None,
                       help="Baseline manifest JSON for validation (auto-detected if omitted)")
    parser.add_argument("--support-schemas", default=None,
                       help="Directory containing support JSON schemas (auto-detected if omitted)")
    parser.add_argument("--taxonomy-registry", default=None,
                       help="Path to taxonomy_registry.yaml to verify taxonomy snapshot identity (optional)")
    parser.add_argument("--skip-clean-input-check", action="store_true",
                       help="Skip Checkpoint-1 clean input artifact checks")
    args = parser.parse_args()

    print(f"\n{BANNER}")
    print("-" * 70)
    report = Report()


    # Archive guard (non-authoritative data lives under _ARCHIVE/)
    all_paths = []
    all_paths.extend(args.atoms or [])
    if args.excerpts: all_paths.append(args.excerpts)
    if args.schema: all_paths.append(args.schema)
    if args.taxonomy_changes: all_paths.append(args.taxonomy_changes)
    if args.taxonomy: all_paths.append(args.taxonomy)
    if args.decisions: all_paths.append(args.decisions)
    if args.checklists: all_paths.append(args.checklists)
    all_paths.extend(args.canonical or [])
    if not _archive_guard(all_paths, args.allow_archive, report):
        report.print_summary()
        sys.exit(1)

    # Base directory for auto-detection
    import os
    base_dir = os.path.dirname(os.path.abspath((args.excerpts or args.atoms[0])))

    # Optional external excerpt-id resolution across the active gold set
    external_excerpt_ids = set()
    if getattr(args, 'resolve_external_from_active_gold', False):
        external_excerpt_ids = _resolve_external_excerpt_ids_from_active_gold(base_dir, report)


    # Auto-detect metadata/manifest if omitted
    metadata_path = args.metadata or _auto_detect_one(base_dir, "passage*_metadata.json")
    manifest_path = args.manifest or (os.path.join(base_dir, "baseline_manifest.json") if os.path.exists(os.path.join(base_dir, "baseline_manifest.json")) else None)

    # Support schemas directory
    schemas_dir = args.support_schemas or (os.path.join(base_dir, "schemas") if os.path.isdir(os.path.join(base_dir, "schemas")) else None)

    # Validate support files against schemas when possible
    metadata_obj = None
    if schemas_dir and metadata_path and os.path.exists(metadata_path):
        try:
            meta_schema = _load_support_schema(schemas_dir, "passage_metadata_schema_v0.1.json")
            metadata_obj = _validate_json_file(metadata_path, meta_schema, report, "[support:metadata]")
        except Exception as e:
            report.warn(f"[support:metadata] Could not validate metadata schema: {e}")


    # Strict linting threshold (v0.3.12+): enable stronger drift/ref-style checks for newer baselines
    strict_lints = _strict_lints_enabled(metadata_obj)

    if schemas_dir and manifest_path and os.path.exists(manifest_path):
        try:
            man_schema = _load_support_schema(schemas_dir, "baseline_manifest_schema_v0.1.json")
            _validate_json_file(manifest_path, man_schema, report, "[support:manifest]")
        except Exception as e:
            report.warn(f"[support:manifest] Could not validate manifest schema: {e}")

    # Checkpoint state machine (CP0-CP6)
    _check_checkpoint_state(base_dir, metadata_obj, schemas_dir, getattr(args, "skip_checkpoint_state_check", False), report)

    # Checkpoint-1 clean inputs (if metadata present)
    if metadata_obj and metadata_obj.get("passage_id") and args.canonical:
        canon_map = {}
        for kv in args.canonical:
            if ":" not in kv:
                continue
            k, v = kv.split(":", 1)
            canon_map[k] = os.path.join(base_dir, v) if not os.path.isabs(v) else v
        _check_clean_inputs(base_dir, metadata_obj["passage_id"], canon_map, args.support_schemas, args.skip_clean_input_check, report)

    # Optional taxonomy snapshot identity check
    if metadata_obj and args.taxonomy and args.taxonomy_registry:
        _taxonomy_snapshot_identity(args.taxonomy, metadata_obj.get("taxonomy_version", ""), args.taxonomy_registry, report)

    schema = None
    if args.schema:
        with open(args.schema, encoding="utf-8") as f:
            schema = json.load(f)
        report.note(f"Schema: {args.schema}")

    # Atoms
    atom_records = []
    for p in args.atoms: atom_records.extend(load_jsonl(p))
    atoms = [(ln, r) for ln, r in atom_records
             if r.get("record_type") == "atom" or "_parse_error" in r]
    if schema: validate_schema(atoms, schema, report, "[atom] ")
    atom_map = validate_atoms(atoms, report)

    # Book ID
    bids = {a.get("book_id") for _, a in atoms if a.get("book_id")}
    if len(bids) > 1: report.error(f"Multiple book_ids: {bids}")
    elif bids:
        bid = bids.pop()
        for _, a in atoms:
            pfx = a.get("atom_id", "").split(":")[0]
            if pfx and pfx != bid:
                report.error(f"'{a['atom_id']}' prefix != book_id '{bid}'")

    # Offsets
    canonical_texts = {}
    if args.canonical:
        cf = {}
        for spec in args.canonical:
            parts = spec.split(":", 1)
            if len(parts) == 2: cf[parts[0]] = (parts[1], None)
            else: report.warn(f"Bad --canonical: '{spec}'")
        canonical_texts = validate_offsets(atoms, cf, report)

    # Excerpts + exclusions
    excerpts = []; exclusions = []; exc_ids = {}; core_ids = set(); excerpt_map = {}
    if args.excerpts:
        recs = load_jsonl(args.excerpts)
        excerpts = [(ln, r) for ln, r in recs if r.get("record_type") == "excerpt"]
        exclusions = [(ln, r) for ln, r in recs if r.get("record_type") == "exclusion"]
        if schema: validate_schema(recs, schema, report, "[exc] ")
        exc_ids, core_ids, excerpt_map = validate_excerpts(
            excerpts, atom_map, report,
            allow_unknown_vocab=args.allow_unknown_vocab,
            allow_external_relations=args.allow_external_relations,
            supports_excerpt_title=bool(schema and schema.get('definitions', {}).get('excerpt_record', {}).get('properties', {}).get('excerpt_title')),
            supports_content_anomalies=bool(schema and schema.get('definitions', {}).get('excerpt_record', {}).get('properties', {}).get('content_anomalies')),
            strict_lints=strict_lints,
            external_excerpt_ids=external_excerpt_ids,
        )
        validate_coverage(atoms, core_ids, excerpts, exclusions, report)
        validate_heading_dualstate(atom_map, exclusions, excerpts, report)
        if canonical_texts:
            validate_source_spans(excerpts, atom_map, canonical_texts, report)

    if exclusions:
        validate_exclusions(exclusions, atom_map, report, strict_lints=strict_lints)

    # Taxonomy changes
    if args.taxonomy_changes:
        tc = load_jsonl(args.taxonomy_changes)
        tc_only = [(ln, r) for ln, r in tc
                   if r.get("record_type") == "taxonomy_change" or "_parse_error" in r]
        validate_taxonomy_changes(tc_only, schema, report,
                                excerpt_ids=set(exc_ids.keys()) if exc_ids else None,
                                excerpt_records=excerpts if excerpts else None,
                                allow_external_excerpts=args.allow_external_relations,
                                external_excerpt_ids=external_excerpt_ids)

    # Taxonomy tree (node existence + leaf validation)
    if args.taxonomy and excerpts:
        validate_taxonomy_tree(excerpts, args.taxonomy, report)

    # ── Traceability layer (v0.3.2) ──
    if not args.skip_traceability:
        # Decision log validation
        if args.decisions and excerpts:
            validate_decisions(args.decisions, set(exc_ids.keys()), args.checklists, report, metadata_obj=metadata_obj)
        elif args.decisions and not excerpts:
            report.warn("--decisions provided but no --excerpts to cross-reference")
        elif not args.decisions and excerpts:
            report.warn("[traceability] No --decisions file provided — "
                       "skipping decision log validation")

        # boundary_reasoning labeled blocks
        if excerpts:
            validate_boundary_reasoning_blocks(excerpts, report, strict_lints=strict_lints)
            # Optional/conditional lint: SUPPORTIVE_DEPENDENCIES YAML review block
            lint_supportive_dependencies_blocks(excerpts, atom_map, report)

        # atomization_notes structured format
        if atoms:
            validate_atomization_notes_format(atoms, report)
    else:
        report.note("Traceability checks skipped (--skip-traceability)")

    passed = report.print_summary()
    sys.exit(0 if passed else 1)

if __name__ == "__main__":
    main()
